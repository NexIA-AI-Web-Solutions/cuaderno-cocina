"""Provisioning boundaries without downloads, decompression or scanner execution."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import ci_release_gate as subject
else:
    import ci_release_gate as subject


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def tar_bytes(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, raw, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(raw) if kind == tarfile.REGTYPE else 0
            member.linkname = 'vulnerability.db' if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE} else ''
            archive.addfile(member, io.BytesIO(raw) if member.isfile() else None)
    return output.getvalue()


class Decoder:
    def __init__(self, raw, *, returncode=0, hangs=False):
        self.stdout = io.BytesIO(raw)
        self.returncode = returncode
        self.hangs = hangs
        self.terminated = self.killed = False

    def wait(self, timeout):
        if self.hangs and not self.killed:
            raise subprocess.TimeoutExpired('zstd', timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class ScannerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = b'raw database without indexes'
        self.installed = b'hydrated database with indexes and sqlite statistics'
        self.stamp = {'digest': 'xxh64:0123456789abcdef', 'source': 'manual import',
                      'client_version': 'v6.1.9'}
        # Formatting is retained byte-for-byte; provisioning must never rewrite this.
        self.stamp_bytes = json.dumps(self.stamp, indent=1).encode() + b'\n'
        self.entries = [('vulnerability.db', self.raw, tarfile.REGTYPE)]
        self.decoder_exit = 0
        self.decoder_hangs = False
        self.tamper_during_status = False
        self.wrong_scanner_version = False
        self.imports = []
        self.downloads = []
        self.status_changes = {}
        self.patch(subject, 'ROOT', self.root)
        self.patch(subject.audit, 'LINUX_GRYPE_SHA256', sha256(b'fake pinned scanner'))
        self.patch(subject.audit, 'LINUX_ARCHIVE_SHA256', sha256(tar_bytes(
            [('grype', b'fake pinned scanner', tarfile.REGTYPE)])))
        self.patch(subject.audit.shared, 'VULNERABILITY_DB_ARCHIVE_SHA256',
                   sha256(b'fake verified compressed archive'))
        self.patch(subject.audit.shared, 'VULNERABILITY_DB_RAW_SHA256', sha256(self.raw), create=True)
        self.patch(subject.audit.shared, 'VULNERABILITY_DB_SHA256', sha256(self.installed))
        self.patch(subject.audit.shared, 'DB_ARCHIVE_SOURCE', 'https://example.test/pinned.tar.zst', create=True)
        self.patch(subject.audit.shared, 'DB_SOURCE', self.stamp['source'])
        self.patch(subject.audit.shared, 'DB_DIGEST', self.stamp['digest'])
        self.patch(subject.audit.shared, 'DB_CLIENT_VERSION', self.stamp['client_version'])
        self.patch(subject.audit.shared, 'DB_SCHEMA_VERSION', 'v6.1.10', create=True)
        self.patch(subject, 'download', self.download)
        self.patch(subject.subprocess, 'Popen', self.decode)
        self.patch(subject.subprocess, 'run', self.scanner_run)

    def patch(self, owner, name, value, **kwargs):
        handle = patch.object(owner, name, value, **kwargs)
        handle.start()
        self.addCleanup(handle.stop)

    def download(self, url, destination, digest):
        self.downloads.append((url, digest))
        if destination.name.startswith('grype_'):
            destination.write_bytes(tar_bytes([('grype', b'fake pinned scanner', tarfile.REGTYPE)]))
        else:
            destination.write_bytes(b'fake verified compressed archive')

    def decode(self, argv, **kwargs):
        self.decoder = Decoder(tar_bytes(self.entries), returncode=self.decoder_exit,
                               hangs=self.decoder_hangs)
        self.decode_argv = argv
        return self.decoder

    def scanner_run(self, argv, **kwargs):
        db_root = self.root / 'data/cuaderno/tooling/grype-db/6'
        if argv[1:] == ['version']:
            version = '0.118.0' if self.wrong_scanner_version else '0.119.0'
            return subprocess.CompletedProcess(argv, 0, stdout=(
                'Version: ' + version + '\nGitCommit: ' + subject.audit.shared.GRYPE_COMMIT + '\n'))
        if argv[1:3] == ['db', 'import']:
            self.imports.append(argv)
            db_root.mkdir(parents=True)
            (db_root / 'vulnerability.db').write_bytes(self.installed)
            (db_root / 'import.json').write_bytes(self.stamp_bytes)
            return subprocess.CompletedProcess(argv, 0)
        self.assertEqual(argv[1:], ['db', 'status', '-o', 'json'])
        status = {'schemaVersion': 'v6.1.10', 'from': 'manual import',
                  'built': subject.audit.shared.DB_BUILT, 'valid': True,
                  'path': str(db_root / 'vulnerability.db')}
        status.update(self.status_changes)
        if self.tamper_during_status:
            (db_root / 'vulnerability.db').write_bytes(b'tampered after import')
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(status))

    def receipt(self):
        return self.root / '.cuaderno-runs/scanner-db-provision.json'

    def assert_rejected(self, *, before_import=False):
        with self.assertRaises((ValueError, subject.audit.shared.ImageAuditFailure,
                                subprocess.TimeoutExpired, subprocess.CalledProcessError)):
            subject.provision_scanner()
        self.assertFalse(self.receipt().exists())
        if before_import:
            self.assertEqual(self.imports, [])

    def test_hydrated_bytes_use_separate_pin_and_preserve_genuine_stamp(self):
        trusted_hash = subject.provision_scanner()
        db_root = self.root / 'data/cuaderno/tooling/grype-db/6'
        self.assertEqual((db_root / 'import.json').read_bytes(), self.stamp_bytes)
        receipt = json.loads(self.receipt().read_text())
        self.assertEqual(receipt['raw_database_sha256'], sha256(self.raw))
        self.assertEqual(receipt['installed_database_sha256'], sha256(self.installed))
        self.assertEqual(receipt['import_metadata_sha256'], sha256(self.stamp_bytes))
        self.assertEqual(receipt['import_metadata'], self.stamp)
        self.assertEqual(trusted_hash, sha256(self.receipt().read_bytes()))
        self.assertEqual(self.receipt().stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.receipt().parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(db_root.stat().st_mode & 0o777, 0o700)
        self.assertTrue(receipt['status']['valid'])
        self.assertEqual(self.downloads[1], (subject.audit.shared.DB_ARCHIVE_SOURCE,
                                           subject.audit.shared.VULNERABILITY_DB_ARCHIVE_SHA256))
        self.assertTrue(self.decoder.stdout.closed)

    def test_raw_tamper_prevents_import(self):
        self.entries = [('vulnerability.db', b'tampered raw database', tarfile.REGTYPE)]
        self.assert_rejected(before_import=True)

    def test_valid_nondeterministic_import_uses_actual_bytes_and_digest(self):
        self.installed = b'another legitimate hydration layout'
        self.stamp['digest'] = 'xxh64:fedcba9876543210'
        self.stamp_bytes = json.dumps(self.stamp, indent=1).encode() + b'\n'
        subject.provision_scanner()
        receipt = json.loads(self.receipt().read_text())
        self.assertEqual(receipt['installed_database_sha256'], sha256(self.installed))
        self.assertEqual(receipt['import_metadata'], self.stamp)

    def test_wrong_scanner_version_prevents_import(self):
        self.wrong_scanner_version = True
        self.assert_rejected(before_import=True)

    def test_existing_database_cache_prevents_import(self):
        (self.root / 'data/cuaderno/tooling/grype-db').mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            subject.provision_scanner()
        self.assertEqual(self.imports, [])
        self.assertFalse(self.receipt().exists())

    def test_linked_data_ancestor_rejects_before_any_outside_write(self):
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside)
            (self.root / 'data').symlink_to(outside_path, target_is_directory=True)
            with self.assertRaises(subject.audit.shared.ImageAuditFailure):
                subject.provision_scanner()
            self.assertEqual(self.downloads, [])
            self.assertEqual(self.imports, [])
            self.assertEqual(list(outside_path.iterdir()), [])

    def test_linked_database_root_rejects_before_scanner_download(self):
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside)
            tooling = self.root / 'data/cuaderno/tooling'
            tooling.mkdir(parents=True)
            (tooling / 'grype-db').symlink_to(outside_path, target_is_directory=True)
            with self.assertRaises(subject.audit.shared.ImageAuditFailure):
                subject.provision_scanner()
            self.assertEqual(self.downloads, [])
            self.assertEqual(self.imports, [])
            self.assertEqual(list(outside_path.iterdir()), [])
            self.assertFalse((tooling / 'grype-linux-0.119.0').exists())

    def test_duplicate_member_prevents_import(self):
        self.entries *= 2
        self.assert_rejected(before_import=True)

    def test_path_member_prevents_import(self):
        self.entries[0] = ('../vulnerability.db', self.raw, tarfile.REGTYPE)
        self.assert_rejected(before_import=True)

    def test_symlink_prevents_import(self):
        self.entries[0] = ('vulnerability.db', b'', tarfile.SYMTYPE)
        self.assert_rejected(before_import=True)

    def test_hardlink_prevents_import(self):
        self.entries[0] = ('vulnerability.db', b'', tarfile.LNKTYPE)
        self.assert_rejected(before_import=True)

    def test_extra_member_prevents_import(self):
        self.entries.append(('import.json', b'{}', tarfile.REGTYPE))
        self.assert_rejected(before_import=True)

    def test_decoder_error_prevents_import(self):
        self.decoder_exit = 1
        self.assert_rejected(before_import=True)
        self.assertTrue(self.decoder.stdout.closed)

    def test_hanging_decoder_is_terminated_and_killed(self):
        self.decoder_hangs = True
        self.assert_rejected(before_import=True)
        self.assertTrue(self.decoder.terminated)
        self.assertTrue(self.decoder.killed)
        self.assertTrue(self.decoder.stdout.closed)

    def test_installed_tamper_rejects_receipt(self):
        self.tamper_during_status = True
        self.assert_rejected()

    def test_forged_stamp_rejects_without_rewriting(self):
        self.stamp_bytes = json.dumps({**self.stamp, 'source': 'forged source'}).encode()
        self.assert_rejected()
        self.assertEqual((self.root / 'data/cuaderno/tooling/grype-db/6/import.json').read_bytes(),
                         self.stamp_bytes)

    def test_stale_status_rejects_receipt(self):
        self.status_changes['built'] = '2000-01-01T00:00:00Z'
        self.assert_rejected()

    def test_invalid_status_rejects_receipt(self):
        self.status_changes['valid'] = False
        self.assert_rejected()

    def test_native_checksum_failure_rejects_receipt(self):
        self.stamp_bytes = json.dumps({**self.stamp, 'digest': 'xxh64:ffffffffffffffff'}).encode()
        self.status_changes.update(valid=False, error='bad db checksum')
        self.assert_rejected()

    def test_invalid_stamp_digest_rejects_receipt(self):
        self.stamp_bytes = json.dumps({**self.stamp, 'digest': 'sha256:forged'}).encode()
        self.assert_rejected()

    def test_main_replaces_inherited_receipt_hash_before_candidate_commands(self):
        context = self.root / 'context.json'
        context.write_text(json.dumps({'image_id': 'sha256:' + 'a' * 64}))
        expected = 'b' * 64

        def first_candidate_command(argv, **kwargs):
            self.assertEqual(subject.os.environ['CUADERNO_SCANNER_DB_RECEIPT_SHA256'], expected)
            self.assertEqual(kwargs['env']['CUADERNO_SCANNER_DB_RECEIPT_SHA256'], expected)
            raise RuntimeError('boundary verified; stop mocked gate')

        with patch.dict(subject.os.environ, {'CI': 'true', 'CUADERNO_ENV': 'test',
                         'CUADERNO_SCANNER_DB_RECEIPT_SHA256': 'untrusted inherited value'}), \
                patch.object(subject.sys, 'argv', ['ci_release_gate.py', '--context', str(context)]), \
                patch.object(subject, 'provision_scanner', return_value=expected), \
                patch.object(subject.subprocess, 'run', side_effect=first_candidate_command):
            with self.assertRaisesRegex(RuntimeError, 'boundary verified'):
                subject.main()


if __name__ == '__main__':
    unittest.main()
