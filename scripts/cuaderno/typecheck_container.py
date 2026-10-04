#!/usr/bin/env python3
"""Build and run the release Vue typecheck in its exact pinned frontend stage."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
NODE_IMAGE = (
    "node:24.21.0-bookworm-slim@"
    "sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6"
)
DOCKERFILE_RELATIVE = Path("deploy/cuaderno/Dockerfile")
DOCKERIGNORE_RELATIVE = Path(".dockerignore")
VERIFIER_RELATIVE = Path("tooling/cuaderno/verify-typecheck-toolchain.mjs")
MANIFEST_RELATIVE = Path("tooling/cuaderno/typecheck-toolchain.json")
TIMEOUT_SECONDS = 1800
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
FRONTEND_PREFIX = (
    f"FROM {NODE_IMAGE} AS frontend",
    "WORKDIR /build/vue3",
    "COPY vue3/package.json vue3/yarn.lock ./",
    "RUN yarn install --frozen-lockfile --non-interactive",
    "COPY vue3/ ./",
)


class TypecheckContainerFailure(ValueError):
    """The fixed container invocation could not be constructed or launched."""


def checkout(root: Path = ROOT) -> tuple[Path, Path, Path, Path]:
    try:
        root = root.resolve(strict=True)
        vue = root / "vue3"
        if vue.is_symlink() or not vue.is_dir() or vue.resolve(strict=True).parent != root:
            raise TypecheckContainerFailure("vue3 debe ser un directorio regular del checkout.")
        dockerfile = root / DOCKERFILE_RELATIVE
        dockerignore = root / DOCKERIGNORE_RELATIVE
        verifier = root / VERIFIER_RELATIVE
        manifest = root / MANIFEST_RELATIVE
        required = (
            dockerfile, dockerignore, verifier, manifest,
            vue / "package.json", vue / "yarn.lock", vue / "tsconfig.app.json",
        )
        if any(file.is_symlink() or not file.is_file() for file in required):
            raise TypecheckContainerFailure("Falta un archivo regular requerido para el typecheck fijado.")
        dockerfile_lines = dockerfile.read_text(encoding="utf-8").splitlines()
        if tuple(dockerfile_lines[:len(FRONTEND_PREFIX)]) != FRONTEND_PREFIX:
            raise TypecheckContainerFailure("La etapa frontend fijada no instala y copia las entradas esperadas.")
        ignore_rules = [
            line.strip() for line in dockerignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if "**/node_modules" not in ignore_rules or any(rule.startswith("!") for rule in ignore_rules):
            raise TypecheckContainerFailure(".dockerignore no excluye node_modules de forma cerrada.")
    except (OSError, UnicodeError, IndexError) as exc:
        raise TypecheckContainerFailure("No se pudo validar el checkout para el typecheck.") from exc
    return root, dockerfile, verifier, manifest


def build_command(*, dockerfile: Path, tag: str) -> list[str]:
    return [
        "docker", "build", "--file", str(dockerfile), "--target", "frontend",
        "--tag", tag, ".",
    ]


def inspect_command(*, tag: str) -> list[str]:
    return ["docker", "image", "inspect", "--format", "{{.Id}}", tag]


def typecheck_command(
    *, image_id: str, verifier: Path, manifest: Path, container: str,
) -> list[str]:
    if IMAGE_ID.fullmatch(image_id) is None:
        raise TypecheckContainerFailure("Docker no devolvió un identificador de imagen inmutable.")
    return [
        "docker", "run", "--rm", "--name", container, "--network", "none", "--read-only",
        "--mount", f"type=bind,source={verifier},target=/tooling/verify-typecheck-toolchain.mjs,readonly",
        "--mount", f"type=bind,source={manifest},target=/tooling/typecheck-toolchain.json,readonly",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--workdir", "/build/vue3", image_id,
        "sh", "-eu", "-c",
        "node /tooling/verify-typecheck-toolchain.mjs --project /build/vue3 "
        "--manifest /tooling/typecheck-toolchain.json && "
        "exec node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json "
        "--tsBuildInfoFile /tmp/cuaderno-typecheck.tsbuildinfo",
    ]


def run(*, root: Path = ROOT, runner=subprocess.run, cleanup_runner=subprocess.run) -> int:
    root, dockerfile, verifier, manifest = checkout(root)
    token = uuid.uuid4().hex[:12]
    tag = f"cuaderno-typecheck-source:{token}"
    container = f"cuaderno-typecheck-{token}"
    try:
        built = runner(
            build_command(dockerfile=dockerfile, tag=tag), cwd=root, check=False,
            timeout=TIMEOUT_SECONDS,
        )
        if built.returncode:
            return built.returncode
        inspected = runner(
            inspect_command(tag=tag), cwd=root, check=False, timeout=60,
            capture_output=True, text=True, encoding="utf-8",
        )
        if inspected.returncode:
            return inspected.returncode
        image_id = inspected.stdout.strip()
        completed = runner(
            typecheck_command(
                image_id=image_id, verifier=verifier, manifest=manifest, container=container,
            ),
            cwd=root, check=False, timeout=TIMEOUT_SECONDS,
        )
        return completed.returncode
    except subprocess.TimeoutExpired:
        try:
            cleanup_runner(
                ["docker", "rm", "-f", container], cwd=root, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        print(f"TYPECHECK CONTAINER ERROR: timeout tras {TIMEOUT_SECONDS}s", file=sys.stderr)
        return 124
    except OSError as exc:
        raise TypecheckContainerFailure("No se pudo ejecutar Docker para el typecheck.") from exc
    finally:
        try:
            cleanup_runner(
                ["docker", "image", "rm", tag], cwd=root, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass


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
