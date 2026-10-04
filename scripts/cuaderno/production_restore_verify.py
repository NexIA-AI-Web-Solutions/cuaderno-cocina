"""Restore a production bundle only into a new isolated verification namespace."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import uuid

try:
    from .production_backup import DockerBoundary, database_manifest, media_manifest, sha256
except ImportError:
    from production_backup import DockerBoundary, database_manifest, media_manifest, sha256


PG16_IMAGE = "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


def trusted_bundle(bundle: Path) -> tuple[Path, dict]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("El bundle debe ser un directorio local regular, sin enlaces.")
    bundle = bundle.resolve(strict=True)
    for name in ("manifest.json", "database.dump", "media.tar"):
        path = bundle / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Falta un archivo regular del bundle: {name}")
    manifest_path = bundle / "manifest.json"
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("El manifest supera el límite admitido.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Clave JSON duplicada: {key}")
            result[key] = value
        return result
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if (manifest.get("schema_version"), manifest.get("kind"), manifest.get("compose_project")) != (
        2, "cuaderno-production-backup", "cuaderno-prod",
    ):
        raise ValueError("El manifest no es un backup de producción Cuaderno compatible.")
    for name in ("database.dump", "media.tar"):
        expected = manifest.get("files", {}).get(name)
        if (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or sha256(bundle / name) != expected):
            raise ValueError(f"Hash incorrecto: {name}")
    if media_manifest(bundle / "media.tar") != manifest.get("media"):
        raise ValueError("El contenido media no coincide con su manifest.")
    return bundle, manifest


class RestoreBoundary(DockerBoundary):
    def exists(self, kind: str, name: str) -> bool:
        result = subprocess.run(
            ["docker", kind, "inspect", name], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    def run_from_file(self, argv: list[str], source: Path) -> bytes:
        with source.open("rb") as stream:
            result = subprocess.run(argv, stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker falló ({result.returncode}): {result.stderr.decode(errors='replace')[-2000:]}")
        return result.stdout


def _run_from_file(boundary: RestoreBoundary, argv: list[str], source: Path) -> bytes:
    method = getattr(boundary, "run_from_file", None)
    if method is not None:
        return method(argv, source)
    return boundary.run(argv, data=source.read_bytes())  # Small in-memory unit-test boundary.


def _assert_new(boundary: RestoreBoundary, namespace: str) -> None:
    for kind, suffixes in (("container", ("db", "web")), ("network", ("network",)),
                           ("volume", ("database", "media"))):
        for suffix in suffixes:
            if boundary.exists(kind, f"{namespace}-{suffix}"):
                raise ValueError("Colisión en el namespace nuevo de restauración.")


def _write_env(values: dict[str, str]) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="cuaderno-restore-", suffix=".env", text=True)
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("Valor interno de entorno inválido.")
                stream.write(f"{key}={value}\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _db_manifest(boundary: RestoreBoundary, container: str) -> dict:
    psql = ["docker", "exec", "-i", container, "psql", "-X", "-U", "cuaderno_prod",
            "-d", "cuaderno_prod", "-v", "ON_ERROR_STOP=1", "-At"]
    names = boundary.run([
        *psql, "-c", "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
    ]).decode().splitlines()
    queries = []
    for table in names:
        quoted = '"' + table.replace('"', '""') + '"'
        literal = "'" + table.replace("'", "''") + "'"
        queries.append(
            f"SELECT json_build_object('table',{literal},'rows',count(*),'content_md5',"
            f"md5(COALESCE(string_agg(row_to_json(t)::text,E'\\n' ORDER BY row_to_json(t)::text),''))) "
            f"FROM public.{quoted} t;"
        )
    output = boundary.run(psql, data="\n".join(queries).encode()).decode()
    tables = {}
    for line in output.splitlines():
        row = json.loads(line)
        tables[row["table"]] = {"rows": row["rows"], "content_md5": row["content_md5"]}
    migrations = boundary.run([
        "docker", "exec", container, "psql", "-X", "-U", "cuaderno_prod", "-d", "cuaderno_prod",
        "-v", "ON_ERROR_STOP=1", "-At", "-c",
        "SELECT app||':'||name||':'||applied::text FROM django_migrations ORDER BY app,name",
    ]).decode().splitlines()
    version = boundary.run(["docker", "exec", container, "psql", "-X", "-U", "cuaderno_prod",
                            "-d", "cuaderno_prod", "-At", "-c", "SHOW server_version"]).decode().strip()
    return {"tables": tables, "migrations": migrations, "postgres_version": version}


def verify(bundle: Path, *, boundary: RestoreBoundary | None = None,
           runtime_image: str | None = None, report_path: Path | None = None) -> dict:
    boundary = boundary or RestoreBoundary()
    bundle, manifest = trusted_bundle(bundle)
    namespace = "cuaderno-restore-" + uuid.uuid4().hex[:12]
    _assert_new(boundary, namespace)
    network, database_volume, media_volume = (
        f"{namespace}-network", f"{namespace}-database", f"{namespace}-media",
    )
    label = f"io.cuaderno.restore={namespace}"
    boundary.run(["docker", "network", "create", "--internal", "--label", label, network])
    boundary.run(["docker", "volume", "create", "--label", label, database_volume])
    boundary.run(["docker", "volume", "create", "--label", label, media_volume])

    password = secrets.token_urlsafe(36)
    db_env = _write_env({"POSTGRES_DB": "cuaderno_prod", "POSTGRES_USER": "cuaderno_prod",
                         "POSTGRES_PASSWORD": password})
    db = f"{namespace}-db"
    try:
        boundary.run([
            "docker", "run", "-d", "--name", db, "--network", network, "--network-alias", "db",
            "--label", label, "--env-file", str(db_env), "-v", f"{database_volume}:/var/lib/postgresql/data",
            PG16_IMAGE,
        ])
    finally:
        db_env.unlink(missing_ok=True)
    boundary.run(["docker", "exec", db, "sh", "-ec",
                  "until pg_isready -U cuaderno_prod -d cuaderno_prod; do sleep 1; done"])
    _run_from_file(boundary, ["docker", "exec", "-i", db, "pg_restore", "-U", "cuaderno_prod", "-d", "cuaderno_prod",
                               "--exit-on-error", "--no-owner", "--no-acl"], bundle / "database.dump")
    restored_database = _db_manifest(boundary, db)
    if restored_database != manifest.get("database"):
        raise ValueError(f"La base restaurada no coincide; se conserva {namespace} para diagnóstico.")

    _run_from_file(boundary, [
        "docker", "run", "--rm", "-i", "--network", "none", "--label", label,
        "-v", f"{media_volume}:/media", PG16_IMAGE, "tar", "-x", "-C", "/media", "-f", "-",
    ], bundle / "media.tar")
    descriptor, restored_name = tempfile.mkstemp(prefix="cuaderno-media-verify-", suffix=".tar")
    os.close(descriptor)
    restored_path = Path(restored_name)
    try:
        restored_path.unlink()
        command = [
            "docker", "run", "--rm", "--network", "none", "--label", label,
            "-v", f"{media_volume}:/media:ro", PG16_IMAGE, "tar", "-c", "-C", "/media", ".",
        ]
        method = getattr(boundary, "run_to_file", None)
        if method is not None:
            method(command, restored_path)
        else:
            restored_path.write_bytes(boundary.run(command))
        if media_manifest(restored_path) != manifest["media"]:
            raise ValueError(f"Media restaurada no coincide; se conserva {namespace} para diagnóstico.")
    finally:
        restored_path.unlink(missing_ok=True)

    candidate = None
    if runtime_image:
        actual = boundary.run(["docker", "image", "inspect", "-f", "{{.Id}}", runtime_image]).decode().strip()
        if not IMAGE_ID.fullmatch(actual):
            raise ValueError("La imagen candidata no resuelve a un Image ID local inmutable.")
        boundary.run(["docker", "run", "--rm", "--network", "none", "--label", label,
                      "-v", f"{media_volume}:/media", PG16_IMAGE, "chown", "-R", "10001:10001", "/media"])
        runtime_env = _write_env({
            "DJANGO_SETTINGS_MODULE": "recipes.cuaderno_production_settings",
            "SECRET_KEY": secrets.token_urlsafe(48), "DB_ENGINE": "django.db.backends.postgresql",
            "POSTGRES_HOST": "db", "POSTGRES_PORT": "5432", "POSTGRES_DB": "cuaderno_prod",
            "POSTGRES_USER": "cuaderno_prod", "POSTGRES_PASSWORD": password,
            "ALLOWED_HOSTS": "127.0.0.1,localhost", "CSRF_TRUSTED_ORIGINS": "https://127.0.0.1",
            "ENABLE_SIGNUP": "0", "DEBUG": "0", "GUNICORN_MEDIA": "0",
        })
        web = f"{namespace}-web"
        try:
            boundary.run(["docker", "run", "-d", "--name", web, "--network", network, "--label", label,
                          "--env-file", str(runtime_env), "-v", f"{media_volume}:/opt/recipes/mediafiles", actual])
        finally:
            runtime_env.unlink(missing_ok=True)
        # ``docker run -d`` only confirms that the container was created.  Migrations and
        # the supervised web process may still be starting, so use a bounded poll inside
        # the new container.  Any timeout deliberately leaves the isolated resources in
        # place, just like the database/media comparison failures above.
        smoke = (
            "import json,time,urllib.request\n"
            "last=None\n"
            "for attempt in range(120):\n"
            " try:\n"
            "  with urllib.request.urlopen('http://127.0.0.1/health/ready/',timeout=10) as response:\n"
            "   if json.load(response).get('ready') is True: break\n"
            " except Exception as exc:\n"
            "  last=exc\n"
            " if attempt == 119: raise SystemExit('readiness timeout: '+type(last).__name__)\n"
            " time.sleep(2)\n"
        )
        boundary.run(["docker", "exec", web, "/opt/recipes/venv/bin/python", "-c", smoke])
        candidate = {"container": web, "image_id": actual, "published_ports": False}

    report = {
        "passed": True, "namespace": namespace, "database_container": db,
        "database_volume": database_volume, "media_volume": media_volume, "network": network,
        "network_internal": True, "published_ports": False, "runtime_candidate": candidate,
        "source_commit": manifest.get("source_commit"), "database_dump_sha256": manifest["files"]["database.dump"],
        "resources_retained_for_review": True,
    }
    report_path = report_path or bundle.parent / f"{bundle.name}-{namespace}-verify.json"
    if report_path.exists() or report_path.is_symlink():
        raise ValueError("El informe de verificación debe usar una ruta nueva.")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--runtime-image")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.bundle, runtime_image=args.runtime_image, report_path=args.report), indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
