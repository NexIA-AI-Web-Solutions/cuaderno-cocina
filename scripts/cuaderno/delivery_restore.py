"""Restore a trusted local bundle to a NEW database and NEW media directory."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tarfile
import time
import uuid
from delivery_backup import ROOT, CONTAINER, USER, create_backup, database_manifest, functional_manifest, media_manifest, run, sha256, sql, validate_local


def restore(bundle: Path) -> dict:
    validate_local()
    started = time.monotonic()
    bundle = bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Versión de backup no soportada.")
    for name in ("database.dump", "media.tar"):
        if sha256(bundle / name) != manifest["files"][name]:
            raise ValueError(f"Hash incorrecto: {name}")
    if media_manifest(bundle / "media.tar") != manifest["media"]:
        raise ValueError("Manifiesto media no coincide.")
    target = "cuaderno_restore_" + uuid.uuid4().hex
    directory = ROOT / "data/cuaderno/restores" / target
    directory.mkdir(parents=True, exist_ok=False)
    sql("postgres", f"CREATE DATABASE {target} OWNER {USER}")
    run("docker", "exec", "-i", CONTAINER, "pg_restore", "-U", USER, "-d", target,
        "--exit-on-error", "--no-owner", "--no-acl", data=(bundle / "database.dump").read_bytes())
    if database_manifest(target) != manifest["database"]:
        raise ValueError(f"Contenido de DB restaurada distinto: {target}; se conserva para diagnóstico.")
    with tarfile.open(bundle / "media.tar") as archive:
        archive.extractall(directory, filter="data")
    files = {path.relative_to(directory).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256(path)}
             for path in directory.rglob("*") if path.is_file()}
    if files != manifest["media"]:
        raise ValueError("Hashes de archivos restaurados distintos.")
    functional = functional_manifest(target)
    if functional != manifest.get("functional"):
        raise ValueError("Login/permisos/costes/saldos restaurados distintos del origen.")
    report = {"passed": True, "target_database": target, "target_media": str(directory.relative_to(ROOT)),
              "tables_verified": len(manifest["database"]["tables"]), "rows_verified": sum(t["rows"] for t in manifest["database"]["tables"].values()),
              "sequences_verified": len(manifest["database"]["sequences"]), "media_files_verified": len(files),
              "elapsed_seconds": round(time.monotonic() - started, 3), "backup_pause_seconds": manifest["write_pause_seconds"],
              "source_commit": manifest["source_commit"], "database_dump_sha256": manifest["files"]["database.dump"]}
    report["functional"] = functional
    (bundle / "restore-result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("Uso: delivery_restore.py <bundle-local> | --round-trip")
        bundle = create_backup() if sys.argv[1] == "--round-trip" else Path(sys.argv[1])
        print(json.dumps(restore(bundle), indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
