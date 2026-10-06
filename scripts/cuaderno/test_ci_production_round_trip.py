"""Round-trip diagnostics with real backup boundaries and no Docker execution."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import ci_release_gate as subject
else:
    import ci_release_gate as subject


class RestoreErrorCategoryTests(unittest.TestCase):
    def test_known_native_fragments_return_only_allowlisted_categories(self):
        cases = {
            "connection_refused": 'connection to server at "127.0.0.1" failed: Connection refused',
            "connection_closed": 'server closed the connection unexpectedly',
            "server_starting_or_stopping": 'FATAL: the database system is starting up',
            "database_missing": 'FATAL: database "synthetic_db" does not exist',
            "archive_invalid": 'pg_restore: error: did not find magic string in file header',
            "archive_version_unsupported": 'pg_restore: error: unsupported version (1.99) in file header',
            "permission_error": 'pg_restore: error: could not execute query: ERROR: permission denied for schema public',
            "sql_restore_error": 'pg_restore: error: could not execute query: ERROR: synthetic SQL failure',
            "other": 'unrecognized diagnostic with private-fixture-marker',
        }
        for expected, fragment in cases.items():
            with self.subTest(category=expected):
                message = RuntimeError('private-prefix-marker ' + fragment + ' private-suffix-marker')
                self.assertEqual(subject.restore_error_category(message), expected)

    def test_closed_connections_shutdown_and_missing_files_are_classified(self):
        for fragment, expected in (
            ('connection to server was lost', 'connection_closed'),
            ('Connection reset by peer', 'connection_closed'),
            ('the database system is shutting down', 'server_starting_or_stopping'),
            ('the database system is in recovery mode', 'server_starting_or_stopping'),
            ('input file does not appear to be a valid archive', 'archive_invalid'),
            ('could not open input file: Permission denied', 'permission_error'),
        ):
            with self.subTest(category=expected):
                self.assertEqual(subject.restore_error_category(RuntimeError(fragment)), expected)

    def test_unknown_and_near_matches_fail_to_other(self):
        for message in ('', 'private-password-marker', 'database name is missing',
                        'version unsupported', 'unsupported version (private)', 'SELECT 1',
                        'connection refused' + 'x' * 2001):
            with self.subTest(length=len(message)):
                self.assertEqual(subject.restore_error_category(RuntimeError(message)), 'other')


class ProductionRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
        self.fail_stop = False
        self.failure = 'backup'
        self.image = 'sha256:' + 'a' * 64
        self.private_marker = 'private-diagnostic-fixture-not-for-output'
        self.root_patch = patch.object(subject, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.run_patch = patch.object(subject.subprocess, 'run', self.run_command)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)
        self.socket_patch = patch.object(subject.socket, 'socket')
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)

    def run_command(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[-1] == 'stop' and self.fail_stop:
            raise subprocess.CalledProcessError(1, argv)
        output = b''
        if argv[-3:] == ['ps', '-q', 'db']:
            output = b'db-id\n'
        elif argv[-3:] == ['ps', '-q', 'web']:
            output = b'web-id\n'
        elif argv[:2] == ['docker', 'inspect']:
            service = 'db' if argv[-1] == 'db-id' else 'web'
            output = json.dumps([{'Image': self.image, 'State': {'Running': True},
                'Config': {'Env': [], 'Labels': {'com.docker.compose.project': 'cuaderno-prod',
                                               'com.docker.compose.service': service}}}]).encode()
        elif 'psql' in argv:
            output = b'0\n'
        elif 'pg_dump' in argv:
            return subprocess.CompletedProcess(argv, 1, stderr=self.private_marker.encode())
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=b'')

    def diagnostic(self):
        return self.root / '.cuaderno-runs/production-round-trip-diagnostic.json'

    def test_captured_backup_failure_retains_safe_stage_and_failed_operation(self):
        with self.assertRaises(RuntimeError):
            subject.production_round_trip(self.image)
        self.assertTrue(self.diagnostic().exists())
        raw = self.diagnostic().read_text()
        diagnostic = json.loads(raw)
        self.assertEqual(diagnostic['phase'], 'backup')
        self.assertEqual(diagnostic['operation'], 'compose.exec.pg_dump')
        self.assertEqual(diagnostic['error_type'], 'RuntimeError')
        self.assertEqual(diagnostic['cleanup'], {'attempted': True, 'passed': True})
        self.assertNotIn(self.private_marker, raw)
        self.assertNotIn('CUADERNO_SECRET_KEY', raw)
        self.assertEqual(self.diagnostic().stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.calls[-1][-1], 'stop')
        self.assertNotIn('restore_error_category', diagnostic)

    def test_cleanup_failure_does_not_replace_original_backup_exception(self):
        self.fail_stop = True
        with self.assertRaises(RuntimeError):
            subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertEqual(diagnostic['error_type'], 'RuntimeError')
        self.assertEqual(diagnostic['cleanup'], {'attempted': True, 'passed': False,
                                                'error_type': 'CalledProcessError'})

    def fake_backup(self, env, backups, *, include_env, boundary):
        self.assertTrue(include_env)
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        bundle = backups / 'bundle'
        bundle.mkdir()
        (bundle / 'manifest.json').write_text('{"synthetic":true}\n')
        return bundle

    def test_restore_boundary_failure_is_sanitized_and_cleanup_runs(self):
        def restore(bundle, *, boundary, runtime_image, report_path):
            self.assertEqual(runtime_image, self.image)
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError(self.private_marker)):
                boundary.run(['docker', 'exec', 'synthetic-web', '/opt/recipes/venv/bin/python',
                              '-c', 'private smoke command'])

        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(RuntimeError):
                subject.production_round_trip(self.image)
        raw = self.diagnostic().read_text()
        self.assertNotIn(self.private_marker, raw)
        diagnostic = json.loads(raw)
        self.assertEqual(diagnostic['phase'], 'restore')
        self.assertEqual(diagnostic['operation'], 'docker.exec.python-smoke')
        self.assertNotIn('restore_error_category', diagnostic)

    def test_success_keeps_report_and_manifest_and_records_cleanup(self):
        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', return_value={'passed': True}):
            subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertTrue(diagnostic['passed'])
        self.assertNotIn('restore_error_category', diagnostic)
        self.assertEqual(diagnostic['phase'], 'complete')
        self.assertEqual(diagnostic['cleanup'], {'attempted': True, 'passed': True})
        self.assertEqual((self.root / '.cuaderno-runs/production-backup-manifest.json').read_text(),
                         '{"synthetic":true}\n')

    def test_cleanup_only_failure_fails_round_trip(self):
        self.fail_stop = True
        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', return_value={'passed': True}):
            with self.assertRaises(subprocess.CalledProcessError):
                subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertFalse(diagnostic['passed'])
        self.assertEqual(diagnostic['phase'], 'cleanup')
        self.assertEqual(diagnostic['error_type'], 'CalledProcessError')

    def test_pg_restore_failure_records_category_without_any_raw_message_or_arguments(self):
        def restore(bundle, *, boundary, **kwargs):
            source = bundle / 'database.dump'
            source.write_bytes(b'synthetic')
            with patch.object(subject.production_restore_verify.RestoreBoundary, 'run_from_file',
                              side_effect=RuntimeError('Connection refused ' + self.private_marker)):
                boundary.run_from_file(['docker', 'exec', '-i', self.private_marker, 'pg_restore',
                                        '-U', 'private-user-fixture', '-d', 'private-db-fixture'], source)

        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(RuntimeError):
                subject.production_round_trip(self.image)
        raw = self.diagnostic().read_text()
        diagnostic = json.loads(raw)
        self.assertEqual(diagnostic['operation'], 'docker.exec.pg_restore')
        self.assertEqual(diagnostic['restore_error_category'], 'connection_refused')
        self.assertEqual(diagnostic['error_type'], 'RuntimeError')
        for private in (self.private_marker, 'private-user-fixture', 'private-db-fixture', 'Connection refused'):
            self.assertNotIn(private, raw)
        self.assertFalse(diagnostic['passed'])
        self.assertTrue(diagnostic['cleanup']['passed'])

    def test_first_failed_operation_and_category_survive_later_failures(self):
        def restore(bundle, *, boundary, **kwargs):
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError('unsupported version (1.99) in file header ' + self.private_marker)):
                try:
                    boundary.run(['docker', 'exec', 'synthetic-db', 'pg_restore'])
                except RuntimeError:
                    pass
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError('Connection refused ' + self.private_marker)):
                boundary.run(['docker', 'exec', 'synthetic-db', 'psql'])

        self.fail_stop = True
        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(RuntimeError):
                subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertEqual(diagnostic['operation'], 'docker.exec.pg_restore')
        self.assertEqual(diagnostic['restore_error_category'], 'archive_version_unsupported')
        self.assertFalse(diagnostic['cleanup']['passed'])
        self.assertNotIn(self.private_marker, self.diagnostic().read_text())

    def test_pg_restore_unknown_runtime_error_has_only_other(self):
        def restore(bundle, *, boundary, **kwargs):
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError(self.private_marker)):
                boundary.run(['docker', 'exec', 'synthetic-db', 'pg_restore'])

        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(RuntimeError):
                subject.production_round_trip(self.image)
        self.assertEqual(json.loads(self.diagnostic().read_text())['restore_error_category'], 'other')
        self.assertNotIn(self.private_marker, self.diagnostic().read_text())

    def test_pg_restore_non_runtime_exception_does_not_add_category(self):
        def restore(bundle, *, boundary, **kwargs):
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=ValueError(self.private_marker)):
                boundary.run(['docker', 'exec', 'synthetic-db', 'pg_restore'])

        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(ValueError):
                subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertEqual(diagnostic['operation'], 'docker.exec.pg_restore')
        self.assertNotIn('restore_error_category', diagnostic)
        self.assertNotIn(self.private_marker, self.diagnostic().read_text())

    def test_later_pg_restore_failure_does_not_replace_first_other_operation(self):
        def restore(bundle, *, boundary, **kwargs):
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError(self.private_marker)):
                try:
                    boundary.run(['docker', 'exec', 'synthetic-db', 'psql'])
                except RuntimeError:
                    pass
            with patch.object(subject.production_backup.DockerBoundary, 'run',
                              side_effect=RuntimeError('Connection refused ' + self.private_marker)):
                boundary.run(['docker', 'exec', 'synthetic-db', 'pg_restore'])

        with patch.object(subject.production_backup, 'create_backup', side_effect=self.fake_backup), \
                patch.object(subject.production_restore_verify, 'verify', side_effect=restore):
            with self.assertRaises(RuntimeError):
                subject.production_round_trip(self.image)
        diagnostic = json.loads(self.diagnostic().read_text())
        self.assertEqual(diagnostic['operation'], 'docker.exec.psql')
        self.assertNotIn('restore_error_category', diagnostic)


if __name__ == '__main__':
    unittest.main()
