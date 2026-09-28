#!/usr/bin/env python3
"""Change only this kit's implementation model assignment; not account access."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def configure(root: Path, model: str) -> int:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,79}", model):
        raise ValueError("Identificador de modelo inválido.")
    routing_path = root / "tooling/cuaderno/model-routing.json"
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    previous = routing["implementation"]["model"]
    config_path = root / ".codex/config.toml"
    original = config_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(original)
    if parsed.get("agents", {}).get("default_subagent_model") != previous:
        raise ValueError("La configuración fue modificada; reconcilia el modelo actual antes de continuar.")
    replacement, count = re.subn(r'^default_subagent_model\s*=\s*"[^"\n]+"\s*$', f'default_subagent_model = "{model}"', original, flags=re.M)
    if count != 1:
        raise ValueError("No hay una única asignación reconocible en config.toml.")
    planned = {config_path: replacement}
    for file in (root / ".codex/agents").glob("*.toml"):
        text = file.read_text(encoding="utf-8")
        role = tomllib.loads(text)
        if role["name"] == "cocina_reviewer":
            continue
        if role.get("model") != previous:
            raise ValueError(f"{file.name} fue modificado; reconcilia antes de cambiarlo.")
        changed, n = re.subn(r'^model\s*=\s*"[^"\n]+"\s*$', f'model = "{model}"', text, flags=re.M)
        if n != 1:
            raise ValueError(f"Asignación no reconocida: {file.name}")
        tomllib.loads(changed)
        planned[file] = changed
    routing["implementation"]["model"] = model
    routing["implementation"]["interpretation"] = "Asignación explícita del propietario; medium. Verificar disponibilidad en su cliente."
    routing["effective_models_verified"] = False
    planned[routing_path] = json.dumps(routing, ensure_ascii=False, indent=2)+"\n"
    # All validations finish before the first write. Only known kit files are changed.
    for file, content in planned.items():
        file.write_text(content, encoding="utf-8")
    return len(planned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-model", required=True)
    args = parser.parse_args()
    try:
        n = configure(ROOT, args.worker_model)
        print(f"{n} archivos actualizados. Líder y revisor conservados; acceso no verificado.")
        print("Reabre la sesión para comprobar que el cliente carga las asignaciones. AGENTS.md conserva la solicitud histórica; el routing explícito actualizado define el modelo efectivo solicitado.")
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
