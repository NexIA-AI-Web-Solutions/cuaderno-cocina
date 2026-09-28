#!/usr/bin/env python3
"""Dump the isolated G0 Postgres database. Refuses to run if the container is absent."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = "cuaderno-g0-t002-db"
DB = "cuaderno_demo"
USER = "cuaderno_demo"


def main() -> int:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/cuaderno/evidence") / f"backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sql"
    probe = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], text=True, capture_output=True)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        print("La base aislada no está en marcha. No se ha tocado ningún otro volumen.", file=sys.stderr)
        return 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    dump = subprocess.run(
        ["docker", "exec", CONTAINER, "pg_dump", "-U", USER, "-d", DB, "--no-owner"],
        text=True,
        capture_output=True,
    )
    if dump.returncode != 0:
        print(dump.stderr, file=sys.stderr)
        return dump.returncode
    destination.write_text(dump.stdout, encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
