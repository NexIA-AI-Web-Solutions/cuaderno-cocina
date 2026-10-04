"""Create a fail-closed backup of the fixed cuaderno-prod Compose project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy/cuaderno/compose.production.yml"
PROJECT = "cuaderno-prod"
DB_USER = DB_NAME = "cuaderno_prod"
MEDIA = "/opt/recipes/mediafiles"


class DockerBoundary:
    def run(self, argv: list[str], *, data: bytes | None = None) -> bytes:
        result = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker falló ({result.returncode}): {result.stderr.decode(errors='replace')[-2000:]}")
        return result.stdout

    def run_to_file(self, argv: list[str], destination: Path) -> None:
        with destination.open("xb") as stream:
            result = subprocess.run(argv, stdout=stream, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker falló ({result.returncode}): {result.stderr.decode(errors='replace')[-2000:]}")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_private_file(path: Path, *, check_windows_acl: bool = False) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError("El env-file debe ser un archivo regular existente, sin enlaces.")
    path = path.resolve(strict=True)
    if os.name != "nt":
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("El env-file debe pertenecer al operador y tener modo 0600 en Linux.")
    elif check_windows_acl:
        script = (
            "$a=Get-Acl -LiteralPath $args[0]; $bad=$a.Access | Where-Object {"
            "$_.AccessControlType -eq 'Allow' -and ($_.IdentityReference.Value -match "
            "'Everyone|Authenticated Users|\\\\Users$') -and "
            "($_.FileSystemRights.ToString() -match 'FullControl|Modify|Write')};"
            "if($bad){exit 7}"
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script, str(path)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise ValueError("La ACL de Windows concede escritura amplia o no pudo verificarse.")
    return path


def validate_parent(parent: Path) -> Path:
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("El directorio padre de backups debe existir y no ser un enlace.")
    parent = parent.resolve(strict=True)
    if os.name == "nt":
        if str(parent).startswith("\\\\"):
            raise ValueError("El destino debe ser un disco local del operador, no una ruta UNC.")
    else:
        stat = parent.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o022:
            raise ValueError("El padre debe pertenecer al operador y no permitir escritura de grupo/otros.")
    return parent


def media_manifest(archive: Path) -> dict:
    result = {}
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name:
                raise ValueError("Ruta insegura en el archivo de media.")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Media solo admite archivos regulares.")
            normalized = name.as_posix().removeprefix("./")
            if not normalized or normalized in result:
                raise ValueError("Ruta media vacía o duplicada.")
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("No se pudo leer un archivo de media.")
            result[normalized] = {"bytes": member.size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    return result


def compose(env_file: Path, *args: str) -> list[str]:
    return ["docker", "compose", "--project-name", PROJECT, "--env-file", str(env_file),
            "-f", str(COMPOSE), *args]


def database_manifest(boundary: DockerBoundary, env_file: Path) -> dict:
    psql = compose(env_file, "exec", "-T", "db", "psql", "-X", "-U", DB_USER, "-d", DB_NAME,
                   "-v", "ON_ERROR_STOP=1", "-At")
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
    tables_raw = boundary.run(psql, data="\n".join(queries).encode()).decode()
    tables = {}
    for line in tables_raw.splitlines():
        row = json.loads(line)
        tables[row["table"]] = {"rows": row["rows"], "content_md5": row["content_md5"]}
    migrations = boundary.run(compose(
        env_file, "exec", "-T", "db", "psql", "-X", "-U", DB_USER, "-d", DB_NAME,
        "-v", "ON_ERROR_STOP=1", "-At", "-c",
        "SELECT app||':'||name||':'||applied::text FROM django_migrations ORDER BY app,name",
    )).decode().splitlines()
    version = boundary.run(compose(env_file, "exec", "-T", "db", "psql", "-X", "-U", DB_USER,
                                   "-d", DB_NAME, "-At", "-c", "SHOW server_version")).decode().strip()
    return {"tables": tables, "migrations": migrations, "postgres_version": version}


def _container(boundary: DockerBoundary, env_file: Path, service: str) -> tuple[str, dict]:
    identifier = boundary.run(compose(env_file, "ps", "-q", service)).decode().strip()
    if not identifier or "\n" in identifier:
        raise ValueError(f"El servicio {service} debe resolver a un único contenedor.")
    info = json.loads(boundary.run(["docker", "inspect", identifier]))[0]
    labels = info.get("Config", {}).get("Labels", {})
    if labels.get("com.docker.compose.project") != PROJECT or labels.get("com.docker.compose.service") != service:
        raise ValueError(f"El contenedor de {service} no pertenece al proyecto fijo {PROJECT}.")
    return identifier, info


def _run_to_new_file(boundary: DockerBoundary, argv: list[str], destination: Path) -> None:
    method = getattr(boundary, "run_to_file", None)
    if method is not None:
        method(argv, destination)
    else:  # Small in-memory unit-test boundary.
        destination.write_bytes(boundary.run(argv))


def create_backup(env_file: Path, parent: Path, *, boundary: DockerBoundary | None = None,
                  check_windows_acl: bool = False) -> Path:
    boundary = boundary or DockerBoundary()
    env_file = validate_private_file(env_file, check_windows_acl=check_windows_acl)
    parent = validate_parent(parent)
    bundle = parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12])
    bundle.mkdir(mode=0o700, exist_ok=False)
    db_id, db_info = _container(boundary, env_file, "db")
    web_id, web_info = _container(boundary, env_file, "web")
    if not db_info["State"]["Running"]:
        raise ValueError("La base cuaderno-prod no está en ejecución.")
    web_running = bool(web_info["State"]["Running"])
    try:
        if web_running:
            boundary.run(compose(env_file, "stop", "web"))
        clients = boundary.run(compose(
            env_file, "exec", "-T", "db", "psql", "-X", "-U", DB_USER, "-d", DB_NAME,
            "-v", "ON_ERROR_STOP=1", "-At", "-c",
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid() AND backend_type='client backend'",
        )).decode().strip()
        if clients != "0":
            raise ValueError("Hay clientes externos conectados; no se acepta un backup operativo ambiguo.")
        _run_to_new_file(boundary, compose(
            env_file, "exec", "-T", "db", "pg_dump", "-U", DB_USER, "-d", DB_NAME,
            "-Fc", "--no-owner", "--no-acl",
        ), bundle / "database.dump")
        _run_to_new_file(boundary, ["docker", "cp", f"{web_id}:{MEDIA}/.", "-"], bundle / "media.tar")
        database = database_manifest(boundary, env_file)
    finally:
        if web_running:
            boundary.run(compose(env_file, "up", "-d", "--no-deps", "web"))

    manifest = {
        "schema_version": 2,
        "kind": "cuaderno-production-backup",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "compose_project": PROJECT,
        "database": database,
        "media": media_manifest(bundle / "media.tar"),
        "files": {name: sha256(bundle / name) for name in ("database.dump", "media.tar")},
        "runtime": {
            "web_image_id": web_info["Image"], "database_image_id": db_info["Image"],
            "web_container_id": web_id, "database_container_id": db_id,
        },
        "configuration": {
            "compose_sha256": sha256(COMPOSE), "env_file_sha256": sha256(env_file),
            "secrets_recorded": False, "writers_stopped": web_running,
        },
        "source_commit": boundary.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip(),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--destination-parent", required=True, type=Path)
    parser.add_argument("--check-windows-acl", action="store_true")
    args = parser.parse_args()
    try:
        print(create_backup(args.env_file, args.destination_parent,
                            check_windows_acl=args.check_windows_acl))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
