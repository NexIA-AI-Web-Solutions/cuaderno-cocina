#!/usr/bin/env python3
"""Restore a dump into a new database on the isolated Postgres. Never drops cuaderno_demo."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONTAINER = "cuaderno-g0-t002-db"
USER = "cuaderno_demo"
SOURCE = "cuaderno_demo"
TARGET = "cuaderno_restore_g6"


def run(args: list[str], data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=data, text=True, capture_output=True)


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: restore_proof.py <dump.sql>", file=sys.stderr)
        return 2
    dump = Path(sys.argv[1])
    if not dump.is_file():
        print("No está el volcado.", file=sys.stderr)
        return 1
    probe = run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER])
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        print("La base aislada no está en marcha.", file=sys.stderr)
        return 1
    exists = run(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{TARGET}'"])
    if exists.stdout.strip() == "1":
        print(f"{TARGET} ya existe. No se ha tocado.", file=sys.stderr)
        return 1
    created = run(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", "postgres", "-c", f"CREATE DATABASE {TARGET} OWNER {USER}"])
    if created.returncode != 0:
        print(created.stderr, file=sys.stderr)
        return created.returncode
    restored = run(["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", TARGET, "-v", "ON_ERROR_STOP=1"], dump.read_text(encoding="utf-8"))
    if restored.returncode != 0:
        print(restored.stderr[-2000:], file=sys.stderr)
        return restored.returncode
    compare = (
        "SELECT 'recipe', count(*) FROM cookbook_recipe "
        "UNION ALL SELECT 'price', count(*) FROM cuaderno_priceversion "
        "UNION ALL SELECT 'movement', count(*) FROM cuaderno_stockmovement "
        "UNION ALL SELECT 'inventory', count(*) FROM cookbook_inventoryentry ORDER BY 1;"
    )
    source = run(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", SOURCE, "-c", compare])
    target = run(["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", TARGET, "-c", compare])
    print("SOURCE")
    print(source.stdout)
    print("RESTORED")
    print(target.stdout)
    if source.stdout != target.stdout:
        print("Los conteos no coinciden.", file=sys.stderr)
        return 1
    print(TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
