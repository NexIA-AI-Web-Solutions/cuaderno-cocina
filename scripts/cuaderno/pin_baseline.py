"""Reproduce two upstream failures using untouched pin code and a NEW PostgreSQL."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
PIN = "7e1c427a0e17858ddc41bd198c79ccad77d3bd69"
IMAGE = "cuaderno-g0-t002-app:f77a459f"


def run(argv, *, quiet=False, check=True):
    result = subprocess.run(argv, cwd=ROOT, check=False, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE if quiet else None, stderr=subprocess.STDOUT if quiet else None, timeout=900)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {argv[0:3]}")
    return result


def main():
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}:
        raise RuntimeError("Solo entorno local/test/development; nunca una base real.")
    run(["git", "diff", "--exit-code", PIN, "f77a459ff", "--", "cookbook", "recipes", "requirements.txt", "pytest.ini", "Dockerfile"])
    image_id = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], quiet=True).stdout.strip()
    expected_id = "sha256:68946d4df1351cf5b30c7c606243856d65681439d6db4436baed9298d88cea8b"
    if image_id != expected_id:
        raise RuntimeError("La imagen no coincide con el baseline registrado T002.")
    print(f"Pin baseline image: {image_id}")
    suffix = uuid.uuid4().hex[:12]
    network = f"cuaderno-pin-baseline-{suffix}"
    database = f"cuaderno-pin-db-{suffix}"
    tests = f"cuaderno-pin-tests-{suffix}"
    password = uuid.uuid4().hex
    run(["docker", "network", "create", network])
    run(["docker", "run", "-d", "--name", database, "--network", network,
         "-e", "POSTGRES_USER=pinrunner", "-e", f"POSTGRES_PASSWORD={password}", "-e", "POSTGRES_DB=pin_baseline", "postgres:16-alpine"], quiet=True)
    for _ in range(60):
        if run(["docker", "exec", database, "pg_isready", "-U", "pinrunner", "-d", "pin_baseline"], quiet=True, check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"No readiness: {database}; retained for inspection.")
    # No mounts/copies of modified checkout; dependencies installed only in this new test container.
    # This reproduced image has empty upstream version_info; verify immutable image ID above instead.
    command = "set -eu; "
    command += "/opt/recipes/venv/bin/pip install pytest==9.0.3 pytest-django==4.11.1 pytest-cov==6.2.1 pytest-factoryboy==2.8.1 pytest-html==4.1.1 pytest-asyncio==1.4.0 pytest-xdist==3.8.0; "
    command += "/opt/recipes/venv/bin/python -m pytest -o addopts='' -vv --tb=long cookbook/tests/other/test_cooklang_integration.py::test_cooklang_integration cookbook/tests/other/test_markdown_renderer.py::test_markdown_renderer"
    result = run(["docker", "run", "--name", tests, "--network", network, "--entrypoint", "/bin/sh",
                  "-e", f"TEST_DATABASE_URL=postgresql://pinrunner:{password}@{database}:5432/pin_baseline",
                  IMAGE, "-lc", command], check=False)
    print(f"Retained isolated resources: {database}, {tests}, network={network}. No user data/volumes were removed.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
