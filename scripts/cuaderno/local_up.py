"""Build and start ONLY the isolated Cuaderno release preview on loopback."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
import sys
import tempfile
import uuid
try:
    from .delivery_backup import source_manifest
except ImportError:
    from delivery_backup import source_manifest

ROOT = Path(__file__).resolve().parents[2]


def build_identity(commit: str, source_sha256: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("La identidad exige hashes Git/SHA256 válidos.")
    return f"{commit}+worktree.{source_sha256}"


def run(*args, environment=None):
    subprocess.run(args, cwd=ROOT, check=True, env=environment)


def pin_image(reference: str, env_file: Path, *, identity=None, inspector=subprocess.check_output) -> str:
    rows = json.loads(inspector(["docker", "image", "inspect", reference], cwd=ROOT, text=True))
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("La referencia no identifica una imagen única.")
    image = rows[0].get("Id")
    source = (rows[0].get("Config", {}).get("Labels") or {}).get("io.cuaderno.source-identity")
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("La imagen no tiene un ID inmutable válido.")
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}\+worktree\.[0-9a-f]{64}", source):
        raise ValueError("La imagen no declara una fuente Cuaderno verificable.")
    if identity is not None and source != identity:
        raise ValueError("La imagen construida no coincide con la fuente solicitada.")
    if env_file.is_symlink() or env_file.is_junction() or not env_file.is_file():
        raise ValueError("El entorno local debe ser un archivo regular.")
    lines = [line for line in env_file.read_text(encoding="utf-8").splitlines()
             if not line.lstrip().startswith("CUADERNO_LOCAL_IMAGE=")]
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=env_file.parent,
                                     prefix=".compose-", suffix=".env", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write("\n".join([*lines, f"CUADERNO_LOCAL_IMAGE={image}"]) + "\n")
    try:
        if os.name == "posix":
            temporary.chmod(0o600)
        os.replace(temporary, env_file)
    finally:
        temporary.unlink(missing_ok=True)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}:
        parser.error("Exige CUADERNO_ENV=local/test/development.")
    directory = ROOT / "data/cuaderno/local"
    directory.mkdir(parents=True, exist_ok=True)
    env_file = directory / "compose.env"
    if not env_file.exists():
        with env_file.open("x", encoding="utf-8") as stream:
            stream.write(f"CUADERNO_LOCAL_DB_PASSWORD={secrets.token_hex(24)}\nCUADERNO_LOCAL_SECRET_KEY={secrets.token_hex(48)}\n")
    if os.name == "posix":
        env_file.chmod(0o600)
        if env_file.stat().st_mode & 0o077:
            raise PermissionError("compose.env debe ser privado (0600).")
    reference = os.environ.get("CUADERNO_CANDIDATE_IMAGE", "cuaderno-cocina:local")
    identity = None
    if not args.no_build:
        # Keep generated packages outside the source manifest. Each build gets
        # a new export; the builder validates its pinned sources and runtime bytes.
        security_context = ROOT / '.cuaderno-runs' / f'runtime-security-{uuid.uuid4().hex[:12]}'
        run(sys.executable, 'scripts/cuaderno/build_runtime_security_apks.py', '--output', str(security_context))
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        source_hash = source_manifest()["sha256"]
        identity = build_identity(commit, source_hash)
        reference = f"cuaderno-cocina:local-{commit[:12]}-{source_hash}"
        run("docker", "build", "-f", "deploy/cuaderno/Dockerfile", "--build-context", f"runtime_security={security_context}", "--build-arg", f"SOURCE_COMMIT={identity}", "-t", reference, ".")
    image = pin_image(reference, env_file, identity=identity)
    if not args.no_build:
        run("docker", "tag", image, "cuaderno-cocina:local")
    run("docker", "compose", "--project-name", "cuaderno-release", "--env-file", str(env_file), "-f", "deploy/cuaderno/compose.local.yml", "up", "-d", "--wait", "--wait-timeout", "600",
        environment={**os.environ, "CUADERNO_LOCAL_IMAGE": image})
    print("Preview local: http://127.0.0.1:18081 — bases y volúmenes exclusivos cuaderno-release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
