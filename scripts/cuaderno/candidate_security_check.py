#!/usr/bin/env python3
"""Scan one exact candidate, generate its strict proofs, and assess findings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

try:
    from . import (candidate_context, candidate_image_archive_check,
                   image_archive_audit, image_security_assessment as security)
except ImportError:
    import candidate_context
    import candidate_image_archive_check
    import image_archive_audit
    import image_security_assessment as security


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COUNTS = {"python-release": 6, "poplib-backport": 1, "alpine-backports": 4}


class CandidateSecurityFailure(ValueError):
    pass


def _write_new(path: Path, value: dict) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
    except OSError as exc:
        raise CandidateSecurityFailure(f"No se pudo conservar {path.name}.") from exc


def _proof_metadata(runtime: dict) -> dict[str, dict]:
    alpine = runtime.get("alpine_provenance")
    if (not isinstance(alpine, dict) or alpine.get("schema_version") != 1
            or alpine.get("verified") is not True):
        raise CandidateSecurityFailure("La sonda no devolvió procedencia Alpine estricta.")
    alpine = {key: value for key, value in alpine.items() if key not in {"schema_version", "verified"}}
    alpine["license_urls"] = {
        "busybox": "https://git.busybox.net/busybox/tree/LICENSE",
        "zlib": "https://zlib.net/zlib_license.html",
    }
    if not security._valid_alpine_metadata(alpine):
        raise CandidateSecurityFailure("La procedencia Alpine no satisface la política exacta.")
    return {
        "python-release": {**security.PYTHON_RELEASE,
                           "cves": sorted(security.PYTHON_RELEASE_CVES)},
        "poplib-backport": {
            "cve": security.patch_runtime_security.CVE,
            "upstream_commit": security.patch_runtime_security.UPSTREAM_COMMIT,
            "original_sha256": security.patch_runtime_security.ORIGINAL_SHA256,
            "patched_sha256": security.patch_runtime_security.PATCHED_SHA256,
            "original_url": security.patch_runtime_security.ORIGINAL_URL,
            "patched_url": security.patch_runtime_security.PATCHED_URL,
            "commit_url": security.patch_runtime_security.COMMIT_URL,
            "license_url": security.patch_runtime_security.LICENSE_URL,
        },
        "alpine-backports": alpine,
    }


def _generate_proofs(*, report_path: Path, scan: dict, runtime: dict,
                     root: Path, prefix: str) -> list[Path]:
    report, _raw = security._strict(report_path, "El informe Grype candidato")
    source_input = report.get("source", {}).get("target", {}).get("userInput")
    allowed_inputs = {image_archive_audit.CONTAINER_ARCHIVE_INPUT,
                      image_archive_audit.CONTAINER_ARCHIVE_INPUT.removeprefix('docker-archive:')}
    if source_input not in allowed_inputs:
        raise CandidateSecurityFailure("El informe candidato no usa el archivo aislado fijado.")
    try:
        matches, ignored, _severities = image_archive_audit._validate_archive_report(
            report, binding=scan["archive_binding"], source_input=source_input)
    except (KeyError, TypeError, image_archive_audit.shared.ImageAuditFailure) as exc:
        raise CandidateSecurityFailure("El informe candidato no coincide con su archivo.") from exc
    if ignored != [] or len(matches) != 11:
        raise CandidateSecurityFailure("El informe debe conservar exactamente 11 hallazgos y ningún ignoredMatch.")
    grouped = {kind: [] for kind in security.PROOF_KINDS}
    seen = set()
    for match in matches:
        fingerprint = security.match_fingerprint(match)
        digest = fingerprint["sha256"]
        if digest in seen:
            raise CandidateSecurityFailure("El informe candidato contiene una huella duplicada.")
        seen.add(digest)
        grouped[security._classify(fingerprint)].append(digest)
    if {kind: len(rows) for kind, rows in grouped.items()} != EXPECTED_COUNTS:
        raise CandidateSecurityFailure("La composición de los 11 hallazgos no coincide con la política.")
    metadata = _proof_metadata(runtime)
    evidence = (root / ".cuaderno-runs").resolve(strict=True)
    paths = []
    for kind in sorted(grouped):
        path = evidence / f"{prefix}-proof-{kind}.json"
        _write_new(path, {"schema_version": 1, "kind": kind,
                          "metadata": metadata[kind], "fingerprints": sorted(grouped[kind])})
        paths.append(path)
    return paths


def run(context_path: Path, *, root: Path = ROOT,
        context_validator=candidate_context.same_candidate,
        scanner=candidate_image_archive_check.run,
        runtime_probe=security.docker_runtime_probe, assessor=security.assess) -> dict:
    root = root.resolve(strict=True)
    context_file = security._regular(context_path, root, "el contexto candidato", direct=True)
    context, _raw = security._strict(context_file, "El contexto candidato")
    context_validator(context, root)
    status, scan_record = scanner(context_file, root=root, context_validator=context_validator)
    scan = scan_record.get("scan") if isinstance(scan_record, dict) else None
    if (status != 2 or not isinstance(scan, dict) or scan.get("status") != "findings"
            or scan.get("scanner_exit") != 2 or scan_record.get("candidate_id") != context.get("candidate_id")
            or scan_record.get("image_id") != context.get("image_id")
            or scan_record.get("source_identity") != context.get("source_identity")):
        raise CandidateSecurityFailure("El scan candidato debe retener findings exactos con exit 2.")
    try:
        archive = security._regular(root / scan_record["archive"], root, "el archivo candidato")
        report_path = security._regular(root / scan["paths"]["report"], root, "el informe candidato")
        summary_path = security._regular(root / scan["paths"]["summary"], root, "el resumen candidato")
    except (KeyError, TypeError) as exc:
        raise CandidateSecurityFailure("El scan candidato no declaró sus rutas exactas.") from exc
    if security._sha(archive) != scan_record.get("archive_sha256"):
        raise CandidateSecurityFailure("El archivo candidato cambió tras el scan.")
    context_validator(context, root)
    runtime = runtime_probe(context, root=root)
    nonce = uuid.uuid4().hex[:12]
    prefix = f"candidate-security-{str(context['candidate_id'])[:8]}-{nonce}"
    proof_paths = _generate_proofs(report_path=report_path, scan=scan, runtime=runtime,
                                   root=root, prefix=prefix)
    output = root / ".cuaderno-runs" / f"{prefix}-assessment.json"
    result = assessor(
        context_path=context_file, archive=archive, report_path=report_path,
        summary_path=summary_path, proof_paths=proof_paths, output_path=output,
        root=root, context_validator=context_validator,
        runtime_probe=lambda _context, *, root: runtime,
    )
    context_validator(context, root)
    if (not output.is_file() or result.get("status") != security.ASSESSMENT_POLICY
            or result.get("raw_scanner_exit") != 2):
        raise CandidateSecurityFailure("La evaluación final no conservó findings revisados.")
    return {
        "schema_version": 1, "status": result["status"], "raw_scanner_exit": 2,
        "candidate_id": context["candidate_id"], "image_id": context["image_id"],
        "source_identity": context["source_identity"],
        "archive": archive.relative_to(root).as_posix(),
        "archive_sha256": scan_record["archive_sha256"],
        "proofs": [{"path": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in proof_paths],
        "assessment": output.relative_to(root).as_posix(),
        "assessment_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path)
    args = parser.parse_args(argv)
    try:
        raw_context = args.context or os.environ.get('CUADERNO_CANDIDATE_CONTEXT')
        if not raw_context:
            raise CandidateSecurityFailure('Falta el contexto candidato.')
        result = run(Path(raw_context))
        print("CUADERNO_CANDIDATE_SECURITY " + json.dumps(result, sort_keys=True))
        return 0
    except (CandidateSecurityFailure, candidate_context.CandidateFailure,
            candidate_image_archive_check.CandidateArchiveFailure,
            image_archive_audit.shared.ImageAuditFailure, security.AssessmentFailure,
            OSError, RuntimeError, UnicodeError, KeyError, TypeError) as exc:
        print(f"CUADERNO_CANDIDATE_SECURITY ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
