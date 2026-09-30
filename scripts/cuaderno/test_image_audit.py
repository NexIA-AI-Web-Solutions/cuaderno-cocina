from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import image_audit as subject
else:
    import image_audit as subject


IMAGE_ID = "sha256:" + "a" * 64
SOURCE_REF = "b" * 40 + "+worktree." + "c" * 64
GRYPE_COMMIT = "b6f5194537747ee7f705f4113069ac9eb269919f"


def container_document(**changes):
    document = {
        "Id": "d" * 64,
        "Name": "/cuaderno-release-web",
        "Image": IMAGE_ID,
        "State": {"Running": True, "Status": "running"},
        "HostConfig": {"PortBindings": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]}},
        "Config": {"Image": "cuaderno-cocina:local", "Labels": {}},
    }
    document.update(changes)
    return [document]


class FakeRunner:
    def __init__(self, paths, *, report=None, scanner_status=2, container=None, source_ref=SOURCE_REF,
                 final_container=None, mutate_archive=False, mutate_database=False,
                 mutate_tool_before_scan=False, mutate_tool_after_scan=False,
                 grype_commit=GRYPE_COMMIT):
        self.paths = paths
        self.report = {
            "matches": [
                {"vulnerability": {"id": "CVE-SYNTHETIC", "severity": "High"}},
            ],
            "ignoredMatches": [],
            "source": {"type": "image", "target": {
                "userInput": f"docker-archive:{paths.archive}", "imageID": IMAGE_ID,
            }},
            "descriptor": {"name": "grype", "version": "0.119.0"},
        } if report is None else report
        self.scanner_status = scanner_status
        self.container = container or container_document()
        self.final_container = final_container
        self.source_ref = source_ref
        self.mutate_archive = mutate_archive
        self.mutate_database = mutate_database
        self.mutate_tool_before_scan = mutate_tool_before_scan
        self.mutate_tool_after_scan = mutate_tool_after_scan
        self.grype_commit = grype_commit
        self.container_inspections = 0
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(map(str, argv)), kwargs))
        argv = list(map(str, argv))
        if argv[:3] == ["docker", "inspect", "cuaderno-release-web"]:
            self.container_inspections += 1
            document = self.final_container if self.final_container and self.container_inspections >= 3 else self.container
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(document), stderr="")
        if argv[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=json.dumps([{"Id": IMAGE_ID, "Config": {"Labels": {"SourceCommit": self.source_ref}}}]),
                stderr="",
            )
        if argv[:3] == ["docker", "exec", "cuaderno-release-web"]:
            return subprocess.CompletedProcess(argv, 0, stdout=self.source_ref + "\n", stderr="")
        if argv[:3] == ["docker", "image", "save"]:
            self.paths.archive.write_bytes(b"synthetic exact image archive")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv[0] == str(self.paths.tool) and argv[1:] == ["version"]:
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=f"Application: grype\nVersion: 0.119.0\nGitCommit: {self.grype_commit}\n",
                stderr="",
            )
        if argv[0] == str(self.paths.tool) and argv[1:] == ["db", "status", "-o", "json"]:
            if self.mutate_tool_before_scan:
                self.paths.tool.write_bytes(b"mutated tool before scan")
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({
                "built": "2026-09-30T00:35:37Z", "schemaVersion": 6,
                "location": str(self.paths.database), "checksum": "sha256:synthetic", "error": None,
            }), stderr="")
        if argv[0] == str(self.paths.tool):
            self.paths.report.write_text(json.dumps(self.report), encoding="utf-8")
            if self.mutate_archive:
                self.paths.archive.write_bytes(b"mutated archive")
            if self.mutate_database:
                self.paths.database.write_bytes(b"mutated database")
            if self.mutate_tool_after_scan:
                self.paths.zip_archive.write_bytes(b"mutated zip after scan")
            return subprocess.CompletedProcess(argv, self.scanner_status, stdout="", stderr="findings")
        raise AssertionError(argv)


class ImageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        tool_dir = self.root / "data/cuaderno/tooling/grype-0.119.0"
        db_dir = self.root / "data/cuaderno/tooling/grype-db/6"
        tool_dir.mkdir(parents=True)
        db_dir.mkdir(parents=True)
        (tool_dir / "grype.exe").write_bytes(b"synthetic pinned grype")
        (tool_dir / "grype_0.119.0_windows_amd64.zip").write_bytes(b"synthetic official archive")
        (db_dir / "vulnerability.db").write_bytes(b"synthetic database")
        (db_dir / "import.json").write_text(json.dumps({
            "digest": subject.DB_DIGEST, "source": subject.DB_SOURCE,
            "client_version": subject.DB_CLIENT_VERSION,
        }), encoding="utf-8")
        self.scan_id = "12345678-1234-4234-8234-123456789abc"
        self.paths = subject.audit_paths(self.root, self.scan_id)
        self.tool_hash = hashlib.sha256(b"synthetic pinned grype").hexdigest()
        self.zip_hash = hashlib.sha256(b"synthetic official archive").hexdigest()
        self.db_hash = hashlib.sha256(b"synthetic database").hexdigest()

    def run_audit(self, runner, *, scan_id=None, environment=None):
        return subject.run_audit(
            root=self.root, scan_id=scan_id or self.scan_id, runner=runner,
            environ=environment or {"CUADERNO_ENV": "test"},
            expected_tool_hash=self.tool_hash, expected_zip_hash=self.zip_hash,
            expected_db_hash=self.db_hash,
        )

    def test_container_contract_requires_running_exact_image_and_loopback_binding(self):
        validated = subject.validate_container_document(container_document())
        self.assertEqual(validated["Image"], IMAGE_ID)
        invalid = (
            [],
            container_document(Name="/other"),
            container_document(Image="cuaderno-cocina:local"),
            container_document(State={"Running": False, "Status": "exited"}),
            container_document(HostConfig={"PortBindings": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18081"}]}}),
            container_document(HostConfig={"PortBindings": {"80/tcp": [{"HostIp": "::1", "HostPort": "18081"}]}}),
            container_document(HostConfig={"PortBindings": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18082"}]}}),
            container_document(HostConfig={"PortBindings": {
                "80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}],
                "53/udp": [{"HostIp": "127.0.0.1", "HostPort": "18082"}],
            }}),
            container_document(HostConfig={"PortBindings": {}}),
        )
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(subject.ImageAuditFailure):
                subject.validate_container_document(document)

    def test_rejects_outside_symlink_and_existing_scan_targets_before_processes(self):
        outside = subject.audit_paths(self.root.parent, self.scan_id)
        with self.assertRaises(subject.ImageAuditFailure):
            subject.validate_paths(outside, expected_root=self.root)

        scans = self.root / "data/cuaderno/scans"
        scans.mkdir(parents=True)
        self.paths.scan_dir.mkdir()
        with self.assertRaises(subject.ImageAuditFailure):
            subject.validate_paths(self.paths, expected_root=self.root)

        self.paths.scan_dir.rmdir()
        link = self.root / "data/cuaderno/scans-link"
        try:
            link.symlink_to(self.root.parent, target_is_directory=True)
        except OSError:
            return
        linked_paths = self.paths._replace(scan_root=link, scan_dir=link / self.scan_id)
        with self.assertRaises(subject.ImageAuditFailure):
            subject.validate_paths(linked_paths, expected_root=self.root)

    def test_hash_or_version_mismatch_fails_before_scan_directory_creation(self):
        runner = FakeRunner(self.paths)
        with self.assertRaises(subject.ImageAuditFailure):
            subject.run_audit(
                root=self.root, scan_id=self.scan_id, runner=runner,
                environ={"CUADERNO_ENV": "test"}, expected_tool_hash="0" * 64,
                expected_zip_hash=self.zip_hash,
                expected_db_hash=self.db_hash,
            )
        self.assertFalse(self.paths.scan_dir.exists())

        for reported_commit in (
            "b6f51945",
            "b6f5194537747ee7f705f4113069ac9e0000000",
        ):
            with self.subTest(reported_commit=reported_commit), self.assertRaises(subject.ImageAuditFailure):
                subject.run_audit(
                    root=self.root, scan_id=self.scan_id,
                    runner=FakeRunner(self.paths, grype_commit=reported_commit),
                    environ={"CUADERNO_ENV": "local"}, expected_tool_hash=self.tool_hash,
                    expected_zip_hash=self.zip_hash, expected_db_hash=self.db_hash,
                )
            self.assertFalse(self.paths.scan_dir.exists())
        self.assertEqual(runner.calls, [])

        def wrong_version(argv, **kwargs):
            runner.calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout="Version: 0.118.0\nGitCommit: wrong\n", stderr="")

        with self.assertRaises(subject.ImageAuditFailure):
            subject.run_audit(
                root=self.root, scan_id=self.scan_id, runner=wrong_version,
                environ={"CUADERNO_ENV": "local"}, expected_tool_hash=self.tool_hash,
                expected_zip_hash=self.zip_hash, expected_db_hash=self.db_hash,
            )
        self.assertFalse(self.paths.scan_dir.exists())

        db_runner = FakeRunner(self.paths)
        with self.assertRaises(subject.ImageAuditFailure):
            subject.run_audit(
                root=self.root, scan_id=self.scan_id, runner=db_runner,
                environ={"CUADERNO_ENV": "test"}, expected_tool_hash=self.tool_hash,
                expected_zip_hash=self.zip_hash, expected_db_hash="f" * 64,
            )
        self.assertFalse(self.paths.scan_dir.exists())

    def test_grype_binary_and_release_zip_are_rehashed_immediately_before_and_after_scan(self):
        for index, mutation in enumerate(("before", "after")):
            scan_id = f"12345678-1234-4234-8234-{700 + index:012d}"
            paths = subject.audit_paths(self.root, scan_id)
            runner = FakeRunner(
                paths,
                mutate_tool_before_scan=mutation == "before",
                mutate_tool_after_scan=mutation == "after",
            )
            with self.subTest(mutation=mutation), self.assertRaises(subject.ImageAuditFailure):
                self.run_audit(runner, scan_id=scan_id)
            self.assertFalse(paths.summary.exists())

            # Restore the shared pinned fixture for the next subcase.
            paths.tool.write_bytes(b"synthetic pinned grype")
            paths.zip_archive.write_bytes(b"synthetic official archive")

    def test_db_stamp_and_status_identity_are_exact_and_stat_races_fail_closed(self):
        stamp_mutations = (
            {"digest": "xxh64:other"},
            {"client_version": "v6.1.8"},
            {"source": "https://grype.anchore.io/databases/other"},
        )
        for index, mutation in enumerate(stamp_mutations):
            scan_id = f"12345678-1234-4234-8234-{800 + index:012d}"
            paths = subject.audit_paths(self.root, scan_id)
            stamp = {
                "digest": subject.DB_DIGEST, "source": subject.DB_SOURCE,
                "client_version": subject.DB_CLIENT_VERSION,
            }
            stamp.update(mutation)
            paths.db_stamp.write_text(json.dumps(stamp), encoding="utf-8")
            with self.subTest(stamp=mutation), self.assertRaises(subject.ImageAuditFailure):
                self.run_audit(FakeRunner(paths), scan_id=scan_id)
        self.paths.db_stamp.write_text(json.dumps({
            "digest": subject.DB_DIGEST, "source": subject.DB_SOURCE,
            "client_version": subject.DB_CLIENT_VERSION,
        }), encoding="utf-8")

        status_mutations = (
            {"schemaVersion": 5},
            {"error": "database unavailable"},
            {"location": str(self.root / "foreign/vulnerability.db")},
        )
        for index, mutation in enumerate(status_mutations):
            scan_id = f"12345678-1234-4234-8234-{900 + index:012d}"
            paths = subject.audit_paths(self.root, scan_id)
            runner = FakeRunner(paths)
            original = runner.__call__

            def changed_status(argv, _mutation=mutation, **kwargs):
                result = original(argv, **kwargs)
                normalized = list(map(str, argv))
                if normalized[1:] == ["db", "status", "-o", "json"]:
                    payload = json.loads(result.stdout)
                    payload.update(_mutation)
                    return subprocess.CompletedProcess(normalized, 0, stdout=json.dumps(payload), stderr="")
                return result

            with self.subTest(status=mutation), self.assertRaises(subject.ImageAuditFailure):
                self.run_audit(changed_status, scan_id=scan_id)

        original_stat = Path.stat

        def racing_stat(path, *args, **kwargs):
            if Path(path) == self.paths.database:
                raise OSError("synthetic stat race")
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", racing_stat), self.assertRaises(subject.ImageAuditFailure):
            self.run_audit(FakeRunner(self.paths))

    def test_exact_findings_scan_uses_pinned_offline_environment_and_returns_two(self):
        runner = FakeRunner(self.paths)
        status, summary = self.run_audit(
            runner,
            environment={"CUADERNO_ENV": "dev", "GRYPE_DB_AUTO_UPDATE": "true", "SECRET_KEY": "never-forward"},
        )
        self.assertEqual(status, 2)
        self.assertEqual(summary["image_id"], IMAGE_ID)
        self.assertEqual(summary["source_commit"], SOURCE_REF)
        self.assertEqual(summary["matches"], 1)
        self.assertEqual(summary["severity_counts"], {"High": 1})
        self.assertEqual(summary["scanner_exit"], 2)
        self.assertTrue(self.paths.report.is_file())
        self.assertTrue(self.paths.archive.is_file())
        self.assertTrue(self.paths.summary.is_file())
        scan_call = next(call for call in runner.calls if "--fail-on" in call[0])
        self.assertEqual(scan_call[0], [
            str(self.paths.tool), "--fail-on", "negligible", "--scope", "squashed",
            "--output", "json", "--file", str(self.paths.report),
            f"docker-archive:{self.paths.archive}",
        ])
        environment = scan_call[1]["env"]
        self.assertEqual(environment["GRYPE_DB_CACHE_DIR"], str(self.paths.db_root))
        self.assertEqual(environment["GRYPE_CHECK_FOR_APP_UPDATE"], "false")
        self.assertEqual(environment["GRYPE_DB_AUTO_UPDATE"], "false")
        self.assertEqual(environment["GRYPE_EXTERNAL_SOURCES_ENABLE"], "false")
        self.assertNotIn("SECRET_KEY", environment)
        self.assertNotIn("GRYPE_CONFIG", environment)
        self.assertEqual(scan_call[1]["timeout"], subject.SCAN_TIMEOUT_SECONDS)
        save = next(call for call in runner.calls if call[0][:3] == ["docker", "image", "save"])
        self.assertEqual(save[0], ["docker", "image", "save", "--output", str(self.paths.archive), IMAGE_ID])
        self.assertEqual(save[1]["timeout"], subject.SAVE_TIMEOUT_SECONDS)
        self.assertTrue(all("timeout" in kwargs for _argv, kwargs in runner.calls))

    def test_clean_report_exit_zero_and_empty_ignored_matches_are_required(self):
        clean = FakeRunner(self.paths, report={
            "matches": [], "ignoredMatches": [],
            "source": {"type": "image", "target": {
                "userInput": f"docker-archive:{self.paths.archive}", "imageID": IMAGE_ID,
            }},
            "descriptor": {"name": "grype", "version": "0.119.0"},
        }, scanner_status=0)
        status, summary = self.run_audit(clean)
        self.assertEqual(status, 0)
        self.assertEqual(summary["status"], "clean")
        self.assertEqual(summary["matches"], 0)

        ignored_id = "12345678-1234-4234-8234-000000000077"
        ignored_paths = subject.audit_paths(self.root, ignored_id)
        ignored = FakeRunner(ignored_paths)
        ignored.report["ignoredMatches"] = [{"vulnerability": {"id": "CVE-IGNORED"}}]
        with self.assertRaises(subject.ImageAuditFailure):
            self.run_audit(ignored, scan_id=ignored_id)

    def test_final_container_archive_and_database_integrity_are_rechecked(self):
        cases = (
            FakeRunner(self.paths, final_container=container_document(Image="sha256:" + "e" * 64)),
            FakeRunner(self.paths, mutate_archive=True),
            FakeRunner(self.paths, mutate_database=True),
        )
        for index, template in enumerate(cases):
            scan_id = f"12345678-1234-4234-8234-{100 + index:012d}"
            paths = subject.audit_paths(self.root, scan_id)
            runner = FakeRunner(
                paths, final_container=template.final_container,
                mutate_archive=template.mutate_archive, mutate_database=template.mutate_database,
            )
            with self.subTest(index=index), self.assertRaises(subject.ImageAuditFailure):
                self.run_audit(runner, scan_id=scan_id)

    def test_timeout_and_non_utf8_process_output_become_controlled_failures(self):
        for failure in (
            subprocess.TimeoutExpired(["synthetic"], 1),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
        ):
            def failing_runner(_argv, **_kwargs):
                raise failure

            with self.subTest(failure=type(failure).__name__), self.assertRaises(subject.ImageAuditFailure):
                subject.run_audit(
                    root=self.root, scan_id=self.scan_id, runner=failing_runner,
                    environ={"CUADERNO_ENV": "test"}, expected_tool_hash=self.tool_hash,
                    expected_zip_hash=self.zip_hash, expected_db_hash=self.db_hash,
                )

    def test_report_rejects_nan_wrong_source_empty_and_unexpected_scanner_exit(self):
        cases = []
        wrong_source = FakeRunner(self.paths)
        wrong_source.report["source"]["target"]["imageID"] = "sha256:" + "f" * 64
        cases.append(wrong_source)
        cases.append(FakeRunner(self.paths, report={}))
        cases.append(FakeRunner(self.paths, scanner_status=1))
        for index, runner in enumerate(cases):
            scan_id = f"12345678-1234-4234-8234-{index + 1:012d}"
            paths = subject.audit_paths(self.root, scan_id)
            runner.paths = paths
            if isinstance(runner.report, dict) and runner.report.get("source"):
                runner.report["source"]["target"]["userInput"] = f"docker-archive:{paths.archive}"
            with self.subTest(index=index), self.assertRaises(subject.ImageAuditFailure):
                subject.run_audit(
                    root=self.root, scan_id=scan_id, runner=runner,
                    environ={"CUADERNO_ENV": "test"}, expected_tool_hash=self.tool_hash,
                    expected_zip_hash=self.zip_hash,
                    expected_db_hash=self.db_hash,
                )

        nan_id = "12345678-1234-4234-8234-999999999999"
        nan_paths = subject.audit_paths(self.root, nan_id)
        nan_runner = FakeRunner(nan_paths)
        original = nan_runner.__call__

        def nan_call(argv, **kwargs):
            result = original(argv, **kwargs)
            if list(map(str, argv))[0] == str(nan_paths.tool) and "--fail-on" in argv:
                nan_paths.report.write_text('{"matches":[],"probe":NaN}', encoding="utf-8")
            return result

        with self.assertRaises(subject.ImageAuditFailure):
            subject.run_audit(
                root=self.root, scan_id=nan_id, runner=nan_call,
                environ={"CUADERNO_ENV": "test"}, expected_tool_hash=self.tool_hash,
                expected_zip_hash=self.zip_hash,
                expected_db_hash=self.db_hash,
            )

    def test_environment_and_cli_are_closed(self):
        for environment in ({}, {"CUADERNO_ENV": "production"}, {"CUADERNO_ENV": "local", "CUADERNO_IMAGE": IMAGE_ID}):
            with self.subTest(environment=environment), self.assertRaises(subject.ImageAuditFailure):
                subject.run_audit(
                    root=self.root, scan_id=self.scan_id, runner=lambda *_a, **_k: self.fail("must not run"),
                    environ=environment, expected_tool_hash=self.tool_hash, expected_zip_hash=self.zip_hash,
                    expected_db_hash=self.db_hash,
                )
        with patch.object(subject, "run_audit", return_value=(0, {"status": "clean"})) as run:
            self.assertEqual(subject.main([]), 0)
            run.assert_called_once()
        with self.assertRaises(subject.ImageAuditFailure):
            subject.main(["sha256:" + "e" * 64])


if __name__ == "__main__":
    unittest.main()
