"""Create a fail-closed backup of the fixed cuaderno-prod Compose project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy/cuaderno/compose.production.yml"
PROJECT = "cuaderno-prod"
DB_USER = DB_NAME = "cuaderno_prod"
MEDIA = "/opt/recipes/mediafiles"
RUNTIME_KEYS = frozenset({
    "SCRIPT_NAME", "STATIC_URL", "MEDIA_URL", "SESSION_COOKIE_NAME", "CSRF_COOKIE_NAME",
    "LANGUAGE_COOKIE_NAME", "SESSION_COOKIE_PATH", "CSRF_COOKIE_PATH", "LANGUAGE_COOKIE_PATH",
    "DB_ENGINE", "POSTGRES_DB", "POSTGRES_USER",
})


def runtime_configuration(values: dict) -> dict[str, str]:
    """Validate the nonsecret configuration we can reproduce in an isolated restore."""
    if not isinstance(values, dict) or set(values) - RUNTIME_KEYS:
        raise ValueError("Claves de configuración runtime no admitidas.")
    if any(not isinstance(value, str) for value in values.values()):
        raise ValueError("Valor de configuración runtime no admitido.")
    prefix = values.get("SCRIPT_NAME", "")
    if prefix and (not re.fullmatch(r"(?:/[A-Za-z0-9_.-]+)+", prefix)
                   or any(part in (".", "..") for part in prefix.split("/"))):
        raise ValueError("El prefijo SCRIPT_NAME no es seguro.")
    result = {"SCRIPT_NAME": prefix}
    for key, suffix in (("STATIC_URL", "static/"), ("MEDIA_URL", "media/")):
        expected = f"{prefix}/{suffix}"
        if values.get(key, expected) != expected:
            raise ValueError(f"La configuración {key} debe ser una ruta local del prefijo.")
        result[key] = expected
    for stem, default in (("SESSION", "sessionid"), ("CSRF", "csrftoken"), ("LANGUAGE", "django_language")):
        name_key, path_key = f"{stem}_COOKIE_NAME", f"{stem}_COOKIE_PATH"
        name = values.get(name_key, default)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
            raise ValueError("Nombre de cookie no seguro en la configuración.")
        if values.get(path_key, f"{prefix}/") != f"{prefix}/":
            raise ValueError("La ruta de cookie debe coincidir exactamente con el prefijo.")
        result[name_key], result[path_key] = name, f"{prefix}/"
    if len({result[f"{stem}_COOKIE_NAME"] for stem in ("SESSION", "CSRF", "LANGUAGE")}) != 3:
        raise ValueError("Los nombres de cookie deben ser distintos.")
    if values.get("DB_ENGINE", "django.db.backends.postgresql") != "django.db.backends.postgresql":
        raise ValueError("La configuración de base de datos debe usar PostgreSQL.")
    result["DB_ENGINE"] = "django.db.backends.postgresql"
    for key, default in (("POSTGRES_DB", DB_NAME), ("POSTGRES_USER", DB_USER)):
        value = values.get(key, default)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
            raise ValueError("Identificador no seguro en la configuración de base de datos.")
        result[key] = value
    return result


def container_environment(info: dict) -> dict[str, str]:
    # Read only allowlisted keys. Credentials must never enter the manifest or errors.
    result = {}
    for entry in info.get("Config", {}).get("Env", []):
        key, separator, value = entry.partition("=")
        if separator and key in RUNTIME_KEYS:
            if key in result:
                raise ValueError("Configuración runtime duplicada.")
            result[key] = value
    return result


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


def database_manifest(boundary: DockerBoundary, env_file: Path, *, db_user: str = DB_USER,
                      db_name: str = DB_NAME) -> dict:
    psql = compose(env_file, "exec", "-T", "db", "psql", "-X", "-U", db_user, "-d", db_name,
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
        env_file, "exec", "-T", "db", "psql", "-X", "-U", db_user, "-d", db_name,
        "-v", "ON_ERROR_STOP=1", "-At", "-c",
        "SELECT app||':'||name||':'||applied::text FROM django_migrations ORDER BY app,name",
    )).decode().splitlines()
    version = boundary.run(compose(env_file, "exec", "-T", "db", "psql", "-X", "-U", db_user,
                                   "-d", db_name, "-At", "-c", "SHOW server_version")).decode().strip()
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
                  check_windows_acl: bool = False, include_env: bool = False) -> Path:
    boundary = boundary or DockerBoundary()
    env_file = validate_private_file(env_file, check_windows_acl=check_windows_acl)
    parent = validate_parent(parent)
    db_id, db_info = _container(boundary, env_file, "db")
    web_id, web_info = _container(boundary, env_file, "web")
    runtime = runtime_configuration(container_environment(web_info))
    db_config = runtime_configuration({key: value for key, value in container_environment(db_info).items()
                                       if key in ("POSTGRES_DB", "POSTGRES_USER")})
    if any(runtime[key] != db_config[key] for key in ("POSTGRES_DB", "POSTGRES_USER")):
        raise ValueError("La configuración de base de datos web/db no coincide.")
    db_user, db_name = runtime["POSTGRES_USER"], runtime["POSTGRES_DB"]
    if not db_info["State"]["Running"]:
        raise ValueError("La base cuaderno-prod no está en ejecución.")
    bundle = parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12])
    bundle.mkdir(mode=0o700, exist_ok=False)
    if include_env:
        descriptor = os.open(bundle / "environment.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as destination, env_file.open("rb") as source:
            shutil.copyfileobj(source, destination)
    web_running = bool(web_info["State"]["Running"])
    try:
        if web_running:
            boundary.run(compose(env_file, "stop", "web"))
        clients = boundary.run(compose(
            env_file, "exec", "-T", "db", "psql", "-X", "-U", db_user, "-d", db_name,
            "-v", "ON_ERROR_STOP=1", "-At", "-c",
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
            "AND pid<>pg_backend_pid() AND backend_type='client backend'",
        )).decode().strip()
        if clients != "0":
            raise ValueError("Hay clientes externos conectados; no se acepta un backup operativo ambiguo.")
        _run_to_new_file(boundary, compose(
            env_file, "exec", "-T", "db", "pg_dump", "-U", db_user, "-d", db_name,
            "-Fc", "--no-owner", "--no-acl",
        ), bundle / "database.dump")
        _run_to_new_file(boundary, ["docker", "cp", f"{web_id}:{MEDIA}/.", "-"], bundle / "media.tar")
        database = database_manifest(boundary, env_file, db_user=db_user, db_name=db_name)
    finally:
        if web_running:
            boundary.run(compose(env_file, "up", "-d", "--no-deps", "web"))

    manifest = {
        "schema_version": 3,
        "kind": "cuaderno-production-backup",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "compose_project": PROJECT,
        "database": database,
        "media": media_manifest(bundle / "media.tar"),
        "files": {name: sha256(bundle / name) for name in
                  ("database.dump", "media.tar", *(["environment.env"] if include_env else []))},
        "runtime": {
            "web_image_id": web_info["Image"], "database_image_id": db_info["Image"],
            "web_container_id": web_id, "database_container_id": db_id,
        },
        "configuration": {
            "compose_sha256": sha256(COMPOSE), "env_file_sha256": sha256(env_file),
            "secrets_recorded": include_env, "writers_stopped": web_running,
            "runtime_environment": runtime,
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
    parser.add_argument("--include-env", action="store_true", help="Incluir copia privada 0600 del env protegido.")
    args = parser.parse_args()
    try:
        print(create_backup(args.env_file, args.destination_parent,
                            check_windows_acl=args.check_windows_acl, include_env=args.include_env))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
