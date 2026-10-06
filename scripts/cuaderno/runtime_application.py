"""Bind the copied runtime application bytes independently to checkout bytes."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import stat
from pathlib import Path

DIRECTORIES = ("cookbook", "recipes", "cuaderno", "http.d")
COPY_FILES = {
    **{name: name for name in ("boot.sh", "manage.py", "plugin.py", "requirements.txt", "LICENSE.md")},
    "PYTHON-PRODUCTION.constraints.txt": "tooling/cuaderno/python-production.constraints.txt",
    "PYTHON-TEST.constraints.txt": "tooling/cuaderno/python-test.constraints.txt",
    **{f"release-tools/{name}.py": f"scripts/cuaderno/{name}.py" for name in (
        "release_runtime_check", "python_lock", "release_manifest", "process_supervisor", "runtime_application", "frontend_assets", "patch_runtime_security", "patch_tempfile_security", "bind_system_node",
    )},
}


def forbidden(relative: str) -> bool:
    parts = Path(relative).parts
    return ("__pycache__" in parts or relative.endswith((".pyc", ".pyo"))
            or relative in {"cookbook/tests", "cuaderno/tests"}
            or relative.startswith(("cookbook/tests/", "cuaderno/tests/")))


def generated(relative: str) -> bool:
    return (relative.startswith("cookbook/static/vue3/")
            or relative in {"cookbook/version_info.py", "http.d/Recipes.conf"})


def build(root: Path, *, checkout=False) -> dict:
    root = root.resolve(strict=True)
    entries = {}
    for name in DIRECTORIES:
        directory = root / name
        if directory.is_symlink() or directory.is_junction() or not directory.is_dir():
            raise ValueError(f"Missing regular runtime directory: {name}")
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if forbidden(relative):
                if not checkout:
                    raise ValueError(f"Forbidden test or bytecode in image: {relative}")
                continue
            if relative == "http.d/Recipes.conf" and not checkout:
                raise ValueError("Nginx configuration must be generated only at startup.")
            if generated(relative):
                continue
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Linked runtime input: {relative}")
            if path.is_file():
                entries[relative] = path
            elif not path.is_dir():
                raise ValueError(f"Non-regular runtime input: {relative}")
    for target, source in COPY_FILES.items():
        entries[target] = root / (source if checkout else target)
    hashes = {}
    for relative, path in sorted(entries.items()):
        if path.is_symlink() or path.is_junction() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Missing regular runtime input: {relative}")
        content = path.read_bytes()
        # These are the only source transformations made by the Dockerfile.
        if relative == "boot.sh" or Path(relative).parent.as_posix() == "http.d" and relative.endswith(".template"):
            content = re.sub(b"\r(?=\n|$)", b"", content)
        hashes[relative] = hashlib.sha256(content).hexdigest()
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if not checkout and stat.S_IMODE((root / "boot.sh").stat().st_mode) != 0o755:
        raise ValueError("Runtime boot.sh must have mode 0755.")
    return {"schema_version": 1, "files": hashes, "sha256": digest, "boot_mode": "0755"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = build(args.root)
    output = args.output if args.output.is_absolute() else args.root / args.output
    if output.parent.resolve() != args.root.resolve() or output.exists() or output.is_symlink():
        raise ValueError("Runtime manifest must be a new root artifact.")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
