#!/usr/bin/env python3
"""Audit the exact running local release image with pinned offline Grype."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "cuaderno-release-web"
GRYPE_VERSION = "0.119.0"
GRYPE_COMMIT = "b6f5194537747ee7f705f4113069ac9eb269919f"
GRYPE_SHA256 = "5fa9104fb0630b9cd8049b12cb7b29713ce58fcaf586a26b3ad93d418982a52c"
GRYPE_ZIP_SHA256 = "1db5c23b8ba0038a04acebed9c17945e1ade68d9f83e2fe1c101e4fb1feb9a48"
VULNERABILITY_DB_SHA256 = "04d141a255a18805a25dae81566dd3696c551be38bfe17929fd1008b338228d4"
DB_DIGEST = "xxh64:8803575133ab5141"
DB_CLIENT_VERSION = "v6.1.9"
DB_SOURCE = (
    "https://grype.anchore.io/databases/v6/"
    "vulnerability-db_v6.1.9_2026-09-30T00:35:37Z_1790749967.tar.zst"
    "?checksum=sha256%3Aac0db74474a11c2850db2376e4838c1bc5444097d21b277ad9dec767b6d39869"
)
MAX_REPORT_BYTES = 128 * 1024 * 1024
SHORT_TIMEOUT_SECONDS = 30
SAVE_TIMEOUT_SECONDS = 900
SCAN_TIMEOUT_SECONDS = 1800
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_RE = re.compile(r"^[0-9a-f]{40}(?:\+worktree\.[0-9a-f]{64})?$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
ALLOWED_ENVIRONMENTS = frozenset({"local", "test", "dev"})


class ImageAuditFailure(RuntimeError):
    """Fail-closed error safe to show without subprocess output."""


class AuditPaths(NamedTuple):
    root: Path
    tool: Path
    zip_archive: Path
    db_root: Path
    db_stamp: Path
    database: Path
    scan_root: Path
    scan_dir: Path
    archive: Path
    report: Path
    summary: Path


def audit_paths(root, scan_id):
    root = Path(root)
    scan_root = root / "data/cuaderno/scans"
    scan_dir = scan_root / scan_id
    tool_root = root / "data/cuaderno/tooling/grype-0.119.0"
    db_root = root / "data/cuaderno/tooling/grype-db"
    return AuditPaths(
        root, tool_root / "grype.exe", tool_root / "grype_0.119.0_windows_amd64.zip",
        db_root, db_root / "6/import.json", db_root / "6/vulnerability.db",
        scan_root, scan_dir, scan_dir / "image.tar", scan_dir / "grype.json", scan_dir / "summary.json",
    )


def _is_linklike(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _contained(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _reject_link_ancestors(path: Path, root: Path) -> None:
    current = path
    while True:
        if current.exists() and _is_linklike(current):
            raise ImageAuditFailure("Una ruta del audit atraviesa un enlace o junction.")
        if current == root:
            return
        if current.parent == current:
            raise ImageAuditFailure("Una ruta del audit sale del proyecto.")
        current = current.parent


def validate_paths(paths, *, expected_root):
    root = Path(expected_root).resolve(strict=True)
    if Path(paths.root).resolve(strict=True) != root:
        raise ImageAuditFailure("La raíz del audit no es el workspace fijado.")
    scan_id = Path(paths.scan_dir).name
    if UUID_RE.fullmatch(scan_id) is None:
        raise ImageAuditFailure("El identificador de scan no es un UUID v4 canónico.")
    expected = audit_paths(root, scan_id)
    for field in AuditPaths._fields[1:]:
        supplied = Path(getattr(paths, field))
        fixed = Path(getattr(expected, field))
        if supplied != fixed or not _contained(supplied, root):
            raise ImageAuditFailure("Una ruta no coincide con el destino fijo del proyecto.")
        _reject_link_ancestors(supplied, root)
    for required in (paths.tool, paths.zip_archive, paths.db_stamp, paths.database):
        required = Path(required)
        if not required.is_file() or _is_linklike(required):
            raise ImageAuditFailure("Falta un artefacto local regular requerido por el audit.")
    if Path(paths.scan_dir).exists():
        raise ImageAuditFailure("El directorio UUID del scan ya existe; no se sobrescribe.")
    return paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ImageAuditFailure("No se pudo leer un artefacto del audit.") from exc
    return digest.hexdigest()


def _regular_nonempty(path: Path, label: str) -> bool:
    try:
        return path.is_file() and not _is_linklike(path) and path.stat().st_size > 0
    except OSError as exc:
        raise ImageAuditFailure(f"No se pudo verificar {label} de forma estable.") from exc


def _strict_json_bytes(raw: bytes, label: str):
    def reject_constant(token):
        raise ValueError(token)

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ImageAuditFailure(f"{label} no es JSON UTF-8 estricto.") from exc


def _read_json_file(path: Path, *, limit: int, label: str):
    if not path.is_file() or _is_linklike(path):
        raise ImageAuditFailure(f"{label} no es un archivo regular.")
    try:
        size = path.stat().st_size
        if not 0 < size <= limit:
            raise ImageAuditFailure(f"{label} está vacío o supera el límite.")
        raw = path.read_bytes()
    except OSError as exc:
        raise ImageAuditFailure(f"No se pudo leer {label}.") from exc
    if len(raw) != size:
        raise ImageAuditFailure(f"{label} cambió durante la lectura.")
    return _strict_json_bytes(raw, label), raw


def _completed(runner, argv, *, timeout, env=None):
    try:
        return runner(
            argv, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="strict", env=env, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ImageAuditFailure("No se pudo ejecutar una herramienta local requerida.") from exc


def validate_container_document(document):
    if not isinstance(document, list) or len(document) != 1 or not isinstance(document[0], dict):
        raise ImageAuditFailure("docker inspect no devolvió un contenedor unívoco.")
    container = document[0]
    state = container.get("State")
    host_config = container.get("HostConfig")
    bindings = host_config.get("PortBindings") if isinstance(host_config, dict) else None
    if (container.get("Name") != f"/{CONTAINER}"
            or not isinstance(container.get("Image"), str) or IMAGE_RE.fullmatch(container["Image"]) is None
            or not isinstance(state, dict) or state.get("Running") is not True or state.get("Status") != "running"
            or bindings != {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]}):
        raise ImageAuditFailure("El contenedor release exacto no está ejecutándose de forma verificable.")
    return container


def _verify_grype(paths, runner, expected_tool_hash, expected_zip_hash):
    _verify_grype_hashes(paths, expected_tool_hash, expected_zip_hash)
    completed = _completed(runner, [str(paths.tool), "version"], timeout=SHORT_TIMEOUT_SECONDS)
    output = completed.stdout or ""
    if (completed.returncode != 0
            or re.search(r"(?m)^Version:\s*0\.119\.0\s*$", output) is None
            or re.search(rf"(?m)^GitCommit:\s*{re.escape(GRYPE_COMMIT)}\s*$", output) is None):
        raise ImageAuditFailure("La versión/commit del scanner local no coincide con el pin.")
    _verify_grype_hashes(paths, expected_tool_hash, expected_zip_hash)


def _verify_grype_hashes(paths, expected_tool_hash, expected_zip_hash):
    if _sha256(paths.tool) != expected_tool_hash or _sha256(paths.zip_archive) != expected_zip_hash:
        raise ImageAuditFailure("Los hashes de Grype no coinciden con el release oficial fijado.")


def _inspect_container(runner):
    completed = _completed(runner, ["docker", "inspect", CONTAINER], timeout=SHORT_TIMEOUT_SECONDS)
    if completed.returncode != 0:
        raise ImageAuditFailure("No se pudo inspeccionar el contenedor release exacto.")
    return validate_container_document(_strict_json_bytes((completed.stdout or "").encode(), "docker inspect"))


def _source_identity(runner, image_id):
    completed = _completed(runner, [
        "docker", "exec", CONTAINER, "/opt/recipes/venv/bin/python", "-c",
        "from cookbook.version_info import TANDOOR_REF; print(TANDOOR_REF)",
    ], timeout=SHORT_TIMEOUT_SECONDS)
    source_ref = (completed.stdout or "").strip()
    if completed.returncode != 0 or SOURCE_RE.fullmatch(source_ref) is None:
        raise ImageAuditFailure("La imagen no expone un TANDOOR_REF verificable.")
    image = _completed(runner, ["docker", "image", "inspect", image_id], timeout=SHORT_TIMEOUT_SECONDS)
    if image.returncode != 0:
        raise ImageAuditFailure("No se pudo inspeccionar el Image ID exacto.")
    document = _strict_json_bytes((image.stdout or "").encode(), "docker image inspect")
    if not isinstance(document, list) or len(document) != 1 or document[0].get("Id") != image_id:
        raise ImageAuditFailure("docker image inspect no corresponde al Image ID del contenedor.")
    config = document[0].get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    labels = {} if labels is None else labels
    if not isinstance(labels, dict):
        raise ImageAuditFailure("Las labels de la imagen no son un objeto.")
    if labels.get("SourceCommit") is not None and labels["SourceCommit"] != source_ref:
        raise ImageAuditFailure("SourceCommit de la imagen contradice TANDOOR_REF.")
    return source_ref


def _db_stamp(paths):
    document, _raw = _read_json_file(paths.db_stamp, limit=64 * 1024, label="DB stamp")
    if (not isinstance(document, dict) or document != {
            "digest": DB_DIGEST, "source": DB_SOURCE, "client_version": DB_CLIENT_VERSION,
    }):
        raise ImageAuditFailure("El DB stamp local de Grype es inválido.")
    if not _regular_nonempty(paths.database, "la base local de vulnerabilidades"):
        raise ImageAuditFailure("La base local de vulnerabilidades está vacía.")
    return document


def _offline_environment(paths, inherited):
    environment = {
        "GRYPE_DB_CACHE_DIR": str(paths.db_root),
        "GRYPE_CHECK_FOR_APP_UPDATE": "false",
        "GRYPE_DB_AUTO_UPDATE": "false",
        "GRYPE_EXTERNAL_SOURCES_ENABLE": "false",
    }
    for key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = inherited.get(key)
        if isinstance(value, str) and value:
            environment[key] = value
    return environment


def _verify_db_status(paths, runner, environment):
    completed = _completed(
        runner, [str(paths.tool), "db", "status", "-o", "json"],
        timeout=SHORT_TIMEOUT_SECONDS, env=environment,
    )
    if completed.returncode != 0:
        raise ImageAuditFailure("Grype no pudo verificar su base offline fijada.")
    document = _strict_json_bytes((completed.stdout or "").encode(), "grype db status")
    location = document.get("location") if isinstance(document, dict) else None
    if (not isinstance(document, dict) or document.get("schemaVersion") != 6
            or document.get("error") is not None or not isinstance(location, str)
            or Path(location).resolve(strict=False) != paths.database.resolve(strict=True)):
        raise ImageAuditFailure("grype db status no corresponde a la base local fijada.")
    return document


def _validate_report(document, *, image_id, source_input):
    if not isinstance(document, dict):
        raise ImageAuditFailure("El informe Grype no es un objeto JSON.")
    matches = document.get("matches")
    ignored = document.get("ignoredMatches")
    descriptor = document.get("descriptor")
    source = document.get("source")
    target = source.get("target") if isinstance(source, dict) else None
    if (not isinstance(matches, list) or not all(isinstance(row, dict) for row in matches)
            or ignored != []
            or not isinstance(descriptor, dict) or descriptor.get("name") != "grype"
            or descriptor.get("version") != GRYPE_VERSION
            or not isinstance(source, dict) or source.get("type") != "image"
            or not isinstance(target, dict) or target.get("imageID") != image_id
            or target.get("userInput") != source_input):
        raise ImageAuditFailure("El informe no corresponde al scanner y la imagen exactos.")
    severities = Counter()
    for match in matches:
        vulnerability = match.get("vulnerability")
        severity = vulnerability.get("severity") if isinstance(vulnerability, dict) else None
        if not isinstance(severity, str) or not severity:
            raise ImageAuditFailure("Un hallazgo no conserva su severidad original.")
        severities[severity] += 1
    return matches, ignored, dict(sorted(severities.items()))


def run_audit(*, root=ROOT, scan_id=None, runner=subprocess.run, environ=None,
              expected_tool_hash=GRYPE_SHA256, expected_zip_hash=GRYPE_ZIP_SHA256,
              expected_db_hash=VULNERABILITY_DB_SHA256):
    environment = dict(os.environ if environ is None else environ)
    if environment.get("CUADERNO_ENV") not in ALLOWED_ENVIRONMENTS:
        raise ImageAuditFailure("CUADERNO_ENV debe ser local, test o dev.")
    if any(key in environment for key in ("CUADERNO_IMAGE", "CUADERNO_CONTAINER", "CUADERNO_SCAN_DIR")):
        raise ImageAuditFailure("No se admiten destinos por entorno.")
    scan_id = scan_id or str(uuid.uuid4())
    paths = validate_paths(audit_paths(Path(root).resolve(), scan_id), expected_root=Path(root))
    _verify_grype(paths, runner, expected_tool_hash, expected_zip_hash)
    container = _inspect_container(runner)
    image_id = container["Image"]
    source_ref = _source_identity(runner, image_id)
    if _inspect_container(runner)["Image"] != image_id:
        raise ImageAuditFailure("El contenedor release cambió de imagen durante el preflight.")
    db_stamp = _db_stamp(paths)
    database_hash = _sha256(paths.database)
    if database_hash != expected_db_hash:
        raise ImageAuditFailure("La base local de vulnerabilidades no coincide con su SHA-256 fijado.")
    scanner_environment = _offline_environment(paths, environment)
    _verify_db_status(paths, runner, scanner_environment)
    try:
        paths.scan_root.mkdir(parents=True, exist_ok=True)
        _reject_link_ancestors(paths.scan_root, paths.root.resolve(strict=True))
        paths.scan_dir.mkdir(exist_ok=False)
    except OSError as exc:
        raise ImageAuditFailure("No se pudo crear el directorio UUID nuevo del scan.") from exc
    save = _completed(
        runner, ["docker", "image", "save", "--output", str(paths.archive), image_id],
        timeout=SAVE_TIMEOUT_SECONDS,
    )
    if save.returncode != 0 or not _regular_nonempty(paths.archive, "el archivo de imagen"):
        raise ImageAuditFailure("docker image save no produjo el archivo regular esperado.")
    archive_hash = _sha256(paths.archive)
    source_input = f"docker-archive:{paths.archive}"
    _verify_grype_hashes(paths, expected_tool_hash, expected_zip_hash)
    scanner = _completed(runner, [
        str(paths.tool), "--fail-on", "negligible", "--scope", "squashed",
        "--output", "json", "--file", str(paths.report), source_input,
    ], env=scanner_environment, timeout=SCAN_TIMEOUT_SECONDS)
    if scanner.returncode not in {0, 2}:
        raise ImageAuditFailure("Grype terminó con un estado no admitido.")
    _verify_grype_hashes(paths, expected_tool_hash, expected_zip_hash)
    report, raw_report = _read_json_file(paths.report, limit=MAX_REPORT_BYTES, label="El informe Grype")
    matches, ignored, severity_counts = _validate_report(report, image_id=image_id, source_input=source_input)
    if scanner.returncode != (2 if matches else 0):
        raise ImageAuditFailure("El exit status de Grype contradice los hallazgos.")
    if _sha256(paths.archive) != archive_hash:
        raise ImageAuditFailure("El archivo de imagen cambió durante el scan.")
    if _sha256(paths.database) != database_hash:
        raise ImageAuditFailure("La base de vulnerabilidades cambió durante el scan.")
    final_container = _inspect_container(runner)
    if final_container["Image"] != image_id:
        raise ImageAuditFailure("El contenedor release cambió de imagen durante el scan.")
    relative = lambda path: path.relative_to(paths.root).as_posix()
    summary = {
        "status": "findings" if scanner.returncode == 2 else "clean",
        "scanner_exit": scanner.returncode,
        "image_id": image_id,
        "source_commit": source_ref,
        "grype": {"version": GRYPE_VERSION, "git_commit": GRYPE_COMMIT, "sha256": expected_tool_hash},
        "database": db_stamp,
        "matches": len(matches),
        "ignored_matches": len(ignored),
        "severity_counts": severity_counts,
        "archive_sha256": archive_hash,
        "report_sha256": hashlib.sha256(raw_report).hexdigest(),
        "paths": {"archive": relative(paths.archive), "report": relative(paths.report), "summary": relative(paths.summary)},
    }
    try:
        with paths.summary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(summary, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
    except OSError as exc:
        raise ImageAuditFailure("No se pudo conservar el resumen del scan.") from exc
    return scanner.returncode, summary


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments:
        raise ImageAuditFailure("Este audit no acepta rutas, imágenes ni argumentos.")
    status, summary = run_audit()
    print("CUADERNO_IMAGE_AUDIT " + json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImageAuditFailure as exc:
        print(f"CUADERNO_IMAGE_AUDIT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
