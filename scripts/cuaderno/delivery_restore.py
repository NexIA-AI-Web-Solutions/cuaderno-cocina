"""Restore a trusted local bundle to a NEW database and NEW media directory."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tarfile
import time
import uuid
try:
    from .delivery_backup import ROOT, CONTAINER, USER, create_backup, database_manifest, functional_manifest, media_manifest, run, sha256, sql, validate_local
except ImportError:  # Direct invocation: python scripts/cuaderno/delivery_restore.py
    from delivery_backup import ROOT, CONTAINER, USER, create_backup, database_manifest, functional_manifest, media_manifest, run, sha256, sql, validate_local


def trusted_bundle(bundle: Path, *, root: Path = ROOT) -> Path:
    """Resolve a local bundle without allowing restore/report writes outside its backup root."""
    root = root.resolve(strict=True)
    backup_root = (root / "data/cuaderno/backups").resolve(strict=True)
    if not backup_root.is_relative_to(root):
        raise ValueError("La raíz de backups debe permanecer dentro del workspace.")
    lexical = bundle if bundle.is_absolute() else root / bundle
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise ValueError("El bundle local no existe o no es accesible.") from exc
    if not resolved.is_dir() or not resolved.is_relative_to(backup_root):
        raise ValueError("El bundle debe estar dentro de data/cuaderno/backups.")
    current = lexical.absolute()
    while current != backup_root:
        if current.is_symlink() or bool(getattr(current, "is_junction", lambda: False)()):
            raise ValueError("El bundle no puede atravesar enlaces simbólicos o junctions.")
        parent = current.parent
        if parent == current:
            raise ValueError("No se pudo verificar la ruta del bundle.")
        current = parent
    for name in ("manifest.json", "database.dump", "media.tar"):
        candidate = resolved / name
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"Fichero de bundle ausente o inseguro: {name}")
    return resolved


def restore(bundle: Path, *, root: Path = ROOT) -> dict:
    started = time.monotonic()
    bundle = trusted_bundle(bundle, root=root)
    validate_local()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Versión de backup no soportada.")
    for name in ("database.dump", "media.tar"):
        if sha256(bundle / name) != manifest["files"][name]:
            raise ValueError(f"Hash incorrecto: {name}")
    if media_manifest(bundle / "media.tar") != manifest["media"]:
        raise ValueError("Manifiesto media no coincide.")
    target = "cuaderno_restore_" + uuid.uuid4().hex
    directory = root / "data/cuaderno/restores" / target
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
    report = {"passed": True, "target_database": target, "target_media": str(directory.relative_to(root)),
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
