#!/usr/bin/env python3
"""Verify that frontend provenance names and hashes every shipped bundle file."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


REPORT_NAME = "cuaderno-build-provenance.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_REPORT_BYTES = 64 * 1024 * 1024


class FrontendAssetsFailure(ValueError):
    pass


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _confined_regular(path: Path, root: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise FrontendAssetsFailure(f"No se puede leer {label}.") from exc
    if _is_link(path) or not stat.S_ISREG(metadata.st_mode) or not resolved.is_relative_to(root):
        raise FrontendAssetsFailure(f"{label} no es un archivo regular confinado.")
    return resolved


def _strict_document(report: Path, root: Path) -> dict:
    resolved = _confined_regular(report, root, "el informe de procedencia")
    if resolved.parent != root or resolved.name != REPORT_NAME:
        raise FrontendAssetsFailure("El informe debe ser el artefacto directo esperado del bundle.")
    before = resolved.stat(follow_symlinks=False)
    if before.st_size > MAX_REPORT_BYTES:
        raise FrontendAssetsFailure("El informe de procedencia supera el limite permitido.")

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise FrontendAssetsFailure(f"Clave JSON duplicada: {key}")
            result[key] = value
        return result

    try:
        raw = resolved.read_bytes()
        after = resolved.stat(follow_symlinks=False)
        if _file_identity(before) != _file_identity(after) or len(raw) != after.st_size:
            raise FrontendAssetsFailure("El informe cambio durante la verificacion.")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                FrontendAssetsFailure(f"Constante JSON no finita: {item}")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FrontendAssetsFailure("El informe no es JSON UTF-8 estricto.") from exc
    if not isinstance(value, dict):
        raise FrontendAssetsFailure("El informe de procedencia debe ser un objeto JSON.")
    return value


def _safe_name(value) -> str:
    if (not isinstance(value, str) or not value or "\\" in value
            or re.search(r"[\x00-\x1f\x7f]", value)):
        raise FrontendAssetsFailure("Nombre de asset invalido.")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise FrontendAssetsFailure("Nombre de asset fuera del bundle.")
    if re.match(r"^[A-Za-z]:", value) or value == REPORT_NAME:
        raise FrontendAssetsFailure("Nombre de asset reservado o absoluto.")
    return value


def _declared(document: dict) -> dict[str, tuple[int, str]]:
    if document.get("schema_version") != 1 or not isinstance(document.get("final_assets"), list):
        raise FrontendAssetsFailure("El informe no contiene final_assets version 1.")
    rows = document["final_assets"]
    if not rows:
        raise FrontendAssetsFailure("final_assets no puede estar vacio.")
    declared = {}
    names = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"file_name", "bytes", "sha256"}:
            raise FrontendAssetsFailure("Fila final_assets invalida.")
        name = _safe_name(row["file_name"])
        size, digest = row["bytes"], row["sha256"]
        if (name in declared or type(size) is not int or size < 0
                or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None):
            raise FrontendAssetsFailure("Fila final_assets duplicada o mal tipada.")
        declared[name] = (size, digest)
        names.append(name)
    if names != sorted(names):
        raise FrontendAssetsFailure("final_assets debe estar ordenado de forma reproducible.")
    return declared


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


def _hash_file(path: Path, root: Path) -> tuple[int, str]:
    resolved = _confined_regular(path, root, f"el asset {path.name}")
    before = resolved.stat(follow_symlinks=False)
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as stream:
        descriptor_before = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
        descriptor_after = os.fstat(stream.fileno())
    after = resolved.stat(follow_symlinks=False)
    if not (_file_identity(before) == _file_identity(descriptor_before)
            == _file_identity(descriptor_after) == _file_identity(after)):
        raise FrontendAssetsFailure("Un asset cambio durante la verificacion.")
    return size, digest.hexdigest()


def _actual(root: Path) -> dict[str, tuple[int, str]]:
    result = {}

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise FrontendAssetsFailure("No se puede recorrer el bundle frontend.") from exc
        for entry in entries:
            path = Path(entry.path)
            if _is_link(path):
                raise FrontendAssetsFailure("El bundle frontend contiene un enlace.")
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise FrontendAssetsFailure("No se puede inspeccionar un asset frontend.") from exc
            if stat.S_ISDIR(metadata.st_mode):
                if not path.resolve(strict=True).is_relative_to(root):
                    raise FrontendAssetsFailure("Un directorio sale del bundle frontend.")
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                name = path.relative_to(root).as_posix()
                if name != REPORT_NAME:
                    result[name] = _hash_file(path, root)
            else:
                raise FrontendAssetsFailure("El bundle contiene una entrada no regular.")

    visit(root)
    return result


def verify(root: Path, report: Path | None = None) -> dict:
    requested_root = root
    if _is_link(requested_root):
        raise FrontendAssetsFailure("El bundle debe ser un directorio real.")
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise FrontendAssetsFailure("No existe el directorio del bundle.") from exc
    if not root.is_dir():
        raise FrontendAssetsFailure("El bundle debe ser un directorio real.")
    report = report or root / REPORT_NAME
    document = _strict_document(report, root)
    declared = _declared(document)
    actual = _actual(root)
    if _actual(root) != actual:
        raise FrontendAssetsFailure("El bundle cambio durante la verificacion.")
    if set(declared) != set(actual):
        missing = sorted(set(actual) - set(declared))
        extra = sorted(set(declared) - set(actual))
        raise FrontendAssetsFailure(f"Cobertura final_assets distinta: faltan={missing}, sobran={extra}")
    for name in sorted(actual):
        if actual[name] != declared[name]:
            raise FrontendAssetsFailure(f"Bytes/hash no coinciden para {name}.")
    aggregate = hashlib.sha256(json.dumps(
        declared, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {"status": "verified", "files": len(actual), "sha256": aggregate}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.root, args.report), sort_keys=True))
        return 0
    except (FrontendAssetsFailure, OSError) as exc:
        print(f"FRONTEND ASSETS ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
