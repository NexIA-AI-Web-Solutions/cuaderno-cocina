#!/usr/bin/env python3
"""Assemble an immutable release manifest from explicit candidate evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

try:
    from . import candidate_context, release_gate
except ImportError:
    import candidate_context
    import release_gate


ROOT = Path(__file__).resolve().parents[2]
CONTEXT_KEYS = release_gate.MANIFEST_KEYS - {"checks"}


class ManifestCollectFailure(ValueError):
    pass


def _strict_json(path: Path, label: str) -> tuple[dict, bytes]:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ManifestCollectFailure(f"{label} contiene una clave duplicada: {key}")
            value[key] = item
        return value

    try:
        raw = path.read_bytes()
        document = json.loads(
            raw, object_pairs_hook=unique,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ManifestCollectFailure(f"{label} contiene {item} no permitido.")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestCollectFailure(f"No se pudo leer {label} como JSON estricto.") from exc
    if not isinstance(document, dict):
        raise ManifestCollectFailure(f"{label} debe ser un objeto JSON.")
    return document, raw


def _evidence_root(root: Path) -> Path:
    evidence = root / ".cuaderno-runs"
    if evidence.is_symlink() or bool(getattr(evidence, "is_junction", lambda: False)()):
        raise ManifestCollectFailure("El directorio de evidencias no puede ser un enlace.")
    try:
        resolved = evidence.resolve(strict=True)
    except OSError as exc:
        raise ManifestCollectFailure("No existe .cuaderno-runs.") from exc
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise ManifestCollectFailure("El directorio de evidencias sale del checkout.")
    return resolved


def _regular_confined(path: Path, evidence: Path, label: str, *, direct: bool = False) -> Path:
    candidate = path if path.is_absolute() else evidence.parent / path
    if candidate.is_symlink() or bool(getattr(candidate, "is_junction", lambda: False)()):
        raise ManifestCollectFailure(f"{label} no puede ser un enlace.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ManifestCollectFailure(f"No existe {label}.") from exc
    if not resolved.is_file() or not resolved.is_relative_to(evidence):
        raise ManifestCollectFailure(f"{label} sale del directorio de evidencias.")
    if direct and resolved.parent != evidence:
        raise ManifestCollectFailure(f"{label} debe estar directamente en .cuaderno-runs.")
    return resolved


def _output_path(path: Path, root: Path, evidence: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink() or bool(getattr(candidate, "is_junction", lambda: False)()):
        raise ManifestCollectFailure("La salida no puede ser un enlace.")
    try:
        parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise ManifestCollectFailure("El directorio de salida no existe.") from exc
    if parent != evidence:
        raise ManifestCollectFailure("La salida debe estar directamente en .cuaderno-runs.")
    if candidate.exists():
        raise ManifestCollectFailure("La salida debe ser nueva; no se sobrescribe evidencia.")
    return candidate


def _reject_tracked_output(root: Path, output: Path, runner) -> None:
    relative = output.relative_to(root).as_posix()
    try:
        result = runner(
            ["git", "ls-files", "--error-unmatch", "--", relative], cwd=root, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="strict", timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ManifestCollectFailure("No se pudo comprobar si la salida está versionada.") from exc
    if result.returncode == 0:
        raise ManifestCollectFailure("La salida está versionada y no puede usarse como evidencia local.")
    if result.returncode != 1:
        raise ManifestCollectFailure("Git no pudo comprobar la ruta de salida.")


def collect(context_path: Path, record_paths: list[Path], *,
            output_path: Path = Path(".cuaderno-runs/manifest.json"), root: Path = ROOT,
            runner=subprocess.run, context_validator=candidate_context.same_candidate,
            gate=release_gate.aggregate) -> tuple[Path, dict]:
    """Create a new manifest only after the existing release gate accepts it."""
    root = root.resolve(strict=True)
    evidence = _evidence_root(root)
    context_file = _regular_confined(context_path, evidence, "el contexto candidato", direct=True)
    output = _output_path(output_path, root, evidence)
    _reject_tracked_output(root, output, runner)

    context, _ = _strict_json(context_file, "El contexto candidato")
    if set(context) != CONTEXT_KEYS:
        raise ManifestCollectFailure("El contexto candidato no tiene el contrato exacto esperado.")
    if not record_paths:
        raise ManifestCollectFailure("Deben indicarse explícitamente las 17 evidencias.")

    checks = {}
    seen_paths = set()
    for supplied in record_paths:
        record_path = _regular_confined(supplied, evidence, "una evidencia", direct=True)
        if record_path in seen_paths:
            raise ManifestCollectFailure("La misma evidencia se indicó más de una vez.")
        seen_paths.add(record_path)
        record, raw = _strict_json(record_path, f"La evidencia {record_path.name}")
        command = record.get("command")
        if not isinstance(command, str) or command not in release_gate.REQUIRED_CHECKS:
            raise ManifestCollectFailure(f"Comando de evidencia inesperado: {command!r}")
        if command in checks:
            raise ManifestCollectFailure(f"Hay evidencias duplicadas para {command}.")
        checks[command] = {
            "path": record_path.relative_to(evidence).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if set(checks) != release_gate.REQUIRED_CHECKS:
        missing = sorted(release_gate.REQUIRED_CHECKS - set(checks))
        raise ManifestCollectFailure("Faltan evidencias requeridas: " + ", ".join(missing))

    document = {key: context[key] for key in CONTEXT_KEYS}
    document["checks"] = checks
    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    temporary = evidence / f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            summary = gate(
                temporary, root=root, runner=runner, context_validator=context_validator,
            )
        except release_gate.ReleaseGateFailure as exc:
            raise ManifestCollectFailure(f"El release gate rechazó el manifiesto: {exc}") from exc
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise ManifestCollectFailure("La salida apareció durante la validación; no se sobrescribe.") from exc
        except OSError as exc:
            raise ManifestCollectFailure("No se pudo publicar atómicamente el manifiesto validado.") from exc
        return output, summary
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--records", required=True, nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".cuaderno-runs/manifest.json"))
    args = parser.parse_args(argv)
    try:
        path, summary = collect(args.context, args.records, output_path=args.output)
        print(json.dumps({"manifest": str(path.relative_to(ROOT)), **summary},
                         ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except ManifestCollectFailure as exc:
        print(f"RELEASE MANIFEST ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
