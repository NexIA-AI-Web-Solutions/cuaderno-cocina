#!/usr/bin/env python3
"""Apply the byte-pinned CPython 3.13.16 poplib command-injection fix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile


PYTHON_VERSION = (3, 13, 16)
CVE = "CVE-2025-15367"
UPSTREAM_COMMIT = "b234a2b67539f787e191d2ef19a7cbdce32874e7"
ORIGINAL_URL = "https://raw.githubusercontent.com/python/cpython/v3.13.16/Lib/poplib.py"
PATCHED_URL = f"https://raw.githubusercontent.com/python/cpython/{UPSTREAM_COMMIT}/Lib/poplib.py"
COMMIT_URL = f"https://github.com/python/cpython/commit/{UPSTREAM_COMMIT}"
LICENSE_URL = "https://github.com/python/cpython/blob/v3.13.16/LICENSE"
ORIGINAL_SHA256 = "527e714523264093910a0a0b1a55c6583f952835c89061537fc40ad98c347056"
PATCHED_SHA256 = "a6ffff188814b56d95b043c31d9e0dfee51ac6d6e92afe74ab070cb6136b076f"
ORIGINAL_BLOCK = (
    b"    def _putcmd(self, line):\n"
    b"        if self._debugging: print('*cmd*', repr(line))\n"
    b"        line = bytes(line, self.encoding)\n"
    b"        self._putline(line)\n"
)
PATCHED_BLOCK = (
    b"    def _putcmd(self, line):\n"
    b"        if self._debugging: print('*cmd*', repr(line))\n"
    b"        line = bytes(line, self.encoding)\n"
    b"        if re.search(b'[\\x00-\\x1F\\x7F]', line):\n"
    b"            raise ValueError('Control characters not allowed in commands')\n"
    b"        self._putline(line)\n"
)


class PatchFailure(ValueError):
    pass


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def patch_poplib(path: Path, *, python_version=None, python_implementation=None) -> dict:
    version = tuple(sys.version_info[:3] if python_version is None else python_version)
    implementation = (platform.python_implementation() if python_implementation is None
                      else python_implementation)
    if implementation != "CPython" or version != PYTHON_VERSION:
        raise PatchFailure("El backport solo admite CPython 3.13.16 exacto.")
    path = Path(path)
    if path.name != "poplib.py" or not path.is_absolute():
        raise PatchFailure("La ruta stdlib debe ser absoluta y terminar en poplib.py.")
    if path.is_symlink() or not path.is_file():
        raise PatchFailure("poplib.py debe ser un archivo regular, no un enlace.")
    try:
        original_stat = path.stat()
        raw = path.read_bytes()
    except OSError as exc:
        raise PatchFailure("No se pudo leer poplib.py.") from exc
    current = _sha256(raw)
    if current == PATCHED_SHA256:
        return _result(path, "already-patched")
    if current != ORIGINAL_SHA256:
        raise PatchFailure("poplib.py no coincide con los bytes originales fijados.")
    if raw.count(ORIGINAL_BLOCK) != 1 or PATCHED_BLOCK in raw:
        raise PatchFailure("El bloque vulnerable de poplib.py no coincide de forma única.")
    patched = raw.replace(ORIGINAL_BLOCK, PATCHED_BLOCK, 1)
    if _sha256(patched) != PATCHED_SHA256:
        raise PatchFailure("El resultado no coincide con el SHA-256 del backport fijado.")

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".poplib-security-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(original_stat.st_mode))
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise PatchFailure("No se pudo reemplazar poplib.py atómicamente.") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    if _sha256(path.read_bytes()) != PATCHED_SHA256:
        raise PatchFailure("La verificación posterior de poplib.py falló.")
    return _result(path, "patched")


def _result(path: Path, status: str) -> dict:
    return {
        "status": status,
        "cve": CVE,
        "python": ".".join(map(str, PYTHON_VERSION)),
        "path": str(path),
        "original_sha256": ORIGINAL_SHA256,
        "patched_sha256": PATCHED_SHA256,
        "upstream_commit": UPSTREAM_COMMIT,
        "sources": {
            "original": ORIGINAL_URL, "patched": PATCHED_URL,
            "commit": COMMIT_URL, "license": LICENSE_URL,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdlib-path", required=True, type=Path)
    args = parser.parse_args(argv)
    result = patch_poplib(args.stdlib_path)
    print("CUADERNO_RUNTIME_SECURITY " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchFailure as exc:
        print(f"CUADERNO_RUNTIME_SECURITY ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
