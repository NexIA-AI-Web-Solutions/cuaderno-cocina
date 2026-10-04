#!/usr/bin/env python3
"""Run the release Vue typecheck in the exact pinned, offline Node image."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
NODE_IMAGE = (
    "node:24.21.0-bookworm-slim@"
    "sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6"
)
TIMEOUT_SECONDS = 1800


class TypecheckContainerFailure(ValueError):
    """The fixed container invocation could not be constructed or launched."""


def command(*, root: Path = ROOT, container: str | None = None) -> list[str]:
    try:
        root = root.resolve(strict=True)
        vue = root / "vue3"
        if vue.is_symlink() or not vue.is_dir():
            raise TypecheckContainerFailure("vue3 debe ser un directorio regular del checkout.")
        vue = vue.resolve(strict=True)
        if vue.parent != root:
            raise TypecheckContainerFailure("vue3 debe pertenecer directamente al checkout.")
        compiler = vue / "node_modules/vue-tsc/bin/vue-tsc.js"
        config = vue / "tsconfig.app.json"
        if compiler.is_symlink() or not compiler.is_file() or config.is_symlink() or not config.is_file():
            raise TypecheckContainerFailure("Falta el compilador fijado o tsconfig.app.json.")
    except OSError as exc:
        raise TypecheckContainerFailure("No se pudo resolver el checkout para el typecheck.") from exc
    container = container or f"cuaderno-typecheck-{uuid.uuid4().hex[:12]}"
    return [
        "docker", "run", "--rm", "--name", container, "--network", "none",
        "--mount", f"type=bind,source={vue},target=/project,readonly",
        "--workdir", "/project", NODE_IMAGE,
        "node", "node_modules/vue-tsc/bin/vue-tsc.js", "--noEmit",
        "-p", "tsconfig.app.json", "--tsBuildInfoFile", "/tmp/cuaderno-typecheck.tsbuildinfo",
    ]


def run(*, root: Path = ROOT, runner=subprocess.run, cleanup_runner=subprocess.run) -> int:
    container = f"cuaderno-typecheck-{uuid.uuid4().hex[:12]}"
    argv = command(root=root, container=container)
    try:
        completed = runner(argv, cwd=root.resolve(), check=False, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            cleanup_runner(
                ["docker", "rm", "-f", container], cwd=root.resolve(), check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        print(f"TYPECHECK CONTAINER ERROR: timeout tras {TIMEOUT_SECONDS}s", file=sys.stderr)
        return 124
    except OSError as exc:
        raise TypecheckContainerFailure("No se pudo ejecutar Docker para el typecheck.") from exc
    return completed.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        return run()
    except TypecheckContainerFailure as exc:
        print(f"TYPECHECK CONTAINER ERROR: {exc}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
