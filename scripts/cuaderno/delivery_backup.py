"""Consistent backup of the explicitly named, isolated Cuaderno demo containers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
_TARGETS = {
    "baseline": ("cuaderno-g0-t002-db", "cuaderno-g0-t002-web"),
    "release": ("cuaderno-release-db", "cuaderno-release-web"),
}
_target = os.environ.get("CUADERNO_BACKUP_TARGET", "baseline")
if _target not in _TARGETS:
    raise ValueError("Destino permitido: baseline o release local, no nombres arbitrarios.")
CONTAINER, WEB = _TARGETS[_target]
DB = USER = "cuaderno_demo"
MEDIA = "/opt/recipes/mediafiles"


def run(*args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout


def validate_local() -> None:
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}:
        raise ValueError("Exige CUADERNO_ENV=local/test/development; solo contenedores demo fijados.")
    for name in (CONTAINER, WEB):
        info = json.loads(run("docker", "inspect", name))[0]
        if info["Name"] != f"/{name}" or not info["State"]["Running"] or info["State"]["Paused"]:
            raise ValueError(f"Contenedor demo no disponible: {name}")
        if name == WEB:
            bindings = info["HostConfig"]["PortBindings"] or {}
            if not bindings or any(b["HostIp"] != "127.0.0.1" for rows in bindings.values() for b in rows):
                raise ValueError("La web demo debe estar publicada solo en loopback.")


def sql(database: str, query: str) -> str:
    return run("docker", "exec", CONTAINER, "psql", "-X", "-U", USER, "-d", database,
               "-v", "ON_ERROR_STOP=1", "-At", "-c", query).decode().strip()


def database_manifest(database: str) -> dict:
    tables = sql(database, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
    queries = []
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        literal = "'" + table.replace("'", "''") + "'"
        queries.append(
            f"SELECT json_build_object('table', {literal}, 'rows', count(*), 'content_md5', "
            f"md5(COALESCE(string_agg(row_to_json(t)::text, E'\\n' ORDER BY row_to_json(t)::text), ''))) "
            f"FROM public.{quoted} t;"
        )
    # stdin avoids Windows' argv length limit and hundreds of Docker roundtrips.
    output = run("docker", "exec", "-i", CONTAINER, "psql", "-X", "-U", USER, "-d", database,
                 "-v", "ON_ERROR_STOP=1", "-At", data="\n".join(queries).encode()).decode()
    result = {}
    for line in output.splitlines():
        row = json.loads(line)
        result[row["table"]] = {"rows": row["rows"], "content_md5": row["content_md5"]}
    sequences = sql(database, "SELECT json_build_array(sequencename, last_value)::text FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")
    return {"tables": result, "sequences": sequences.splitlines()}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_manifest() -> dict:
    names = run("git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    files = {}
    for name in sorted(set(names) - {""}):
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Fuente enlazada fuera del proyecto: no se incluye en el manifiesto.")
        if path.is_file():
            files[name] = sha256(path)
    return {"description": "Checkout local (incluye untracked no ignorados); image_id identifica el runtime por separado.",
            "files": files, "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def functional_manifest(database: str) -> dict:
    password = os.environ.get("CUADERNO_DEMO_PASSWORD")
    if not password:
        raise ValueError("Define CUADERNO_DEMO_PASSWORD para probar login del backup/restore local.")
    run("docker", "cp", str(ROOT / "scripts/cuaderno/restore_smoke.py"), f"{WEB}:/tmp/cuaderno_restore_smoke.py")
    result = run("docker", "exec", "-e", "PYTHONPATH=/opt/recipes", "-e", "CUADERNO_ENV=local", "-e", f"POSTGRES_DB={database}",
                 "-e", f"CUADERNO_DEMO_PASSWORD={password}", WEB,
                 "/opt/recipes/venv/bin/python", "/tmp/cuaderno_restore_smoke.py").decode()
    for line in result.splitlines():
        if line.startswith("CUADERNO_SMOKE="):
            return json.loads(line.split("=", 1)[1])
    raise ValueError("Smoke funcional no produjo un resultado comprobable.")


def media_manifest(archive: Path) -> dict:
    result = {}
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name:
                raise ValueError("Ruta insegura en media.")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Media debe contener archivos regulares, sin enlaces ni dispositivos.")
            name = path.as_posix()
            if name in result:
                raise ValueError("Ruta media duplicada.")
            with source.extractfile(member) as stream:
                result[name] = {"bytes": member.size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    return result


def create_backup(destination: Path | None = None) -> Path:
    validate_local()
    destination = destination or ROOT / "data/cuaderno/backups" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    commit = run("git", "-C", str(ROOT), "rev-parse", "HEAD").decode().strip()
    image_id = run("docker", "inspect", "-f", "{{.Image}}", WEB).decode().strip()
    paused = False
    started = time.monotonic()
    try:
        run("docker", "pause", WEB)
        paused = True
        info = json.loads(run("docker", "inspect", WEB))[0]
        web_addresses = [network["IPAddress"] for network in info["NetworkSettings"]["Networks"].values()]
        address_list = ",".join("'" + address.replace("'", "''") + "'" for address in web_addresses)
        unexpected = sql(DB, f"SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid() "
                         f"AND backend_type='client backend' AND (client_addr IS NULL OR host(client_addr) NOT IN ({address_list}))")
        if unexpected != "0":
            raise ValueError("Hay escritores/clientes externos a la web demo; backup abortado y web reanudada.")
        in_flight = sql(DB, "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid() "
                        "AND backend_type='client backend' AND state <> 'idle'")
        if in_flight != "0":
            raise ValueError("Hay transacciones en curso; backup abortado y web reanudada. Reintenta cuando esté inactiva.")
        (destination / "database.dump").write_bytes(run("docker", "exec", CONTAINER, "pg_dump", "-U", USER, "-d", DB, "-Fc", "--no-owner", "--no-acl"))
        (destination / "media.tar").write_bytes(run("docker", "cp", f"{WEB}:{MEDIA}/.", "-"))
        snapshot = database_manifest(DB)
    finally:
        if paused:
            run("docker", "unpause", WEB)
    pause_seconds = round(time.monotonic() - started, 3)
    # Validate the immutable dump, NOT the live source before/after its pause.
    # This avoids racing another write against the functional fingerprint.
    probe = "cuaderno_restore_probe_" + uuid.uuid4().hex
    sql("postgres", f"CREATE DATABASE {probe} OWNER {USER}")
    run("docker", "exec", "-i", CONTAINER, "pg_restore", "-U", USER, "-d", probe,
        "--exit-on-error", "--no-owner", "--no-acl", data=(destination / "database.dump").read_bytes())
    if database_manifest(probe) != snapshot:
        raise ValueError("El dump no reproduce el snapshot consistente; copia no aceptada.")
    functional = functional_manifest(probe)
    manifest = {
        "schema_version": 1, "utc": datetime.now(timezone.utc).isoformat(), "source_database": DB,
        "source_commit": commit, "image_id": image_id,
        "source_target": _target, "functional": functional,
        "functional_probe_database": probe, "checkout_source": source_manifest(),
        "tracked_diff_sha256": hashlib.sha256(run("git", "-C", str(ROOT), "diff", "HEAD", "--")).hexdigest(),
        "consistency": "Local web paused; verified no external clients or in-flight transactions before snapshot.",
        "write_pause_seconds": pause_seconds, "database": snapshot,
        "media": media_manifest(destination / "media.tar"),
        "files": {name: sha256(destination / name) for name in ("database.dump", "media.tar")},
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination
