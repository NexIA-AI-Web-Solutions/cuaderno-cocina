"""Export and scan the immutable candidate image once with the pinned Linux scanner."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

try:
    from . import candidate_context, image_archive_audit
except ImportError:
    import candidate_context
    import image_archive_audit


ROOT = Path(__file__).resolve().parents[2]
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class CandidateArchiveFailure(ValueError):
    pass


def _context_path(root: Path, supplied: Path | None) -> Path:
    raw = supplied or (Path(os.environ["CUADERNO_CANDIDATE_CONTEXT"])
                       if "CUADERNO_CANDIDATE_CONTEXT" in os.environ else None)
    if raw is None:
        raise CandidateArchiveFailure("Falta el contexto candidato.")
    path = raw if raw.is_absolute() else root / raw
    evidence = (root / ".cuaderno-runs").resolve(strict=True)
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != evidence:
        raise CandidateArchiveFailure("El contexto debe ser un archivo regular directo de .cuaderno-runs.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateArchiveFailure("Contexto candidato inválido.") from exc
    if not isinstance(value, dict):
        raise CandidateArchiveFailure("Contexto candidato inválido.")
    return path, value


def export_image(image_id: str, destination: Path, *, root: Path) -> None:
    with destination.open("xb") as stream:
        result = subprocess.run(["docker", "image", "save", image_id], cwd=root, stdout=stream,
                                stderr=subprocess.PIPE, check=False, timeout=3600)
    if result.returncode:
        raise RuntimeError(
            f"docker image save falló ({result.returncode}); archivo parcial retenido: {destination.name}"
        )


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(context_path: Path | None = None, *, root: Path = ROOT,
        context_validator=candidate_context.same_candidate, exporter=export_image,
        auditor=image_archive_audit.run_archive_audit) -> tuple[int, dict]:
    root = root.resolve(strict=True)
    if os.environ.get("CUADERNO_ENV", "").lower() not in {"local", "test", "development"}:
        raise CandidateArchiveFailure("El escaneo candidato solo opera en local/test/development.")
    _path, context = _context_path(root, context_path)
    context_validator(context, root)
    image_id, source = context.get("image_id"), context.get("source_identity")
    if IMAGE_RE.fullmatch(str(image_id)) is None or not isinstance(source, str):
        raise CandidateArchiveFailure("El contexto no contiene imagen/fuente válidas.")
    scan_root = root / "data/cuaderno/scans"
    if scan_root.is_symlink() or bool(getattr(scan_root, "is_junction", lambda: False)()):
        raise CandidateArchiveFailure("La raíz de scans no puede ser un enlace.")
    scan_root.mkdir(parents=True, exist_ok=True)
    if not scan_root.resolve().is_relative_to(root):
        raise CandidateArchiveFailure("La raíz de scans sale del workspace.")
    directory = scan_root / f"candidate-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    directory.mkdir(mode=0o700, exist_ok=False)
    archive = directory / "image.tar"
    exporter(image_id, archive, root=root)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size == 0:
        raise CandidateArchiveFailure("La exportación no produjo un archivo regular no vacío.")
    archive_hash = sha256(archive)
    context_validator(context, root)
    metadata = {
        "schema_version": 1, "candidate_id": context.get("candidate_id"),
        "image_id": image_id, "source_identity": source,
        "archive": archive.relative_to(root).as_posix(), "archive_sha256": archive_hash,
    }
    (directory / "candidate-archive.json").write_text(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    status, summary = auditor(
        archive=archive, image_id=image_id, source_ref=source,
        expected_archive_sha256=archive_hash, root=root,
    )
    context_validator(context, root)
    return status, {**metadata, "scan": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path)
    args = parser.parse_args()
    try:
        status, report = run(args.context)
        print("CUADERNO_CANDIDATE_IMAGE_SCAN " + json.dumps(report, ensure_ascii=False, sort_keys=True))
        return status
    except (CandidateArchiveFailure, candidate_context.CandidateFailure, OSError, RuntimeError,
            image_archive_audit.shared.ImageAuditFailure) as exc:
        print(f"ERROR candidate image scan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
