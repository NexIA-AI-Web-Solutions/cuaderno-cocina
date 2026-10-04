#!/usr/bin/env python3
"""Build and verify the pinned Alpine runtime-security APK bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

EXPECTED_PACKAGES = {
    "busybox": "1.37.0-r31",
    "busybox-binsh": "1.37.0-r31",
    "ssl_client": "1.37.0-r31",
    "zlib": "1.3.2-r1",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs(root: Path) -> dict[str, str]:
    manifest = root / "source-inputs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError("source-inputs.json must be a non-empty object")
    for relative, expected in data.items():
        path = root / relative
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"unsafe source path: {relative!r}")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"source input is not a regular file: {relative}")
        if sha256(path) != expected:
            raise ValueError(f"source input hash mismatch: {relative}")
    return data


def validate_export(output: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for apk in output.glob("packages/**/*.apk"):
        for name, version in EXPECTED_PACKAGES.items():
            if apk.name == f"{name}-{version}.apk":
                found[name] = sha256(apk)
    missing = EXPECTED_PACKAGES.keys() - found.keys()
    if missing:
        raise ValueError(f"missing built APKs: {', '.join(sorted(missing))}")
    sums = output / "SHA256SUMS"
    security = output / "SECURITY.alpine-backports.json"
    source = output / "corresponding-source"
    if not sums.is_file() or not security.is_file() or not (source / "aports/main/busybox/APKBUILD").is_file() or not (
        source / "aports/main/zlib/APKBUILD"
    ).is_file():
        raise ValueError("export lacks checksums or corresponding source")
    record = json.loads(security.read_text(encoding="utf-8"))
    if record["source_inputs_sha256"] != sha256(source / "source-inputs.json"):
        raise ValueError("security record source-input hash mismatch")
    for name, version in EXPECTED_PACKAGES.items():
        if record["packages"][name]["version"] != version or record["packages"][name]["apk_sha256"] != found[name]:
            raise ValueError(f"security record mismatch: {name}")
    if set(record["runtime_files"]) != {"/bin/busybox", "/usr/bin/ssl_client", "/usr/lib/libz.so.1.3.2"}:
        raise ValueError("security record runtime file set mismatch")
    if any(len(value) != 64 for value in record["runtime_files"].values()):
        raise ValueError("security record runtime hash malformed")
    return found


def build(repo: Path, output: Path, *, runner=subprocess.run) -> dict[str, str]:
    context = repo / "docker/runtime-security"
    load_inputs(context)
    output = output.resolve()
    allowed = (repo / ".cuaderno-runs").resolve()
    if output == allowed or allowed not in output.parents:
        raise ValueError("output must be a new directory below .cuaderno-runs")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "docker", "buildx", "build", "--platform", "linux/amd64", "--target", "export",
        "--file", str(context / "Dockerfile"), "--output", f"type=local,dest={output}", str(context),
    ]
    runner(command, cwd=repo, check=True)
    return validate_export(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        build(args.repo.resolve(), args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"runtime-security build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
