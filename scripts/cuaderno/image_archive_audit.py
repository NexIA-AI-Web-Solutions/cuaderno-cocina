#!/usr/bin/env python3
"""Scan one retained release image archive with the pinned offline Linux Grype."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from typing import NamedTuple
import uuid

try:
    from . import image_audit as shared
    from . import scanner_db_provenance
except ImportError:
    import image_audit as shared
    import scanner_db_provenance


ROOT = Path(__file__).resolve().parents[2]
LINUX_GRYPE_SHA256 = "e02ba25615668c6bae03473e3c6493b6dfffc2e4e419f65f9bd62555ac10cd0e"
LINUX_ARCHIVE_SHA256 = "3fa2dc4b924621ab65404cf08d0b8438d896d80ab949c9d5a4ca283c36004c9b"
SCANNER_IMAGE = (
    "node:24.21.0-bookworm-slim@"
    "sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6"
)
CONTAINER_TOOL = "/grype-tool/grype"
CONTAINER_DATABASE = "/grype-db/6/vulnerability.db"
CONTAINER_ARCHIVE_INPUT = "docker-archive:/scan-input/image.tar"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
MAX_ARCHIVE_MEMBERS = 20_000
MAX_OCI_JSON_BYTES = 4 * 1024 * 1024
MAX_OCI_DESCRIPTORS = 256


class ArchiveAuditPaths(NamedTuple):
    root: Path
    tool: Path
    zip_archive: Path
    db_root: Path
    db_stamp: Path
    database: Path
    scan_root: Path
    scan_dir: Path
    archive: Path
    scanner_dir: Path
    report: Path
    summary: Path


def _sha256(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise shared.ImageAuditFailure("No se pudo hashear un artefacto requerido.") from exc


def _strict_json(raw: bytes, label: str):
    if len(raw) > MAX_OCI_JSON_BYTES:
        raise shared.ImageAuditFailure(f"{label} supera el límite de metadatos OCI.")
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise shared.ImageAuditFailure(f"{label} no es JSON estricto.") from exc


def _digest(value) -> str:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise shared.ImageAuditFailure("Descriptor OCI con digest inválido.")
    return value


def _blob_name(digest: str) -> str:
    return "blobs/sha256/" + _digest(digest).removeprefix("sha256:")


def _archive_binding(archive: Path, *, image_id: str, source_ref: str) -> dict:
    """Bind a Docker 29 OCI archive to its selected Linux/amd64 config."""
    try:
        stream = tarfile.open(archive, mode="r:*")
    except (OSError, tarfile.TarError) as exc:
        raise shared.ImageAuditFailure("La imagen retenida no es un tar OCI legible.") from exc
    with stream:
        members = stream.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise shared.ImageAuditFailure("El tar OCI contiene demasiadas entradas.")
        indexed = {}
        for member in members:
            name = member.name
            parts = name.split("/")
            if (not name or name.startswith("/") or "\\" in name
                    or any(part in ("", ".", "..") for part in parts)):
                raise shared.ImageAuditFailure("El tar OCI contiene una ruta no confinada.")
            if name in indexed:
                raise shared.ImageAuditFailure("El tar OCI contiene entradas duplicadas.")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise shared.ImageAuditFailure("El tar OCI contiene enlaces o tipos no admitidos.")
            indexed[name] = member

        def read(name: str, label: str) -> bytes:
            member = indexed.get(name)
            if member is None or not member.isfile() or member.size > MAX_OCI_JSON_BYTES:
                raise shared.ImageAuditFailure(f"Falta {label} regular y acotado en el tar OCI.")
            extracted = stream.extractfile(member)
            if extracted is None:
                raise shared.ImageAuditFailure(f"No se pudo leer {label} del tar OCI.")
            raw = extracted.read(MAX_OCI_JSON_BYTES + 1)
            if len(raw) != member.size:
                raise shared.ImageAuditFailure(f"El tamaño de {label} no coincide con el tar OCI.")
            return raw

        oci_metadata = {name for name in ("oci-layout", "index.json") if name in indexed}
        if oci_metadata and oci_metadata != {"oci-layout", "index.json"}:
            raise shared.ImageAuditFailure("El tar contiene metadatos OCI parciales.")
        if not oci_metadata:
            docker_raw = read("manifest.json", "manifest.json")
            docker_manifest = _strict_json(docker_raw, "manifest.json")
            if (not isinstance(docker_manifest, list) or len(docker_manifest) != 1
                    or not isinstance(docker_manifest[0], dict)):
                raise shared.ImageAuditFailure("manifest.json debe describir una sola imagen Docker.")
            row = docker_manifest[0]
            config_name = row.get("Config")
            layers = row.get("Layers")
            if (not isinstance(config_name, str)
                    or re.fullmatch(r"[0-9a-f]{64}\.json", config_name) is None
                    or not isinstance(layers, list) or not all(isinstance(name, str) for name in layers)
                    or len(set(layers)) != len(layers)):
                raise shared.ImageAuditFailure("El manifest Docker no fija config y capas válidas.")
            config_digest = "sha256:" + config_name.removesuffix(".json")
            if image_id != config_digest:
                raise shared.ImageAuditFailure("El Image ID clásico no coincide con su config exacta.")
            config_raw = read(config_name, "config Docker")
            if "sha256:" + hashlib.sha256(config_raw).hexdigest() != config_digest:
                raise shared.ImageAuditFailure("El nombre de la config Docker no coincide con sus bytes.")
            config = _strict_json(config_raw, "config Docker")
            if (not isinstance(config, dict) or config.get("os") != "linux"
                    or config.get("architecture") != "amd64"):
                raise shared.ImageAuditFailure("La config Docker no es linux/amd64.")
            labels = config.get("config", {}).get("Labels")
            if not isinstance(labels, dict) or labels.get("io.cuaderno.source-identity") != source_ref:
                raise shared.ImageAuditFailure("La config Docker no conserva la identidad de fuente exacta.")
            for layer in layers:
                member = indexed.get(layer)
                if member is None or not member.isfile():
                    raise shared.ImageAuditFailure("El manifest Docker referencia una capa ausente o no regular.")
            manifest_digest = "sha256:" + hashlib.sha256(docker_raw).hexdigest()
            return {"format": "docker", "config_digest": config_digest,
                    "manifest_digest": manifest_digest,
                    "chain": [manifest_digest, config_digest]}

        layout = _strict_json(read("oci-layout", "oci-layout"), "oci-layout")
        if layout != {"imageLayoutVersion": "1.0.0"}:
            raise shared.ImageAuditFailure("La versión de oci-layout no está fijada.")
        root_raw = read("index.json", "index.json")
        root = _strict_json(root_raw, "index.json")
        if (not isinstance(root, dict) or root.get("schemaVersion") != 2
                or root.get("mediaType") != OCI_INDEX or not isinstance(root.get("manifests"), list)):
            raise shared.ImageAuditFailure("index.json no es un índice OCI v1.")

        visited, selected, descriptor_count = set(), [], 0

        def descriptor_blob(descriptor: dict, expected_media: set[str]):
            nonlocal descriptor_count
            descriptor_count += 1
            if descriptor_count > MAX_OCI_DESCRIPTORS or not isinstance(descriptor, dict):
                raise shared.ImageAuditFailure("La cadena OCI es ambigua o demasiado grande.")
            media = descriptor.get("mediaType")
            digest = _digest(descriptor.get("digest"))
            size = descriptor.get("size")
            if media not in expected_media or type(size) is not int or not 0 <= size <= MAX_OCI_JSON_BYTES:
                raise shared.ImageAuditFailure("Descriptor OCI con tipo o tamaño inválido.")
            raw = read(_blob_name(digest), f"blob {digest}")
            if len(raw) != size or "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
                raise shared.ImageAuditFailure("El hash o tamaño de un descriptor OCI no coincide.")
            return media, digest, raw

        def visit(descriptor: dict, chain: tuple[str, ...], depth: int):
            if depth > 4:
                raise shared.ImageAuditFailure("La cadena de índices OCI es demasiado profunda.")
            platform = descriptor.get("platform") if isinstance(descriptor, dict) else None
            if platform is not None and not isinstance(platform, dict):
                raise shared.ImageAuditFailure("Descriptor OCI con plataforma inválida.")
            if isinstance(platform, dict) and (platform.get("os"), platform.get("architecture")) not in {
                    ("linux", "amd64"), (None, None)}:
                return
            media, digest, raw = descriptor_blob(descriptor, {OCI_INDEX, OCI_MANIFEST})
            if digest in visited:
                raise shared.ImageAuditFailure("La cadena OCI contiene ciclos o descriptores repetidos.")
            visited.add(digest)
            document = _strict_json(raw, f"blob {digest}")
            if not isinstance(document, dict) or document.get("schemaVersion") != 2:
                raise shared.ImageAuditFailure("Descriptor OCI sin schemaVersion 2.")
            if media == OCI_INDEX:
                if document.get("mediaType") != OCI_INDEX or not isinstance(document.get("manifests"), list):
                    raise shared.ImageAuditFailure("Índice OCI inválido.")
                for child in document["manifests"]:
                    visit(child, chain + (digest,), depth + 1)
                return
            if document.get("mediaType") != OCI_MANIFEST or not isinstance(document.get("config"), dict):
                raise shared.ImageAuditFailure("Manifest OCI inválido.")
            _media, config_digest, config_raw = descriptor_blob(document["config"], {OCI_CONFIG})
            config = _strict_json(config_raw, f"config {config_digest}")
            if not isinstance(config, dict):
                raise shared.ImageAuditFailure("Config OCI inválida.")
            config_platform = (config.get("os"), config.get("architecture"))
            declared_platform = ((platform or {}).get("os"), (platform or {}).get("architecture"))
            if config_platform != ("linux", "amd64"):
                return
            if declared_platform not in {(None, None), ("linux", "amd64")}:
                raise shared.ImageAuditFailure("La plataforma OCI declarada contradice su config.")
            selected.append({"config": config, "config_digest": config_digest,
                             "manifest_digest": digest, "chain": chain + (digest, config_digest)})

        for descriptor in root["manifests"]:
            visit(descriptor, ("sha256:" + hashlib.sha256(root_raw).hexdigest(),), 0)
        configs = {row["config_digest"] for row in selected}
        if len(selected) != 1 or len(configs) != 1:
            raise shared.ImageAuditFailure("El tar debe resolver una única imagen linux/amd64.")
        binding = selected[0]
        if image_id not in binding["chain"]:
            raise shared.ImageAuditFailure("El Image ID no pertenece a la cadena OCI linux/amd64 exacta.")
        labels = binding["config"].get("config", {}).get("Labels")
        if not isinstance(labels, dict) or labels.get("io.cuaderno.source-identity") != source_ref:
            raise shared.ImageAuditFailure("La config OCI no conserva la identidad de fuente exacta.")

        docker_manifest = _strict_json(read("manifest.json", "manifest.json"), "manifest.json")
        expected_config = _blob_name(binding["config_digest"])
        if (not isinstance(docker_manifest, list) or len(docker_manifest) != 1
                or not isinstance(docker_manifest[0], dict)
                or docker_manifest[0].get("Config") != expected_config):
            raise shared.ImageAuditFailure("manifest.json no coincide con la config OCI seleccionada.")
        return {"format": "oci", "config_digest": binding["config_digest"],
                "manifest_digest": binding["manifest_digest"], "chain": list(binding["chain"])}


def _validate_archive_report(report, *, binding: dict, source_input: str):
    target = report.get("source", {}).get("target") if isinstance(report, dict) else None
    reported_input = target.get("userInput") if isinstance(target, dict) else None
    allowed_inputs = {source_input}
    if source_input.startswith("docker-archive:"):
        allowed_inputs.add(source_input.removeprefix("docker-archive:"))
    if reported_input not in allowed_inputs:
        raise shared.ImageAuditFailure("El informe no conserva la entrada exacta del archivo retenido.")
    # Grype 0.119 omits ignoredMatches when the fixed ignore policy matched
    # nothing. An explicit null or any non-empty/ill-typed value remains invalid.
    normalized = report
    if isinstance(report, dict) and "ignoredMatches" not in report:
        normalized = {**report, "ignoredMatches": []}
    return shared._validate_report(
        normalized, image_id=binding["config_digest"], source_input=reported_input,
    )


def archive_paths(root: Path, archive: Path) -> ArchiveAuditPaths:
    root = root.resolve(strict=True)
    lexical_scan_root = root / "data/cuaderno/scans"
    shared._reject_link_ancestors(lexical_scan_root, root)
    scan_root = lexical_scan_root.resolve(strict=True)
    requested = archive if archive.is_absolute() else root / archive
    shared._reject_link_ancestors(requested.absolute(), root)
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise shared.ImageAuditFailure("El archivo de imagen retenido no existe.") from exc
    if (not resolved.is_file()
            or not resolved.is_relative_to(scan_root) or resolved.name != "image.tar"):
        raise shared.ImageAuditFailure("La imagen debe ser image.tar regular dentro de data/cuaderno/scans.")
    scan_dir = resolved.parent
    tool_root = root / "data/cuaderno/tooling/grype-linux-0.119.0"
    db_root = root / "data/cuaderno/tooling/grype-db"
    paths = ArchiveAuditPaths(
        root, tool_root / "grype", tool_root / "grype_0.119.0_linux_amd64.tar.gz",
        db_root, db_root / "6/import.json", db_root / "6/vulnerability.db",
        scan_root, scan_dir, resolved, scan_dir / "linux-scanner",
        scan_dir / "linux-scanner/grype-linux.json", scan_dir / "linux-scanner/summary-linux.json",
    )
    for path in (paths.tool, paths.zip_archive, paths.db_stamp, paths.database):
        if not path.is_file() or path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise shared.ImageAuditFailure("Tooling Linux/DB ausente, enlazado o fuera del workspace.")
    if paths.scanner_dir.exists() or paths.report.exists() or paths.summary.exists():
        raise shared.ImageAuditFailure("El resultado Linux ya existe; no se sobrescribe.")
    return paths


def _mount(source: Path, target: str, *, readonly: bool) -> str:
    raw = str(source.resolve(strict=True))
    if any(character in raw for character in (",", "\n", "\r", "\x00")):
        raise shared.ImageAuditFailure("Una ruta del scanner no se puede expresar como mount seguro.")
    suffix = ",readonly" if readonly else ""
    return f"type=bind,source={raw},target={target}{suffix}"


class LinuxContainerRunner:
    """Translate only the three fixed Grype invocations into an offline Linux container."""

    source_input = CONTAINER_ARCHIVE_INPUT
    database_path = CONTAINER_DATABASE

    def __init__(self, paths: ArchiveAuditPaths, *, runner=subprocess.run,
                 cleanup_runner=subprocess.run):
        self.paths = paths
        self.runner = runner
        self.cleanup_runner = cleanup_runner

    def __call__(self, argv, **kwargs):
        host = list(map(str, argv))
        tool = str(self.paths.tool)
        if not host or host[0] != tool:
            raise shared.ImageAuditFailure("El runner Linux solo admite el Grype fijado.")
        arguments = host[1:]
        if arguments == ["version"]:
            guest = arguments
        elif arguments == ["db", "status", "-o", "json"]:
            guest = arguments
        elif arguments == [
            "--fail-on", "negligible", "--scope", "squashed", "--output", "json",
            "--file", str(self.paths.report), CONTAINER_ARCHIVE_INPUT,
        ]:
            guest = [
                "--fail-on", "negligible", "--scope", "squashed", "--output", "json",
                "--file", "/scanner-output/grype-linux.json", CONTAINER_ARCHIVE_INPUT,
            ]
        else:
            raise shared.ImageAuditFailure("Invocación Grype no incluida en el contrato portable.")
        container = f"cuaderno-grype-{uuid.uuid4().hex[:12]}"
        identity = (["--user", f"{os.getuid()}:{os.getgid()}"]
                    if hasattr(os, "getuid") and hasattr(os, "getgid") else [])
        command = [
            "docker", "run", "--rm", "--name", container,
            "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            *identity,
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=1g",
            "--mount", _mount(self.paths.tool.parent, "/grype-tool", readonly=True),
            "--mount", _mount(self.paths.db_root, "/grype-db", readonly=True),
            "--mount", _mount(self.paths.archive, "/scan-input/image.tar", readonly=True),
            "--mount", _mount(self.paths.scanner_dir, "/scanner-output", readonly=False),
            "-e", "GRYPE_DB_CACHE_DIR=/grype-db",
            "-e", "GRYPE_CHECK_FOR_APP_UPDATE=false",
            "-e", "GRYPE_DB_AUTO_UPDATE=false",
            "-e", "GRYPE_EXTERNAL_SOURCES_ENABLE=false",
            "-e", "HOME=/tmp", "-e", "XDG_CACHE_HOME=/tmp/.cache",
            "--entrypoint", CONTAINER_TOOL, SCANNER_IMAGE, *guest,
        ]
        try:
            return self.runner(
                command, cwd=self.paths.root, check=False, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                timeout=kwargs.get("timeout", shared.SCAN_TIMEOUT_SECONDS),
            )
        except subprocess.TimeoutExpired:
            try:
                self.cleanup_runner(
                    ["docker", "rm", "-f", container], cwd=self.paths.root, check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            raise


def run_archive_audit(*, archive: Path, image_id: str, source_ref: str,
                      expected_archive_sha256: str, root: Path = ROOT,
                      runner=None, environ=None, docker_runner=subprocess.run,
                      expected_tool_hash: str = LINUX_GRYPE_SHA256,
                      expected_tool_archive_hash: str = LINUX_ARCHIVE_SHA256,
                      expected_db_hash: str | None = None,
                      expected_db_receipt_sha256: str | None = None):
    environment = dict(os.environ if environ is None else environ)
    if environment.get("CUADERNO_ENV") not in shared.ALLOWED_ENVIRONMENTS:
        raise shared.ImageAuditFailure("CUADERNO_ENV debe ser local, test o dev.")
    if shared.IMAGE_RE.fullmatch(image_id or "") is None:
        raise shared.ImageAuditFailure("Image ID inválido.")
    if shared.SOURCE_RE.fullmatch(source_ref or "") is None:
        raise shared.ImageAuditFailure("Identidad de fuente inválida.")
    if (not isinstance(expected_archive_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_archive_sha256) is None):
        raise shared.ImageAuditFailure("SHA-256 esperado del archivo inválido.")

    paths = archive_paths(Path(root), Path(archive))
    initial_archive_hash = _sha256(paths.archive)
    if initial_archive_hash != expected_archive_sha256:
        raise shared.ImageAuditFailure("El archivo de imagen no coincide con su SHA-256 esperado.")
    binding = _archive_binding(paths.archive, image_id=image_id, source_ref=source_ref)
    try:
        paths.scanner_dir.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        raise shared.ImageAuditFailure("No se pudo crear el directorio nuevo y confinado del scanner.") from exc
    if runner is None:
        runner = LinuxContainerRunner(paths, runner=docker_runner)
    shared._verify_grype(paths, runner, expected_tool_hash, expected_tool_archive_hash)
    receipt = None
    if expected_db_receipt_sha256 is not None or expected_db_hash is None:
        receipt = scanner_db_provenance.verify(
            paths, expected_db_receipt_sha256, expected_tool_hash, expected_tool_archive_hash,
        )
        expected_db_hash = receipt["installed_database_sha256"]
    db_stamp = shared._db_stamp(
        paths, expected_stamp=receipt["import_metadata"] if receipt else None,
    )
    stamp_hash = _sha256(paths.db_stamp)
    database_hash = _sha256(paths.database)
    if database_hash != expected_db_hash:
        raise shared.ImageAuditFailure("La base local de vulnerabilidades no coincide con su pin.")
    scanner_environment = shared._offline_environment(paths, environment)
    shared._verify_db_status(
        paths, runner, scanner_environment,
        expected_database_path=getattr(runner, "database_path", None),
        timeout=(shared.SCAN_TIMEOUT_SECONDS if isinstance(runner, LinuxContainerRunner)
                 else shared.SHORT_TIMEOUT_SECONDS),
    )
    if receipt:
        scanner_db_provenance.verify(
            paths, expected_db_receipt_sha256, expected_tool_hash, expected_tool_archive_hash,
        )

    source_input = getattr(runner, "source_input", f"docker-archive:{paths.archive}")
    scanner = shared._completed(runner, [
        str(paths.tool), "--fail-on", "negligible", "--scope", "squashed",
        "--output", "json", "--file", str(paths.report), source_input,
    ], env=scanner_environment, timeout=shared.SCAN_TIMEOUT_SECONDS)
    if scanner.returncode not in {0, 2}:
        raise shared.ImageAuditFailure("Grype Linux terminó con un estado no admitido.")
    shared._verify_grype_hashes(paths, expected_tool_hash, expected_tool_archive_hash)
    report, raw_report = shared._read_json_file(
        paths.report, limit=shared.MAX_REPORT_BYTES, label="El informe Grype Linux",
    )
    matches, ignored, severities = _validate_archive_report(
        report, binding=binding, source_input=source_input,
    )
    if scanner.returncode != (2 if matches else 0):
        raise shared.ImageAuditFailure("El exit status de Grype contradice los hallazgos.")
    if (_sha256(paths.archive) != initial_archive_hash
            or _sha256(paths.database) != database_hash or _sha256(paths.db_stamp) != stamp_hash):
        raise shared.ImageAuditFailure("La imagen o DB, incluido su metadata, cambió durante el scan.")
    if receipt:
        scanner_db_provenance.verify(
            paths, expected_db_receipt_sha256, expected_tool_hash, expected_tool_archive_hash,
        )
        shared._verify_db_status(
            paths, runner, scanner_environment,
            expected_database_path=getattr(runner, "database_path", None),
            timeout=shared.SCAN_TIMEOUT_SECONDS if isinstance(runner, LinuxContainerRunner)
                    else shared.SHORT_TIMEOUT_SECONDS,
        )
        scanner_db_provenance.verify(
            paths, expected_db_receipt_sha256, expected_tool_hash, expected_tool_archive_hash,
        )

    summary = {
        "status": "findings" if matches else "clean",
        "scanner_exit": scanner.returncode,
        "image_id": image_id,
        "source_commit": source_ref,
        "grype": {"version": shared.GRYPE_VERSION, "git_commit": shared.GRYPE_COMMIT,
                  "sha256": expected_tool_hash, "platform": "linux_amd64"},
        "database": db_stamp,
        "matches": len(matches),
        "ignored_matches": len(ignored),
        "severity_counts": severities,
        "archive_sha256": initial_archive_hash,
        "archive_binding": binding,
        "report_sha256": hashlib.sha256(raw_report).hexdigest(),
        "paths": {"archive": paths.archive.relative_to(paths.root).as_posix(),
                  "report": paths.report.relative_to(paths.root).as_posix(),
                  "summary": paths.summary.relative_to(paths.root).as_posix()},
    }
    if receipt:
        summary["database_provision"] = {
            "receipt_sha256": expected_db_receipt_sha256,
            "installed_database_sha256": database_hash,
            "import_metadata_sha256": stamp_hash,
            "raw_database_sha256": receipt["raw_database_sha256"],
            "archive_sha256": receipt["archive_sha256"],
        }
    try:
        with paths.summary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(summary, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
    except OSError as exc:
        raise shared.ImageAuditFailure("No se pudo conservar el resumen Linux.") from exc
    return scanner.returncode, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args(argv)
    status, summary = run_archive_audit(
        archive=args.archive, image_id=args.image_id, source_ref=args.source_ref,
        expected_archive_sha256=args.archive_sha256,
        expected_db_receipt_sha256=os.environ.get("CUADERNO_SCANNER_DB_RECEIPT_SHA256"),
    )
    print("CUADERNO_IMAGE_AUDIT " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return status


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except shared.ImageAuditFailure as exc:
        print(f"CUADERNO_IMAGE_AUDIT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
