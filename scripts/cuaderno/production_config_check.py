"""Validate versioned production Compose with synthetic values and no services."""
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    environment = {**os.environ,
        "CUADERNO_IMAGE": "sha256:" + "a" * 64,
        "CUADERNO_DOMAIN": "cuaderno.example.invalid",
        "CUADERNO_SECRET_KEY": secrets.token_hex(48),
        "CUADERNO_DB_PASSWORD": secrets.token_hex(24),
    }
    subprocess.run(["docker", "compose", "--project-name", "cuaderno-prod-config-check",
                    "-f", str(ROOT / "deploy/cuaderno/compose.production.yml"), "config", "--quiet"],
                   env=environment, cwd=ROOT, check=True, timeout=60)
    print("Versioned production Compose syntax valid; no services started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
