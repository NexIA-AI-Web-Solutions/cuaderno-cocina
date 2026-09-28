#!/usr/bin/env python3
"""Show ready tasks; validate dependencies and honest completion evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATES = {"TODO", "IN_PROGRESS", "REVIEW", "DONE", "BLOCKED"}


def validate(data: dict) -> list[dict]:
    tasks = data.get("tasks", [])
    if not tasks or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Tareas vacías o ids duplicados.")
    mapping = {t["id"]: t for t in tasks}
    for task in tasks:
        if task.get("status") not in STATES:
            raise ValueError(f"Estado inválido: {task['id']}")
        if not task.get("acceptance"):
            raise ValueError(f"Falta aceptación: {task['id']}")
        for dep in task.get("depends_on", []):
            if dep not in mapping:
                raise ValueError(f"Dependencia desconocida: {dep}")
        if task["status"] == "DONE":
            if not task.get("evidence") or not task.get("review_evidence"):
                raise ValueError(f"DONE sin evidencia y review: {task['id']}")
            if any(mapping[d]["status"] != "DONE" for d in task.get("depends_on", [])):
                raise ValueError(f"DONE con dependencia pendiente: {task['id']}")
    visited, active = set(), set()
    def visit(rid: str) -> None:
        if rid in active:
            raise ValueError("Ciclo en tareas.")
        if rid in visited:
            return
        active.add(rid)
        for dep in mapping[rid].get("depends_on", []):
            visit(dep)
        active.remove(rid)
        visited.add(rid)
    for rid in mapping:
        visit(rid)
    return tasks


def ready(tasks: list[dict]) -> list[dict]:
    done = {t["id"] for t in tasks if t["status"] == "DONE"}
    return [t for t in tasks if t["status"] == "TODO" and set(t.get("depends_on", [])).issubset(done)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    try:
        tasks = validate(json.loads((ROOT / "tooling/cuaderno/tasks.json").read_text(encoding="utf-8")))
        for task in ready(tasks) if args.ready else tasks:
            print(f"{task['id']} {task['gate']} {task['status']}: {task['title']}")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
