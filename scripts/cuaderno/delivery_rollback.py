"""Restore a trusted backup with its exact old image into retained NEW local targets."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

try:
    from .delivery_backup import media_manifest
except ImportError:  # Direct invocation: python scripts/cuaderno/delivery_rollback.py
    from delivery_backup import media_manifest


ROOT = Path(__file__).resolve().parents[2]
DB_USER = "cuaderno_demo"
DATABASE_CONTAINERS = {
    "baseline": "cuaderno-g0-t002-db",
    "release": "cuaderno-release-db",
}
IMAGE_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
SUFFIX_PATTERN = re.compile(r"[0-9a-f]{12}\Z")
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class DockerBoundary:
    def run(self, argv, *, data: bytes | None = None) -> bytes:
        result = subprocess.run(
            list(argv), input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            stderr = result.stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Docker falló ({result.returncode}): {stderr}")
        return result.stdout

    def container_exists(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "container", "inspect", name],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        stderr = result.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"No se pudo comprobar el runtime destino ({result.returncode}): {stderr}")


@dataclass(frozen=True)
class RollbackSpec:
    workspace_root: Path
    bundle: Path
    manifest: dict
    image_id: str
    database_container: str
    database_network: str
    database_password: str
    manifest_sha256: str
    login_password: str
    smoke_path: Path
    smoke_sha256: str


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _local_environment() -> None:
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}:
        raise ValueError("Rollback restringido a un entorno local/test aislado.")


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} debe ser un archivo regular local, sin enlaces.")


def _validate_backup_root(root: Path, resolved_backup_root: Path) -> None:
    if not resolved_backup_root.is_relative_to(root):
        raise ValueError("La raíz de backups resuelta debe permanecer dentro del workspace.")


def _trusted_bundle(bundle: Path, root: Path) -> Path:
    lexical_backup_root = root / "data/cuaderno/backups"
    backup_root = lexical_backup_root.resolve(strict=True)
    _validate_backup_root(root, backup_root)
    raw = bundle if bundle.is_absolute() else root / bundle
    lexical = Path(os.path.abspath(raw))
    if not lexical.is_relative_to(lexical_backup_root):
        raise ValueError("El bundle debe estar dentro de data/cuaderno/backups.")
    cursor = root
    for part in lexical.relative_to(root).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("La ruta del bundle no puede atravesar enlaces simbólicos.")
    if raw.is_symlink():
        raise ValueError("El bundle no puede ser un enlace simbólico.")
    resolved = raw.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(backup_root):
        raise ValueError("El bundle debe estar dentro de data/cuaderno/backups.")
    return resolved


def _trusted_workspace_file(root: Path, relative: Path, label: str) -> Path:
    raw = root / relative
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} no puede atravesar enlaces simbólicos.")
    _regular_file(raw, label)
    resolved = raw.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} debe permanecer dentro del workspace.")
    return resolved


def _validate_database_fingerprint(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"tables", "sequences"}:
        raise ValueError("Fingerprint de base inválido.")
    tables, sequences = value["tables"], value["sequences"]
    if not isinstance(tables, dict) or not isinstance(sequences, list) or not all(isinstance(row, str) for row in sequences):
        raise ValueError("Fingerprint de tablas/secuencias inválido.")
    for name, row in tables.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("Nombre de tabla inválido en manifest.")
        if (not isinstance(row, dict) or set(row) != {"rows", "content_md5"}
                or type(row["rows"]) is not int or row["rows"] < 0
                or not isinstance(row["content_md5"], str)
                or not re.fullmatch(r"[0-9a-f]{32}", row["content_md5"])):
            raise ValueError("Fingerprint de contenido de tabla inválido.")


def _validate_checkout_source(value: object) -> str:
    if not isinstance(value, dict) or set(value) != {"description", "files", "sha256"}:
        raise ValueError("checkout_source inválido en el manifest.")
    description, files, digest = value["description"], value["files"], value["sha256"]
    if not isinstance(description, str) or not description.strip() or not isinstance(files, dict):
        raise ValueError("checkout_source incompleto en el manifest.")
    for name, file_digest in files.items():
        if not isinstance(name, str) or not isinstance(file_digest, str):
            raise ValueError("Archivo inválido en checkout_source.")
        path = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or path.is_absolute()
                or ".." in path.parts or path.as_posix() != name
                or not re.fullmatch(r"[0-9a-f]{64}", file_digest)):
            raise ValueError("Ruta o hash inválido en checkout_source.")
    expected = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if not isinstance(digest, str) or digest != expected:
        raise ValueError("Hash agregado inválido en checkout_source.")
    smoke_digest = files.get("scripts/cuaderno/restore_smoke.py")
    if not isinstance(smoke_digest, str):
        raise ValueError("checkout_source no registra restore_smoke.py.")
    return smoke_digest


def _read_manifest(bundle: Path) -> dict:
    path = bundle / "manifest.json"
    _regular_file(path, "manifest.json")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest demasiado grande.")
    try:
        def reject_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Clave JSON duplicada: {key}")
                result[key] = value
            return result

        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"JSON no finito: {value}")),
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Manifest JSON inválido.") from exc
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Versión de backup no soportada.")
    required = {
        "source_target", "source_commit", "image_id", "database", "functional", "media",
        "files", "checkout_source",
    }
    if not required.issubset(manifest):
        raise ValueError("Manifest incompleto para rollback.")
    if type(manifest["source_target"]) is not str or manifest["source_target"] not in DATABASE_CONTAINERS:
        raise ValueError("Origen local de backup no reconocido.")
    if type(manifest["source_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]):
        raise ValueError("Commit fuente del backup inválido.")
    _validate_database_fingerprint(manifest["database"])
    _validate_checkout_source(manifest["checkout_source"])
    if not isinstance(manifest["functional"], dict) or manifest["functional"].get("passed") is not True:
        raise ValueError("Fingerprints de base o funcional inválidos.")
    if not isinstance(manifest["media"], dict) or not isinstance(manifest["files"], dict):
        raise ValueError("Hashes del bundle inválidos.")
    image_id = manifest["image_id"]
    if not isinstance(image_id, str) or not IMAGE_PATTERN.fullmatch(image_id):
        raise ValueError("image_id debe ser un SHA-256 local exacto.")
    return manifest


def _container_details(boundary, name: str) -> tuple[str, str]:
    try:
        rows = json.loads(boundary.run(["docker", "inspect", name]))
    except (json.JSONDecodeError, TypeError, IndexError, KeyError) as exc:
        raise ValueError("No se pudo verificar el PostgreSQL local fijado.") from exc
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Inspección ambigua del PostgreSQL local.")
    info = rows[0]
    state = info.get("State")
    if info.get("Name") != f"/{name}" or not isinstance(state, dict) or not state.get("Running") or state.get("Paused"):
        raise ValueError("El PostgreSQL local fijado no está disponible.")
    networks = info.get("NetworkSettings", {}).get("Networks", {})
    if not isinstance(networks, dict) or not networks:
        raise ValueError("El PostgreSQL local no tiene una red verificable.")
    environment = info.get("Config", {}).get("Env", [])
    password_rows = [row.split("=", 1)[1] for row in environment
                     if isinstance(row, str) and row.startswith("POSTGRES_PASSWORD=")]
    if len(password_rows) != 1 or not password_rows[0]:
        raise ValueError("El PostgreSQL local no expone una credencial sintética única al orquestador.")
    return sorted(networks)[0], password_rows[0]


def preflight(bundle: Path, boundary=None, *, root: Path = ROOT) -> RollbackSpec:
    _local_environment()
    boundary = boundary or DockerBoundary()
    root = root.resolve(strict=True)
    login_password = os.environ.get("CUADERNO_DEMO_PASSWORD")
    if not login_password:
        raise ValueError("Define CUADERNO_DEMO_PASSWORD antes del rollback aislado.")
    smoke_path = _trusted_workspace_file(
        root, Path("scripts/cuaderno/restore_smoke.py"), "restore_smoke.py",
    )
    trusted = _trusted_bundle(Path(bundle), root)
    manifest = _read_manifest(trusted)
    smoke_sha256 = _validate_checkout_source(manifest["checkout_source"])
    if _sha256(smoke_path) != smoke_sha256:
        raise ValueError("restore_smoke.py no coincide con checkout_source del backup.")
    for name in ("database.dump", "media.tar"):
        path = trusted / name
        _regular_file(path, name)
        expected = manifest["files"].get(name)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Hash manifest inválido: {name}")
        if _sha256(path) != expected:
            raise ValueError(f"Hash incorrecto: {name}")
    if media_manifest(trusted / "media.tar") != manifest["media"]:
        raise ValueError("Manifiesto de media no coincide.")

    image_id = manifest["image_id"]
    inspected = boundary.run(
        ["docker", "image", "inspect", image_id, "--format", "{{.Id}}"],
    ).decode("utf-8", errors="strict").strip()
    if inspected != image_id:
        raise ValueError("La imagen local no coincide con el image_id del backup.")
    database_container = DATABASE_CONTAINERS[manifest["source_target"]]
    network, password = _container_details(boundary, database_container)
    return RollbackSpec(
        workspace_root=root,
        bundle=trusted,
        manifest=manifest,
        image_id=image_id,
        database_container=database_container,
        database_network=network,
        database_password=password,
        manifest_sha256=_sha256(trusted / "manifest.json"),
        login_password=login_password,
        smoke_path=smoke_path,
        smoke_sha256=smoke_sha256,
    )


def _verify_bundle_unchanged(spec: RollbackSpec) -> None:
    if _sha256(spec.bundle / "manifest.json") != spec.manifest_sha256:
        raise ValueError("El manifest cambió después del preflight.")
    for name in ("database.dump", "media.tar"):
        if _sha256(spec.bundle / name) != spec.manifest["files"][name]:
            raise ValueError(f"{name} cambió después del preflight.")
    if media_manifest(spec.bundle / "media.tar") != spec.manifest["media"]:
        raise ValueError("Media cambió después del preflight.")


def _verify_smoke_unchanged(spec: RollbackSpec) -> None:
    current = _trusted_workspace_file(
        spec.workspace_root, Path("scripts/cuaderno/restore_smoke.py"), "restore_smoke.py",
    )
    if current != spec.smoke_path or _sha256(current) != spec.smoke_sha256:
        raise ValueError("restore_smoke.py cambió después del preflight.")


def _safe_target(root: Path, suffix: str) -> tuple[Path, Path]:
    base = root / "data/cuaderno/rollbacks"
    cursor = root
    for part in base.relative_to(root).parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise ValueError("El destino de rollback no puede atravesar enlaces simbólicos.")
    if not base.resolve(strict=False).is_relative_to(root):
        raise ValueError("Destino de rollback fuera del workspace.")
    target = base / f"rollback-{suffix}"
    return target, target / "media"


def _sql(boundary, container: str, database: str, query: str) -> str:
    return boundary.run([
        "docker", "exec", container, "psql", "-X", "-U", DB_USER, "-d", database,
        "-v", "ON_ERROR_STOP=1", "-At", "-c", query,
    ]).decode("utf-8", errors="strict").strip()


def _database_manifest(boundary, container: str, database: str) -> dict:
    tables = _sql(
        boundary, container, database,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
    ).splitlines()
    queries = []
    for table in tables:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Nombre de tabla restaurada no seguro.")
        literal = "'" + table.replace("'", "''") + "'"
        quoted = '"' + table.replace('"', '""') + '"'
        queries.append(
            f"SELECT json_build_object('table', {literal}, 'rows', count(*), 'content_md5', "
            f"md5(COALESCE(string_agg(row_to_json(t)::text, E'\\n' ORDER BY row_to_json(t)::text), ''))) "
            f"FROM public.{quoted} t;"
        )
    result = {}
    if queries:
        output = boundary.run([
            "docker", "exec", "-i", container, "psql", "-X", "-U", DB_USER,
            "-d", database, "-v", "ON_ERROR_STOP=1", "-At",
        ], data="\n".join(queries).encode()).decode("utf-8", errors="strict")
        for line in output.splitlines():
            row = json.loads(line)
            result[row["table"]] = {"rows": row["rows"], "content_md5": row["content_md5"]}
    sequences = _sql(
        boundary, container, database,
        "SELECT json_build_array(sequencename, last_value)::text FROM pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename",
    )
    return {"tables": result, "sequences": sequences.splitlines()}


def _extract_media(archive_path: Path, destination: Path, *, root: Path | None = None) -> None:
    root = (root or destination.parent).resolve(strict=True)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("El destino media debe ser un directorio regular ya creado.")
    resolved_destination = destination.resolve(strict=True)
    if not resolved_destination.is_relative_to(root):
        raise ValueError("El destino media debe permanecer dentro del destino aislado.")
    seen: set[str] = set()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            raw_name = member.name
            relative = PurePosixPath(raw_name)
            if (not raw_name or "\\" in raw_name or ":" in raw_name
                    or relative.is_absolute() or ".." in relative.parts):
                raise ValueError("Ruta media insegura en el archivo de backup.")
            normalized = relative.as_posix()
            while normalized.startswith("./"):
                normalized = normalized[2:]
            if not normalized or normalized in seen:
                raise ValueError("Ruta media vacía o duplicada en el backup.")
            seen.add(normalized)
            if normalized == ".":
                if member.isdir():
                    continue
                raise ValueError("La raíz del archivo media debe ser un directorio.")
            if member.isdir():
                continue
            if not member.isreg():
                raise ValueError("El backup media solo puede contener archivos regulares.")
            target = destination.joinpath(*PurePosixPath(normalized).parts)
            if not target.resolve(strict=False).is_relative_to(resolved_destination):
                raise ValueError("Ruta media fuera del destino aislado.")
            cursor = resolved_destination
            for part in target.relative_to(destination).parts[:-1]:
                cursor = cursor / part
                if cursor.exists() and cursor.is_symlink():
                    raise ValueError("La extracción media no puede atravesar enlaces simbólicos.")
            target.parent.mkdir(parents=True, exist_ok=True)
            if (not target.parent.resolve(strict=True).is_relative_to(resolved_destination)
                    or target.exists() or target.is_symlink()):
                raise ValueError("Destino media inseguro o duplicado.")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Archivo media sin contenido.")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def _restored_media(directory: Path) -> dict:
    return {
        path.relative_to(directory).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def _functional_smoke(spec: RollbackSpec, boundary, runtime: str, database: str, media: Path, root: Path) -> dict:
    code = (
        "import os,runpy; "
        f"assert os.environ.get('POSTGRES_DB')=={database!r}; "
        f"assert os.environ.get('POSTGRES_HOST')=={spec.database_container!r}; "
        "runpy.run_path('/tmp/cuaderno_restore_smoke.py', run_name='__main__')"
    )
    boundary.run([
        "docker", "create", "--name", runtime, "--network", spec.database_network,
        "-e", "DATABASE_URL=", "-e", "DB_ENGINE=django.db.backends.postgresql",
        "-e", f"POSTGRES_HOST={spec.database_container}", "-e", f"POSTGRES_USER={DB_USER}",
        "-e", f"POSTGRES_PASSWORD={spec.database_password}", "-e", f"POSTGRES_DB={database}",
        "-e", "CUADERNO_ENV=local", "-e", f"CUADERNO_DEMO_PASSWORD={spec.login_password}",
        "-e", "SECRET_KEY=isolated-rollback-synthetic-secret", "-e", "DISABLE_EXTERNAL_CONNECTORS=1",
        "-v", f"{spec.smoke_path}:/tmp/cuaderno_restore_smoke.py:ro",
        "-v", f"{media}:/opt/recipes/mediafiles:ro",
        "--entrypoint", "/opt/recipes/venv/bin/python", spec.image_id, "-c", code,
    ])
    output = boundary.run(["docker", "start", "-a", runtime]).decode("utf-8", errors="replace")
    try:
        rows = json.loads(boundary.run(["docker", "inspect", runtime]))
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise ValueError("No se pudo verificar el runtime antiguo aislado.") from exc
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Inspección ambigua del runtime antiguo aislado.")
    info = rows[0]
    state = info.get("State")
    if (info.get("Name") != f"/{runtime}" or info.get("Image") != spec.image_id
            or not isinstance(state, dict) or state.get("Status") != "exited"
            or type(state.get("ExitCode")) is not int or state["ExitCode"] != 0
            or state.get("OOMKilled") is not False or state.get("Error") != ""):
        raise ValueError("Identidad o salida inválida del runtime antiguo aislado.")
    markers = [line.split("=", 1)[1] for line in output.splitlines()
               if line.startswith("CUADERNO_SMOKE=")]
    if len(markers) != 1:
        raise ValueError("El runtime antiguo debe producir un único fingerprint funcional.")
    try:
        value = json.loads(markers[0])
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Fingerprint funcional del runtime antiguo inválido.") from exc
    if not isinstance(value, dict):
        raise ValueError("Fingerprint funcional del runtime antiguo inválido.")
    return value


def rollback(bundle: Path, *, boundary=None, root: Path = ROOT, suffix: str | None = None) -> dict:
    boundary = boundary or DockerBoundary()
    root = root.resolve(strict=True)
    spec = preflight(Path(bundle), boundary, root=root)
    suffix = suffix or uuid.uuid4().hex[:12]
    if not isinstance(suffix, str) or not SUFFIX_PATTERN.fullmatch(suffix):
        raise ValueError("Sufijo de rollback local inválido.")
    database = f"cuaderno_restore_rollback_{suffix}"
    runtime = f"cuaderno-rollback-{suffix}-web"
    target, media = _safe_target(root, suffix)
    if target.exists():
        raise ValueError("El destino de rollback ya existe; no se sobrescribe.")
    if boundary.container_exists(runtime):
        raise ValueError("El runtime destino de rollback ya existe; no se reutiliza.")
    if _sql(
        boundary, spec.database_container, "postgres",
        f"SELECT 1 FROM pg_database WHERE datname='{database}'",
    ):
        raise ValueError("La base destino de rollback ya existe; no se reutiliza.")
    _verify_bundle_unchanged(spec)

    started = time.monotonic()
    mutated = False
    try:
        target.mkdir(parents=True, exist_ok=False)
        media.mkdir()
        mutated = True
        _sql(
            boundary, spec.database_container, "postgres",
            f"CREATE DATABASE {database} OWNER {DB_USER}",
        )
        boundary.run([
            "docker", "exec", "-i", spec.database_container, "pg_restore", "-U", DB_USER,
            "-d", database, "--exit-on-error", "--no-owner", "--no-acl",
        ], data=(spec.bundle / "database.dump").read_bytes())
        if _database_manifest(boundary, spec.database_container, database) != spec.manifest["database"]:
            raise ValueError("Contenido de la base restaurada distinto del backup.")
        _extract_media(spec.bundle / "media.tar", media, root=root)
        restored_media = _restored_media(media)
        if restored_media != spec.manifest["media"]:
            raise ValueError("Contenido media restaurado distinto del backup.")
        _verify_smoke_unchanged(spec)
        functional = _functional_smoke(spec, boundary, runtime, database, media, root)
        if functional != spec.manifest["functional"]:
            raise ValueError("Fingerprint funcional del runtime antiguo distinto del backup.")
        _verify_bundle_unchanged(spec)
        _verify_smoke_unchanged(spec)
        report_path = target / "rollback-result.json"
        report = {
            "passed": True,
            "mode": "isolated-full-restore-not-live-downgrade",
            "source_bundle": str(spec.bundle.relative_to(root)),
            "source_commit": spec.manifest["source_commit"],
            "image_id": spec.image_id,
            "target_database": database,
            "target_media": str(media.relative_to(root)),
            "runtime_container": runtime,
            "database_dump_sha256": spec.manifest["files"]["database.dump"],
            "media_archive_sha256": spec.manifest["files"]["media.tar"],
            "manifest_sha256": spec.manifest_sha256,
            "tables_verified": len(spec.manifest["database"].get("tables", {})),
            "media_files_verified": len(restored_media),
            "functional": functional,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "retained_for_diagnosis": True,
            "report_path": str(report_path.relative_to(root)),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report
    except Exception as exc:
        if mutated:
            raise RuntimeError(
                f"Rollback aislado falló; se conservan database={database}, "
                f"media={media.relative_to(root)}, runtime={runtime} para diagnóstico: {exc}"
            ) from exc
        raise


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(arguments) != 1:
            raise ValueError("Uso: delivery_rollback.py <bundle-local-antiguo>")
        print(json.dumps(rollback(Path(arguments[0])), ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
