"""Build and start ONLY the isolated Cuaderno release preview on loopback."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import re
import subprocess
from delivery_backup import source_manifest

ROOT = Path(__file__).resolve().parents[2]


def build_identity(commit: str, source_sha256: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("La identidad exige hashes Git/SHA256 válidos.")
    return f"{commit}+worktree.{source_sha256}"


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


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
    if not args.no_build:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        identity = build_identity(commit, source_manifest()["sha256"])
        run("docker", "build", "-f", "deploy/cuaderno/Dockerfile", "--build-arg", f"SOURCE_COMMIT={identity}", "-t", "cuaderno-cocina:local", ".")
    run("docker", "compose", "--project-name", "cuaderno-release", "--env-file", str(env_file), "-f", "deploy/cuaderno/compose.local.yml", "up", "-d", "--wait", "--wait-timeout", "600")
    print("Preview local: http://127.0.0.1:18081 — bases y volúmenes exclusivos cuaderno-release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
