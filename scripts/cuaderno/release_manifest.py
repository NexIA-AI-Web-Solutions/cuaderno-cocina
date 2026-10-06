"""Create the immutable image manifest after all release artifacts exist."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


SOURCE_RE = re.compile(r"[0-9a-f]{40}(?:\+worktree\.[0-9a-f]{64})?\Z")
ARTIFACTS = {
    "runtime_application": "runtime-application-manifest.json",
    "sbom_python": "SBOM.python.cdx.json",
    "sbom_frontend": "SBOM.frontend.cdx.json",
    "frontend_provenance": "cookbook/static/vue3/cuaderno-build-provenance.json",
    "version_info": "cookbook/version_info.py",
    "security_python_backports": "SECURITY.python-backports.json",
    "security_alpine_backports": "SECURITY.alpine-backports.json",
    "security_node_runtime": "SECURITY.node-runtime.json",
    "security_tempfile_backport": "SECURITY.tempfile-backport.json",
}


def build(root: Path, source_identity: str, output: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir() or SOURCE_RE.fullmatch(source_identity or "") is None:
        raise ValueError("Raíz o identidad de fuente inválida.")
    hashes = {}
    for name, relative in ARTIFACTS.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Artefacto de release inválido: {name}")
        with path.open("rb") as stream:
            hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    output = output if output.is_absolute() else root / output
    if output.exists() or output.is_symlink() or output.parent.resolve(strict=True) != root:
        raise ValueError("El manifiesto debe ser un archivo nuevo directo de la raíz runtime.")
    document = {"schema_version": 1, "source_identity": source_identity, "artifacts": hashes}
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--output", default="RELEASE-MANIFEST.json", type=Path)
    args = parser.parse_args()
    try:
        build(args.root, args.source_identity, args.output)
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR release manifest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
