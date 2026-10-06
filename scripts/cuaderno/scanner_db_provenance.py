"""Read-only verification of a separately trusted scanner database receipt."""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

try:
    from . import image_audit as shared
except ImportError:
    import image_audit as shared


MAX_RECEIPT_BYTES = 64 * 1024
RECEIPT_KEYS = {
    "schema_version", "passed", "archive_url", "archive_sha256", "raw_database_sha256",
    "scanner_binary_sha256", "scanner_archive_sha256", "scanner_version", "scanner_commit",
    "installed_database_path", "installed_database_sha256", "import_metadata_sha256", "import_metadata", "status",
}


def _require(condition, message):
    if not condition:
        raise shared.ImageAuditFailure(message)


def _hash(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "La procedencia requiere un SHA-256 canónico suministrado por quien verifica.")
    return value


def _file_identity(path, root, *, receipt=False):
    _require(path.is_absolute() and shared._contained(path, root), "El artefacto de procedencia sale del proyecto.")
    shared._reject_link_ancestors(path, root)
    try:
        _require(path == path.resolve(strict=True), "El artefacto de procedencia no tiene un destino canónico.")
        metadata = path.lstat()
        _require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_size > 0,
                 "La procedencia requiere archivos regulares propios sin enlaces.")
        if hasattr(os, "getuid"):
            _require(metadata.st_uid == os.getuid(), "El artefacto de procedencia pertenece a otro usuario.")
        if receipt and sys.platform.startswith("linux"):
            _require(stat.S_IMODE(metadata.st_mode) == 0o600, "El recibo de procedencia requiere modo 0600.")
        current = path.parent
        while True:
            directory = current.lstat()
            _require(stat.S_ISDIR(directory.st_mode), "Un ancestro de procedencia no es un directorio regular.")
            if hasattr(os, "getuid"):
                _require(directory.st_uid == os.getuid(), "Un directorio de procedencia pertenece a otro usuario.")
            if current == root:
                break
            current = current.parent
        return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_nlink,
                metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)
    except OSError as error:
        raise shared.ImageAuditFailure("No se pudo verificar un artefacto de procedencia.") from error


def verify(paths, expected_receipt_sha256, expected_tool_hash, expected_tool_archive_hash):
    """Bind the current files to a trusted receipt token, without executing Grype."""
    expected_receipt_sha256 = _hash(expected_receipt_sha256)
    expected_tool_hash = _hash(expected_tool_hash)
    expected_tool_archive_hash = _hash(expected_tool_archive_hash)
    root = Path(paths.root)
    _require(root.is_absolute() and root == root.resolve(strict=True), "La raíz de procedencia no es canónica.")
    receipt_path = root / ".cuaderno-runs/scanner-db-provision.json"
    database, stamp_path = Path(paths.database), Path(paths.db_stamp)
    db_root = Path(paths.db_root)
    tooling = root / "data/cuaderno/tooling"
    tool_directory = tooling / "grype-linux-0.119.0"
    _require(db_root == tooling / "grype-db"
             and Path(paths.tool) == tool_directory / "grype"
             and Path(paths.zip_archive) == tool_directory / "grype_0.119.0_linux_amd64.tar.gz",
             "La procedencia no utiliza los destinos fijos del scanner y su base.")
    _require(database == db_root / "6/vulnerability.db" and stamp_path == db_root / "6/import.json",
             "La base y su metadata no están en el destino fijo de Grype.")
    files = (receipt_path, database, stamp_path, Path(paths.tool), Path(paths.zip_archive))
    identities = {path: _file_identity(path, root, receipt=path == receipt_path) for path in files}
    private = {receipt_path.parent, Path(paths.tool).parent, Path(paths.zip_archive).parent, db_root, database.parent}
    if sys.platform.startswith("linux"):
        for directory in private:
            _require(stat.S_IMODE(directory.stat().st_mode) == 0o700,
                     "Los directorios privados de procedencia requieren modo 0700.")
    receipt, raw = shared._read_json_file(receipt_path, limit=MAX_RECEIPT_BYTES, label="Recibo de procedencia")
    _require(hashlib.sha256(raw).hexdigest() == expected_receipt_sha256, "El recibo no coincide con el token de confianza externo.")
    _require(isinstance(receipt, dict) and set(receipt) == RECEIPT_KEYS,
             "El recibo no contiene exactamente el contrato de procedencia.")
    _require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1 and receipt["passed"] is True,
             "El recibo no acredita una provisión aprobada del esquema esperado.")
    pins = {
        "archive_url": shared.DB_ARCHIVE_SOURCE, "archive_sha256": shared.VULNERABILITY_DB_ARCHIVE_SHA256,
        "raw_database_sha256": shared.VULNERABILITY_DB_RAW_SHA256,
        "scanner_binary_sha256": expected_tool_hash, "scanner_archive_sha256": expected_tool_archive_hash,
        "scanner_version": shared.GRYPE_VERSION, "scanner_commit": shared.GRYPE_COMMIT,
        "installed_database_path": str(database),
    }
    _require(all(isinstance(receipt[key], str) and receipt[key] == expected for key, expected in pins.items()),
             "Un pin, scanner o destino del recibo no coincide con la procedencia fijada.")
    installed_hash = _hash(receipt["installed_database_sha256"])
    stamp_hash = _hash(receipt["import_metadata_sha256"])
    metadata, stamp_raw = shared._read_json_file(stamp_path, limit=64 * 1024, label="Metadata original de Grype")
    _require(isinstance(metadata, dict) and set(metadata) == {"digest", "source", "client_version"}
             and isinstance(metadata["digest"], str) and re.fullmatch(r"xxh64:[0-9a-f]{16}", metadata["digest"]) is not None
             and metadata["source"] == "manual import" and metadata["client_version"] == "v6.1.9",
             "La metadata original de Grype no tiene el formato, origen y cliente esperados.")
    _require(isinstance(receipt["import_metadata"], dict) and receipt["import_metadata"] == metadata
             and hashlib.sha256(stamp_raw).hexdigest() == stamp_hash,
             "El recibo no conserva los bytes y el objeto de metadata originales.")
    expected_status = {"schemaVersion": "v6.1.10", "from": "manual import", "built": shared.DB_BUILT,
                       "path": str(database), "valid": True}
    status = receipt["status"]
    _require(isinstance(status, dict) and set(status) == set(expected_status) and status.get("valid") is True
             and all(isinstance(status[key], str) and status[key] == value for key, value in expected_status.items() if key != "valid"),
             "El status original no acredita la base importada exacta y válida.")
    _require(shared._sha256(paths.tool) == expected_tool_hash and shared._sha256(paths.zip_archive) == expected_tool_archive_hash,
             "El scanner o su archivo oficial cambió tras la provisión.")
    _require(shared._sha256(database) == installed_hash, "La base instalada cambió tras la provisión.")
    for path, identity in identities.items():
        _require(_file_identity(path, root, receipt=path == receipt_path) == identity,
                 "Un artefacto cambió durante la verificación de procedencia.")
    return receipt
