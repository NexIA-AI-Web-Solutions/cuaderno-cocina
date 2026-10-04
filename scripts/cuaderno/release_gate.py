#!/usr/bin/env python3
"""Fail-closed aggregation of release evidence tied to one clean candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

try:
    from . import candidate_context
except ImportError:
    import candidate_context


ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_CHECKS = frozenset({
    "build-image",
    "runtime-python-lock",
    "runtime-pip-check",
    "migrations-final",
    "schema-final",
    "native-regression-final",
    "integration-final",
    "typecheck-final",
    "e2e-final",
    "security-final",
    "performance-final",
    "image-audit-linux",
    "frontend-provenance",
    "sbom-python",
    "sbom-frontend",
    "restore-final",
    "rollback-final",
})
MANIFEST_KEYS = frozenset({
    "schema_version", "git_commit", "source_sha256", "source_identity", "image_id",
    "environment_fingerprint", "candidate_id", "commands_registry_sha256", "environment", "checks",
})


class ReleaseGateFailure(ValueError):
    pass


def _strict_json(path: Path, label: str) -> tuple[dict, bytes]:
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ReleaseGateFailure(f"{label} contiene una clave duplicada.")
            result[key] = value
        return result

    try:
        raw = path.read_bytes()
        document = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(
            ReleaseGateFailure(f"{label} contiene {value} no permitido.")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseGateFailure(f"No se pudo leer {label} como JSON estricto.") from exc
    if not isinstance(document, dict):
        raise ReleaseGateFailure(f"{label} debe ser un objeto JSON.")
    return document, raw


def _regular_confined(path: Path, root: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReleaseGateFailure(f"No existe {label}.") from exc
    if path.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(root):
        raise ReleaseGateFailure(f"{label} sale del directorio de evidencia o es un enlace.")
    return resolved


def _git(root: Path, runner, *args: str) -> str:
    try:
        completed = runner(
            ["git", *args], cwd=root, check=False, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="strict", timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ReleaseGateFailure("No se pudo verificar Git.") from exc
    if completed.returncode != 0:
        raise ReleaseGateFailure("Git no pudo verificar el candidato.")
    return (completed.stdout or "").strip()


def aggregate(manifest_path: Path, *, root: Path = ROOT, runner=subprocess.run,
              context_validator=candidate_context.same_candidate) -> dict:
    root = root.resolve(strict=True)
    evidence_root = root / ".cuaderno-runs"
    try:
        evidence_root = evidence_root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseGateFailure("No existe el directorio local de evidencias.") from exc
    if not evidence_root.is_dir() or not evidence_root.is_relative_to(root):
        raise ReleaseGateFailure("Directorio de evidencias inválido.")
    manifest_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest_path = _regular_confined(manifest_path, evidence_root, "el manifiesto candidato")
    manifest, manifest_raw = _strict_json(manifest_path, "El manifiesto candidato")
    if set(manifest) != MANIFEST_KEYS:
        raise ReleaseGateFailure("El manifiesto candidato no tiene el contrato exacto esperado.")
    if manifest.get("schema_version") != 1:
        raise ReleaseGateFailure("Versión de manifiesto candidata no soportada.")

    commit = manifest.get("git_commit")
    source_sha = manifest.get("source_sha256")
    image_id = manifest.get("image_id")
    environment = manifest.get("environment_fingerprint")
    candidate_id = manifest.get("candidate_id")
    registry_sha = manifest.get("commands_registry_sha256")
    environment_payload = manifest.get("environment")
    checks = manifest.get("checks")
    if (not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None
            or not isinstance(source_sha, str) or SHA256_RE.fullmatch(source_sha) is None
            or not isinstance(image_id, str) or IMAGE_RE.fullmatch(image_id) is None
            or not isinstance(environment, str) or SHA256_RE.fullmatch(environment) is None
            or not isinstance(candidate_id, str) or not candidate_id
            or not isinstance(registry_sha, str) or SHA256_RE.fullmatch(registry_sha) is None
            or not isinstance(environment_payload, dict)
            or not isinstance(checks, dict)):
        raise ReleaseGateFailure("Identidad o matriz de checks inválida.")
    if set(checks) != REQUIRED_CHECKS:
        missing = sorted(REQUIRED_CHECKS - set(checks))
        extra = sorted(set(checks) - REQUIRED_CHECKS)
        detail = (["faltan " + ", ".join(missing)] if missing else []) + (
            ["sobran " + ", ".join(extra)] if extra else [])
        raise ReleaseGateFailure("Matriz de checks no exacta: " + "; ".join(detail))
    if _git(root, runner, "rev-parse", "HEAD") != commit:
        raise ReleaseGateFailure("HEAD no coincide con el candidato.")
    if _git(root, runner, "status", "--porcelain", "--untracked-files=all"):
        raise ReleaseGateFailure("El checkout no está limpio; no se agrega una release.")

    source_identity = f"{commit}+worktree.{source_sha}"
    if manifest.get("source_identity") != source_identity:
        raise ReleaseGateFailure("source_identity no deriva exactamente de commit y fuente.")
    context = {
        "schema_version": 1, "candidate_id": candidate_id, "git_commit": commit,
        "source_sha256": source_sha, "source_identity": source_identity, "image_id": image_id,
        "environment_fingerprint": environment, "commands_registry_sha256": registry_sha,
        "environment": environment_payload,
    }
    try:
        context_validator(context, root)
    except candidate_context.CandidateFailure as exc:
        raise ReleaseGateFailure(f"El contexto candidato actual no coincide: {exc}") from exc
    accepted = []
    for name in sorted(REQUIRED_CHECKS):
        reference = checks.get(name)
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise ReleaseGateFailure(f"Referencia de evidencia inválida: {name}")
        relative = reference["path"]
        expected_hash = reference["sha256"]
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts or not isinstance(expected_hash, str)
                or SHA256_RE.fullmatch(expected_hash) is None):
            raise ReleaseGateFailure(f"Ruta/hash de evidencia inválidos: {name}")
        path = _regular_confined(evidence_root / relative, evidence_root, f"evidencia {name}")
        record, raw = _strict_json(path, f"Evidencia {name}")
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ReleaseGateFailure(f"Hash de evidencia distinto: {name}")
        if (record.get("command") != name or record.get("passed") is not True
                or record.get("exit_code") != 0 or record.get("git_commit") != commit
                or record.get("source_sha256") != source_sha
                or record.get("source_identity") != source_identity
                or record.get("image_id") != image_id
                or record.get("environment_fingerprint") != environment
                or record.get("candidate_id") != candidate_id
                or record.get("commands_registry_sha256") != registry_sha):
            raise ReleaseGateFailure(f"Evidencia no aprobada o de otro candidato: {name}")
        log_relative = record.get("log")
        log_hash = record.get("log_sha256")
        log_bytes = record.get("log_bytes")
        if (not isinstance(log_relative, str) or not log_relative
                or Path(log_relative).name != log_relative
                or not isinstance(log_hash, str) or SHA256_RE.fullmatch(log_hash) is None
                or isinstance(log_bytes, bool) or not isinstance(log_bytes, int) or log_bytes < 0):
            raise ReleaseGateFailure(f"Referencia de log inválida: {name}")
        log_path = _regular_confined(evidence_root / log_relative, evidence_root, f"log de {name}")
        try:
            log_raw = log_path.read_bytes()
        except OSError as exc:
            raise ReleaseGateFailure(f"No se pudo leer el log de {name}.") from exc
        if len(log_raw) != log_bytes or hashlib.sha256(log_raw).hexdigest() != log_hash:
            raise ReleaseGateFailure(f"Bytes/hash del log no coinciden: {name}")
        accepted.append({"command": name, "sha256": expected_hash, "path": relative})

    return {
        "passed": True,
        "candidate_id": candidate_id,
        "git_commit": commit,
        "source_identity": source_identity,
        "image_id": image_id,
        "environment_fingerprint": environment,
        "commands_registry_sha256": registry_sha,
        "checks": accepted,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(aggregate(args.manifest), ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except ReleaseGateFailure as exc:
        print(f"RELEASE GATE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
