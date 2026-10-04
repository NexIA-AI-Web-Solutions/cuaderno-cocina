"""Verify candidate restore or prior-release rollback only in retained new namespaces."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys

try:
    from . import candidate_context
except ImportError:
    import candidate_context


ROOT = Path(__file__).resolve().parents[2]
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class CandidateRecoveryFailure(ValueError):
    pass


def load_context(root: Path, supplied: Path | None) -> tuple[Path, dict]:
    raw = supplied or (Path(os.environ["CUADERNO_CANDIDATE_CONTEXT"])
                       if "CUADERNO_CANDIDATE_CONTEXT" in os.environ else None)
    if raw is None:
        raise CandidateRecoveryFailure("Falta el contexto candidato.")
    path = raw if raw.is_absolute() else root / raw
    evidence = (root / ".cuaderno-runs").resolve(strict=True)
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != evidence:
        raise CandidateRecoveryFailure("El contexto debe estar directamente en .cuaderno-runs.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateRecoveryFailure("Contexto candidato inválido.") from exc
    if not isinstance(value, dict) or IMAGE_RE.fullmatch(str(value.get("image_id"))) is None:
        raise CandidateRecoveryFailure("Contexto candidato inválido.")
    return path, value


def prior_bundle(root: Path, raw: str | None) -> Path:
    if not raw:
        raise CandidateRecoveryFailure("Define CUADERNO_PRIOR_RELEASE_BUNDLE.")
    backup_root = (root / "data/cuaderno/backups").resolve(strict=True)
    path = Path(raw)
    lexical = path if path.is_absolute() else root / path
    if lexical.is_symlink() or bool(getattr(lexical, "is_junction", lambda: False)()):
        raise CandidateRecoveryFailure("El bundle previo no puede ser un enlace.")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise CandidateRecoveryFailure("El bundle previo no existe.") from exc
    if not resolved.is_dir() or not resolved.is_relative_to(backup_root):
        raise CandidateRecoveryFailure("El bundle previo debe estar dentro de data/cuaderno/backups.")
    for name in ("manifest.json", "database.dump", "media.tar"):
        member = resolved / name
        if member.is_symlink() or not member.is_file():
            raise CandidateRecoveryFailure(f"Bundle previo incompleto: {name}")
    return resolved


def _default_restore_dependencies():
    os.environ["CUADERNO_BACKUP_TARGET"] = "release"
    package = f"{__package__}." if __package__ else ""
    backup = importlib.import_module(package + "delivery_backup")
    restore = importlib.import_module(package + "delivery_restore")
    if backup.CONTAINER != "cuaderno-release-db" or backup.WEB != "cuaderno-release-web":
        raise CandidateRecoveryFailure("El backup actual no apunta al preview release fijado.")
    return backup.create_backup, restore.restore


def _default_rollback(bundle: Path):
    package = f"{__package__}." if __package__ else ""
    module = importlib.import_module(package + "delivery_rollback")
    return module.rollback(bundle)


def restore_candidate(context: dict, *, root: Path, backup_creator=None, restore_runner=None) -> dict:
    if backup_creator is None or restore_runner is None:
        backup_creator, restore_runner = _default_restore_dependencies()
    bundle = Path(backup_creator())
    manifest_path = bundle / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateRecoveryFailure("El backup candidato no produjo un manifest válido.") from exc
    if (manifest.get("image_id") != context["image_id"]
            or manifest.get("checkout_source", {}).get("sha256") != context.get("source_sha256")
            or manifest.get("source_target") != "release"):
        raise CandidateRecoveryFailure("El backup no pertenece a la imagen/fuente del candidato release.")
    report = restore_runner(bundle)
    if not isinstance(report, dict) or report.get("passed") is not True:
        raise CandidateRecoveryFailure("La restauración candidata no quedó verificada.")
    return {"mode": "candidate-round-trip", "bundle": str(bundle.relative_to(root)),
            "image_id": context["image_id"], "restore": report}


def rollback_prior(context: dict, *, root: Path, bundle: Path, rollback_runner=None) -> dict:
    manifest_path = bundle / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateRecoveryFailure("Manifest previo inválido.") from exc
    prior_image = manifest.get("image_id")
    if IMAGE_RE.fullmatch(str(prior_image)) is None or prior_image == context["image_id"]:
        raise CandidateRecoveryFailure("Rollback exige una imagen previa exacta distinta del candidato.")
    report = (rollback_runner or _default_rollback)(bundle)
    if (not isinstance(report, dict) or report.get("passed") is not True
            or report.get("image_id") != prior_image
            or report.get("mode") != "isolated-full-restore-not-live-downgrade"):
        raise CandidateRecoveryFailure("El rollback previo no quedó verificado en namespace aislado.")
    return {"mode": "prior-release-rollback", "bundle": str(bundle.relative_to(root)),
            "candidate_image_id": context["image_id"], "prior_image_id": prior_image,
            "rollback": report}


def run(mode: str, context_path: Path | None = None, *, root: Path = ROOT,
        context_validator=candidate_context.same_candidate, backup_creator=None,
        restore_runner=None, rollback_runner=None, prior_bundle_value: str | None = None) -> dict:
    root = root.resolve(strict=True)
    if os.environ.get("CUADERNO_ENV", "").lower() not in {"local", "test", "development"}:
        raise CandidateRecoveryFailure("Recovery candidato solo opera en local/test/development.")
    _path, context = load_context(root, context_path)
    context_validator(context, root)
    if mode == "restore":
        report = restore_candidate(context, root=root, backup_creator=backup_creator,
                                   restore_runner=restore_runner)
    elif mode == "rollback":
        bundle = prior_bundle(root, prior_bundle_value or os.environ.get("CUADERNO_PRIOR_RELEASE_BUNDLE"))
        report = rollback_prior(context, root=root, bundle=bundle, rollback_runner=rollback_runner)
    else:
        raise CandidateRecoveryFailure("Modo recovery desconocido.")
    context_validator(context, root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("restore", "rollback"))
    parser.add_argument("--context", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.mode, args.context), ensure_ascii=False, sort_keys=True))
        return 0
    except (CandidateRecoveryFailure, candidate_context.CandidateFailure, OSError, RuntimeError,
            KeyError, ValueError) as exc:
        print(f"ERROR candidate recovery: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
