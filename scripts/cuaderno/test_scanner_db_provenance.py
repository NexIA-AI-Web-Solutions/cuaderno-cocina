"""Read-only receipt binding, genuine metadata and local-file confinement."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

try:
    from . import scanner_db_provenance as subject
except ImportError:
    import scanner_db_provenance as subject


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ScannerDbProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        tool_dir = self.root / "data/cuaderno/tooling/grype-linux-0.119.0"
        tool_dir.mkdir(mode=0o700, parents=True)
        db_root = self.root / "data/cuaderno/tooling/grype-db"
        (db_root / "6").mkdir(mode=0o700, parents=True)
        db_root.chmod(0o700)
        self.paths = SimpleNamespace(root=self.root, tool=tool_dir / "grype", zip_archive=tool_dir / "grype_0.119.0_linux_amd64.tar.gz",
                                     db_root=db_root, database=db_root / "6/vulnerability.db", db_stamp=db_root / "6/import.json")
        self.paths.tool.write_bytes(b"independently pinned scanner fixture")
        self.paths.zip_archive.write_bytes(b"independently pinned scanner archive fixture")
        self.paths.database.write_bytes(b"hydrated bytes measured by the trusted provisioner")
        self.tool_hash = digest(self.paths.tool.read_bytes())
        self.archive_hash = digest(self.paths.zip_archive.read_bytes())
        self.stamp = {"digest": "xxh64:0123456789abcdef", "source": "manual import", "client_version": "v6.1.9"}
        self.stamp_raw = json.dumps(self.stamp, indent=1).encode() + b"\n"
        self.paths.db_stamp.write_bytes(self.stamp_raw)
        self.receipt_path = self.root / ".cuaderno-runs/scanner-db-provision.json"
        self.receipt_path.parent.mkdir(mode=0o700)
        self.receipt = {
            "schema_version": 1, "passed": True,
            "archive_url": subject.shared.DB_ARCHIVE_SOURCE,
            "archive_sha256": subject.shared.VULNERABILITY_DB_ARCHIVE_SHA256,
            "raw_database_sha256": subject.shared.VULNERABILITY_DB_RAW_SHA256,
            "scanner_binary_sha256": self.tool_hash, "scanner_archive_sha256": self.archive_hash,
            "scanner_version": subject.shared.GRYPE_VERSION, "scanner_commit": subject.shared.GRYPE_COMMIT,
            "installed_database_path": str(self.paths.database),
            "installed_database_sha256": digest(self.paths.database.read_bytes()),
            "import_metadata_sha256": digest(self.stamp_raw), "import_metadata": self.stamp,
            "status": {"schemaVersion": "v6.1.10", "from": "manual import", "built": subject.shared.DB_BUILT,
                       "path": str(self.paths.database), "valid": True},
        }
        self.persist()

    def persist(self):
        raw = json.dumps(self.receipt, indent=2).encode() + b"\n"
        self.receipt_path.write_bytes(raw)
        self.receipt_path.chmod(0o600)
        self.token = digest(raw)

    def verify(self, token=None):
        return subject.verify(self.paths, self.token if token is None else token, self.tool_hash, self.archive_hash)

    def rejected(self):
        with self.assertRaises(subject.shared.ImageAuditFailure):
            self.verify()

    def test_accepts_measured_hydrated_bytes_and_preserves_original_metadata(self):
        before = [path.read_bytes() for path in (self.receipt_path, self.paths.database, self.paths.db_stamp)]
        self.assertEqual(self.verify(), self.receipt)
        self.assertEqual(before, [path.read_bytes() for path in (self.receipt_path, self.paths.database, self.paths.db_stamp)])
        self.assertNotEqual(self.receipt["installed_database_sha256"], subject.shared.VULNERABILITY_DB_RAW_SHA256)

    def test_missing_or_malformed_trust_tokens_are_not_self_computed(self):
        for token in (None, "", "a" * 63, "z" * 64, 42, True):
            with self.subTest(token=token), self.assertRaises(subject.shared.ImageAuditFailure):
                subject.verify(self.paths, token, self.tool_hash, self.archive_hash)

    def test_recomputed_forged_receipt_does_not_replace_the_supplied_token(self):
        trusted = self.token
        self.paths.database.write_bytes(b"forged replacement")
        self.receipt["installed_database_sha256"] = digest(self.paths.database.read_bytes())
        self.persist()
        with self.assertRaises(subject.shared.ImageAuditFailure):
            self.verify(trusted)

    def test_database_and_original_stamp_tamper_are_rejected(self):
        for path in (self.paths.database, self.paths.db_stamp):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"tamper")
                self.rejected()
                path.write_bytes(original)

    def test_actual_tool_and_archive_bytes_must_match_external_pins(self):
        for path in (self.paths.tool, self.paths.zip_archive):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"tamper")
                self.rejected()
                path.write_bytes(original)

    def test_receipt_pins_paths_and_scanner_identity_cannot_be_overridden(self):
        changes = {"archive_url": "https://other.invalid/db", "archive_sha256": "f" * 64,
                   "raw_database_sha256": "f" * 64, "scanner_binary_sha256": "f" * 64,
                   "scanner_archive_sha256": "f" * 64, "scanner_version": "0.120.0", "scanner_commit": "f" * 40,
                   "installed_database_path": str(self.paths.database.parent / "other.db"),
                   "installed_database_sha256": "f" * 64, "import_metadata_sha256": "f" * 64,
                   "schema_version": True, "passed": 1, "unexpected": "field"}
        original = copy.deepcopy(self.receipt)
        for key, value in changes.items():
            with self.subTest(field=key):
                self.receipt = {**copy.deepcopy(original), key: value}
                self.persist()
                self.rejected()
        self.receipt = original

    def test_every_required_receipt_field_is_required(self):
        original = copy.deepcopy(self.receipt)
        for key in original:
            with self.subTest(field=key):
                self.receipt = copy.deepcopy(original)
                del self.receipt[key]
                self.persist()
                self.rejected()

    def test_status_is_exact_and_matches_native_import(self):
        changes = {"valid": 1, "schemaVersion": "v6.1.9", "from": "automatic update",
                   "built": "2000-01-01T00:00:00Z", "path": "/elsewhere/vulnerability.db", "unexpected": True}
        original = copy.deepcopy(self.receipt)
        for key, value in changes.items():
            with self.subTest(field=key):
                self.receipt = copy.deepcopy(original)
                self.receipt["status"][key] = value
                self.persist()
                self.rejected()

    def test_stamp_digest_is_dynamic_but_format_source_and_client_are_exact(self):
        for key, value in {"digest": "xxh64:not-hex", "source": "automatic update", "client_version": "v6.1.10", "extra": True}.items():
            with self.subTest(field=key):
                stamp = {**self.stamp, key: value}
                raw = json.dumps(stamp).encode()
                self.paths.db_stamp.write_bytes(raw)
                self.receipt["import_metadata"] = stamp
                self.receipt["import_metadata_sha256"] = digest(raw)
                self.persist()
                self.rejected()

    def test_stamp_object_and_exact_original_bytes_are_both_bound(self):
        self.receipt["import_metadata"] = {**self.stamp, "digest": "xxh64:ffffffffffffffff"}
        self.persist()
        self.rejected()

    def test_duplicate_receipt_and_stamp_keys_are_rejected_even_with_matching_hashes(self):
        raw = self.receipt_path.read_bytes().replace(b'{', b'{"schema_version":1,', 1)
        self.receipt_path.write_bytes(raw)
        self.token = digest(raw)
        self.rejected()
        self.persist()
        raw = b'{"digest":"xxh64:0123456789abcdef",' + self.stamp_raw[1:]
        self.paths.db_stamp.write_bytes(raw)
        self.receipt["import_metadata_sha256"] = digest(raw)
        self.persist()
        self.rejected()

    def test_oversized_receipt_is_rejected_before_unbounded_json_read(self):
        raw = self.receipt_path.read_bytes() + b" " * (65 * 1024)
        self.receipt_path.write_bytes(raw)
        self.token = digest(raw)
        self.rejected()

    def test_symlink_files_and_ancestors_are_rejected(self):
        for path in (self.receipt_path, self.paths.database, self.paths.db_stamp):
            with self.subTest(path=path):
                backup = path.with_suffix(".real")
                path.rename(backup)
                path.symlink_to(backup)
                self.rejected()
                path.unlink()
                backup.rename(path)
        directory = self.paths.database.parent
        backup = directory.with_name("real-6")
        directory.rename(backup)
        directory.symlink_to(backup, target_is_directory=True)
        self.rejected()
        directory.unlink()
        backup.rename(directory)

    def test_hardlinks_are_rejected_for_receipt_database_and_stamp(self):
        for path in (self.receipt_path, self.paths.database, self.paths.db_stamp):
            with self.subTest(path=path):
                linked = self.root / "second-link"
                os.link(path, linked)
                self.rejected()
                linked.unlink()

    def test_even_trusted_receipts_cannot_redirect_fixed_destinations(self):
        original_paths = vars(self.paths).copy()
        original_receipt = copy.deepcopy(self.receipt)
        for kind in ("database", "tooling", "archive"):
            with self.subTest(kind=kind):
                if kind == "database":
                    source = self.paths.db_root
                    destination = source.with_name("other-db")
                    source.rename(destination)
                    self.paths.db_root = destination
                    self.paths.database = destination / "6/vulnerability.db"
                    self.paths.db_stamp = destination / "6/import.json"
                    self.receipt["installed_database_path"] = str(self.paths.database)
                    self.receipt["status"]["path"] = str(self.paths.database)
                elif kind == "tooling":
                    source = self.paths.tool.parent
                    destination = source.with_name("other-tooling")
                    source.rename(destination)
                    self.paths.tool = destination / "grype"
                    self.paths.zip_archive = destination / original_paths["zip_archive"].name
                else:
                    source = self.paths.zip_archive
                    destination = source.with_name("other.tar.gz")
                    source.rename(destination)
                    self.paths.zip_archive = destination
                self.persist()
                try:
                    self.rejected()
                finally:
                    destination.rename(source)
                    self.paths = SimpleNamespace(**original_paths)
                    self.receipt = copy.deepcopy(original_receipt)
                    self.persist()

    def test_other_uid_cannot_own_files_or_their_ancestors(self):
        if not hasattr(os, "getuid"):
            return
        with mock.patch.object(subject.os, "getuid", return_value=os.getuid() + 1):
            self.rejected()

    def test_linux_receipt_and_private_directories_enforce_exact_permissions(self):
        if not sys.platform.startswith("linux"):
            return
        self.receipt_path.chmod(0o644)
        self.rejected()
        self.receipt_path.chmod(0o600)
        for directory in (self.receipt_path.parent, self.paths.tool.parent, self.paths.db_root, self.paths.database.parent):
            with self.subTest(directory=directory):
                directory.chmod(0o755)
                self.rejected()
                directory.chmod(0o700)
        # Native Grype may create ordinary readable DB/stamp files inside the private directory.
        self.paths.database.chmod(0o644)
        self.paths.db_stamp.chmod(0o644)
        self.assertEqual(self.verify(), self.receipt)


if __name__ == "__main__":
    unittest.main()
