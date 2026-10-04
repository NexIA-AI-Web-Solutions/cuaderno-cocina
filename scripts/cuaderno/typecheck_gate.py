#!/usr/bin/env python3
"""Require a clean full Vue typecheck; explicit baselines are historical diagnostics only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_RE = re.compile(r"(?m)^(.+?)\(\d+,\d+\): error TS\d+:")


class TypecheckGateFailure(ValueError):
    pass


def _run(runner, argv, *, cwd):
    try:
        return runner(argv, cwd=cwd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      text=True, encoding="utf-8", errors="replace", timeout=1200)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TypecheckGateFailure("No se pudo ejecutar el typecheck requerido.") from exc


def check(*, root: Path = ROOT, max_inherited: int = 0, expected_node_major: int = 24,
          runner=subprocess.run) -> dict:
    if not isinstance(max_inherited, int) or max_inherited < 0:
        raise TypecheckGateFailure("Baseline heredado inválido.")
    vue = root.resolve(strict=True) / "vue3"
    node = _run(runner, ["node", "--version"], cwd=vue)
    match = re.fullmatch(r"v(\d+)\.\d+\.\d+\s*", node.stdout or "")
    if node.returncode != 0 or match is None or int(match.group(1)) != expected_node_major:
        raise TypecheckGateFailure("Node no coincide con el major de release.")
    command = ["node", "node_modules/vue-tsc/bin/vue-tsc.js", "--noEmit", "-p", "tsconfig.app.json"]
    completed = _run(runner, command, cwd=vue)
    output = completed.stdout or ""
    paths = DIAGNOSTIC_RE.findall(output)
    if completed.returncode == 0 and paths:
        raise TypecheckGateFailure("vue-tsc devolvió cero pese a emitir diagnósticos.")
    if completed.returncode != 0 and not paths:
        raise TypecheckGateFailure("vue-tsc falló sin diagnósticos analizables.")
    own = sorted(path for path in paths if re.search(r"(?:^|[\\/])cuaderno[\\/]", path))
    inherited = len(paths) - len(own)
    if own:
        raise TypecheckGateFailure("Typecheck Cuaderno rojo: " + ", ".join(own))
    if inherited > max_inherited:
        raise TypecheckGateFailure(f"La deuda heredada creció: {inherited}>{max_inherited}.")
    versions = {}
    for package in ("vue-tsc", "typescript"):
        try:
            document = json.loads((vue / "node_modules" / package / "package.json").read_text(encoding="utf-8"))
            versions[package] = document["version"]
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise TypecheckGateFailure(f"No se pudo fijar la versión de {package}.") from exc
    return {
        "passed": True,
        "diagnostics_total": len(paths),
        "diagnostics_cuaderno": 0,
        "diagnostics_inherited": inherited,
        "maximum_inherited": max_inherited,
        "node": node.stdout.strip(),
        "vue_tsc": versions["vue-tsc"],
        "typescript": versions["typescript"],
        "compiler_exit": completed.returncode,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-inherited", type=int, default=0)
    parser.add_argument("--node-major", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(max_inherited=args.max_inherited, expected_node_major=args.node_major), sort_keys=True))
        return 0
    except TypecheckGateFailure as exc:
        print(f"TYPECHECK GATE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
