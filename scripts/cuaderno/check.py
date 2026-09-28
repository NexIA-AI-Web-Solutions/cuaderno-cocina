#!/usr/bin/env python3
"""Run a verified project command and record real results. Unconfigured = failure."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


class CheckError(ValueError):
    pass


def validated_command(root: Path, name: str, registry: dict) -> tuple[list[str], Path, int, bool]:
    if registry.get("schema_version") != 1:
        raise CheckError("Schema de comandos desconocido.")
    entry = registry.get("commands", {}).get(name)
    if not isinstance(entry, dict) or entry.get("verified") is not True:
        raise CheckError(f"{name}: NO CONFIGURADO/VERIFICADO. G0 debe registrar un comando real.")
    argv = entry.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise CheckError("argv debe ser una lista explícita, no un comando shell.")
    cwd_rel = Path(entry.get("cwd", "."))
    if cwd_rel.is_absolute() or ".." in cwd_rel.parts:
        raise CheckError("cwd debe estar dentro del proyecto.")
    cwd = (root / cwd_rel).resolve()
    if not cwd.is_relative_to(root.resolve()) or not cwd.is_dir():
        raise CheckError("cwd inexistente o fuera del proyecto.")
    timeout = entry.get("timeout_seconds", 600)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 7200:
        raise CheckError("Timeout inválido (1–7200 segundos).")
    if not entry.get("verified_at_commit") or not entry.get("purpose"):
        raise CheckError("Falta commit de verificación o propósito.")
    return argv, cwd, timeout, bool(entry.get("isolated_mutations", False))


def redact(text: str) -> str:
    for key, value in os.environ.items():
        if len(value) >= 6 and re.search(r"SECRET|PASSWORD|TOKEN|API_KEY", key, re.I):
            text = text.replace(value, "[REDACTED]")
    return text


def execute(root: Path, name: str, *, allow_isolated_mutations: bool = False) -> int:
    root = root.resolve()
    registry = json.loads((root / "tooling/cuaderno/commands.json").read_text(encoding="utf-8"))
    argv, cwd, timeout, mutations = validated_command(root, name, registry)
    environment = os.environ.get("CUADERNO_ENV", "").lower()
    if environment in {"prod", "production"}:
        raise CheckError("Este runner no se usa contra producción.")
    if mutations and not (allow_isolated_mutations and environment in {"test", "development", "local"}):
        raise CheckError("Exige CUADERNO_ENV=test/local/development y --allow-isolated-mutations; valida también DB/destino.")
    out = root / ".cuaderno-runs"
    if out.is_symlink():
        raise CheckError("El directorio de evidencias no puede ser un symlink.")
    out.mkdir(exist_ok=True)
    started = time.monotonic()
    text = ""
    try:
        result = subprocess.run(argv, cwd=cwd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        code, text = result.returncode, result.stdout
    except subprocess.TimeoutExpired as exc:
        code, text = 124, f"TIMEOUT: {exc}"
    except OSError as exc:
        code, text = 127, f"EXEC ERROR: {exc}"
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
        commit = git.stdout.strip() if git.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    rid = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{safe_name}-{uuid.uuid4().hex[:8]}"
    (out / f"{rid}.log").write_text(redact(text), encoding="utf-8")
    record = {"command": name, "argv": [redact(a) for a in argv], "cwd": str(cwd.relative_to(root)), "commit": commit,
              "utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic()-started, 3),
              "exit_code": code, "log": f"{rid}.log", "passed": code == 0}
    (out / f"{rid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(redact(text), end="" if text.endswith("\n") else "\n")
    print(f"Resultado real: exit={code}; evidencia=.cuaderno-runs/{rid}.json")
    return code if code >= 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--allow-isolated-mutations", action="store_true")
    args = parser.parse_args()
    try:
        if args.list:
            registry = json.loads((ROOT / "tooling/cuaderno/commands.json").read_text(encoding="utf-8"))
            for name, item in registry["commands"].items():
                print(f"{name}: {'VERIFICADO' if item['verified'] else 'PENDIENTE'} — {item['purpose']}")
            return 0
        if not args.name:
            parser.error("Indica un check o --list.")
        return execute(ROOT, args.name, allow_isolated_mutations=args.allow_isolated_mutations)
    except (CheckError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
