#!/usr/bin/env python3
"""Apply a byte-pinned, unmerged CPython 3.13.16 tempfile/shutil backport offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import stat
import sys


PYTHON_VERSION = (3, 13, 16)
CVE = "CVE-2026-12345"
UPSTREAM_COMMIT = "56caf8e0b89463e2e8465ce06f7aaa31847c1768"
SOURCE_DIRECTORY = Path(__file__).resolve().parents[2] / "tooling/cuaderno/cpython-tempfile-security"
ORIGINAL_SHA256 = {
    "tempfile.py": "7350d7f75ca8d6e4752c377777a315dc26eb4ecd3b6c9c0951bffddc576f030f",
    "shutil.py": "11c32fd568588e38463fdf281caa7ef0edbf3d64daf7961f0e7e68d779528731",
}
PATCHED_SHA256 = {
    "tempfile.py": "05f12fd8e347c9ac71777e3a5b2811a8b9da5200999b3bea83f660599ae460da",
    "shutil.py": "7619899fbdf67c74d77537968dd8382033aa2f8a9436adba5cdd1e724e50e7e9",
}
LICENSE_SHA256 = "78b12c3a81360b357002334f0e70ea0e92eebf7a9b358805c03c48484945f3bb"
MAX_SOURCE_BYTES = 128 * 1024


class PatchFailure(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def provenance() -> dict:
    return {
        "schema_version": 1, "cve": CVE, "python": ".".join(map(str, PYTHON_VERSION)),
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_commit_url": f"https://github.com/python/cpython/commit/{UPSTREAM_COMMIT}",
        "upstream_pull_request": "https://github.com/python/cpython/pull/158429",
        "upstream_status": "open-unmerged-backport",
        "files": {name: {
            "original_url": f"https://raw.githubusercontent.com/python/cpython/v3.13.16/Lib/{name}",
            "original_sha256": ORIGINAL_SHA256[name],
            "patched_url": f"https://raw.githubusercontent.com/python/cpython/{UPSTREAM_COMMIT}/Lib/{name}",
            "patched_sha256": PATCHED_SHA256[name],
        } for name in ORIGINAL_SHA256},
        "license": {
            "url": f"https://raw.githubusercontent.com/python/cpython/{UPSTREAM_COMMIT}/LICENSE",
            "sha256": LICENSE_SHA256,
        },
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchFailure(message)


def _absolute(path: Path) -> Path:
    path = Path(path)
    _require(path.is_absolute() and ".." not in path.parts, "La ruta del backport debe ser absoluta y sin traversal.")
    return path


def _no_links(path: Path) -> None:
    current = _absolute(path)
    while True:
        _require(not current.is_symlink() and not getattr(current, "is_junction", lambda: False)(),
                 "El backport no admite enlaces ni junctions en sus rutas.")
        metadata = current.lstat()
        if current != path:
            _require(stat.S_ISDIR(metadata.st_mode), "Un ancestro del backport no es un directorio.")
        if current.parent == current:
            break
        current = current.parent


def _identity(metadata) -> tuple:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_gid,
            metadata.st_nlink, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def _read_regular(path: Path, *, limit: int = MAX_SOURCE_BYTES) -> tuple[bytes, os.stat_result]:
    _no_links(path)
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= limit,
             "El backport requiere archivos regulares, acotados y sin hardlinks.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        _require(_identity(os.fstat(descriptor)) == _identity(before), "Un archivo cambió al abrir el backport.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        _require(len(raw) <= limit and _identity(os.fstat(descriptor)) == _identity(before)
                 and _identity(path.lstat()) == _identity(before), "Un archivo cambió durante la lectura del backport.")
        return raw, before
    finally:
        os.close(descriptor)


def _vendor_sources(directory: Path) -> dict[str, bytes]:
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "La procedencia del backport tiene claves duplicadas.")
            value[key] = item
        return value

    sources = {}
    for name, expected in PATCHED_SHA256.items():
        raw, _ = _read_regular(directory / name)
        _require(_sha256(raw) == expected, "Los bytes del backport no coinciden con el pin oficial.")
        compile(raw, name, "exec")
        sources[name] = raw
    license_raw, _ = _read_regular(directory / "LICENSE")
    _require(_sha256(license_raw) == LICENSE_SHA256, "La licencia PSF no coincide con el pin fijado.")
    metadata_raw, _ = _read_regular(directory / "provenance.json", limit=16 * 1024)
    metadata = json.loads(metadata_raw, object_pairs_hook=pairs,
                          parse_constant=lambda item: (_ for _ in ()).throw(PatchFailure(item)))
    _require(isinstance(metadata, dict) and type(metadata.get("schema_version")) is int
             and metadata == provenance(), "La procedencia del backport no coincide con el contrato fijado.")
    return sources


def _stage(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _result(directory: Path, status: str) -> dict:
    return {**provenance(), "status": status, "stdlib_path": str(directory),
            "installed_files": {name: {"path": str(directory / name), "sha256": expected}
                                for name, expected in PATCHED_SHA256.items()}}


def patch_stdlib_pair(stdlib_path: Path, *, source_directory: Path = SOURCE_DIRECTORY,
                      python_version=None, python_implementation=None) -> dict:
    """Validate both files before staging; replace each atomically, restoring on failure."""
    version = tuple(sys.version_info[:3] if python_version is None else python_version)
    implementation = platform.python_implementation() if python_implementation is None else python_implementation
    _require(implementation == "CPython" and version == PYTHON_VERSION,
             "El backport solo admite CPython 3.13.16 exacto.")
    directory, source_directory = _absolute(stdlib_path), _absolute(source_directory)
    staged = None
    committed = []
    before = {}
    try:
        _no_links(directory)
        _require(directory.is_dir(), "La ruta stdlib no es un directorio regular.")
        for name in ORIGINAL_SHA256:
            before[name] = _read_regular(directory / name)
        hashes = {name: _sha256(raw) for name, (raw, _) in before.items()}
        if hashes == PATCHED_SHA256:
            return _result(directory, "already-patched")
        _require(hashes == ORIGINAL_SHA256, "La pareja stdlib no coincide con ambos originales; mezcla o manipulación rechazada.")
        sources = _vendor_sources(source_directory)
        # Only after both originals and the complete pinned input have passed.
        candidate = directory / (".cuaderno-tempfile-security-" + secrets.token_hex(12))
        candidate.mkdir(mode=0o700)
        staged = candidate
        for name, (raw, _) in before.items():
            _stage(staged / (name + ".before"), raw)
            _stage(staged / name, sources[name])
        for name, (_, metadata) in before.items():
            current, current_metadata = _read_regular(directory / name)
            _require(_identity(current_metadata) == _identity(metadata) and _sha256(current) == ORIGINAL_SHA256[name],
                     "La pareja stdlib cambió antes de reemplazarla.")
            os.chmod(staged / name, stat.S_IMODE(metadata.st_mode))
            os.replace(staged / name, directory / name)
            committed.append(name)
        for name, (_, metadata) in before.items():
            raw, installed = _read_regular(directory / name)
            _require(_sha256(raw) == PATCHED_SHA256[name]
                     and stat.S_IMODE(installed.st_mode) == stat.S_IMODE(metadata.st_mode),
                     "Falló la verificación final de bytes o permisos de la pareja stdlib.")
        return _result(directory, "patched")
    except (OSError, ValueError, SyntaxError) as error:
        rollback_failed = False
        if staged is not None:
            for name in reversed(committed):
                try:
                    os.chmod(staged / (name + ".before"), stat.S_IMODE(before[name][1].st_mode))
                    os.replace(staged / (name + ".before"), directory / name)
                except OSError:
                    rollback_failed = True
        if rollback_failed:
            raise PatchFailure("El backport falló y no pudo restaurar la pareja; descarta el build.") from error
        if isinstance(error, PatchFailure):
            raise
        raise PatchFailure("No se pudo aplicar o verificar la pareja stdlib fijada.") from error
    finally:
        if staged is not None:
            for name in ORIGINAL_SHA256:
                (staged / name).unlink(missing_ok=True)
                (staged / (name + ".before")).unlink(missing_ok=True)
            staged.rmdir()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdlib-path", required=True, type=Path)
    parser.add_argument("--source-directory", type=Path, default=SOURCE_DIRECTORY)
    args = parser.parse_args(argv)
    result = patch_stdlib_pair(args.stdlib_path, source_directory=args.source_directory)
    print("CUADERNO_TEMPFILE_SECURITY " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchFailure as error:
        print(f"CUADERNO_TEMPFILE_SECURITY ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None
