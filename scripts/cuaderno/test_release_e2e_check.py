from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import release_e2e_check as subject
else:
    import release_e2e_check as subject


IMAGE = "sha256:" + "a" * 64


class ReleaseE2ECheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.e2e = self.root / "tests/cuaderno/e2e"
        (self.e2e / "node_modules/@playwright/test").mkdir(parents=True)
        (self.e2e / "node_modules/playwright").mkdir(parents=True)
        (self.e2e / "node_modules/playwright-core").mkdir(parents=True)
        package = {
            "devDependencies": {"@playwright/test": "1.63.0"},
        }
        lock = {"lockfileVersion": 3, "packages": {
            "": {"devDependencies": {"@playwright/test": "1.63.0"}},
            "node_modules/@playwright/test": {
                "version": "1.63.0", "dependencies": {"playwright": "1.63.0"},
            },
            "node_modules/playwright": {
                "version": "1.63.0", "dependencies": {"playwright-core": "1.63.0"},
            },
            "node_modules/playwright-core": {"version": "1.63.0"},
        }}
        (self.e2e / "package.json").write_text(json.dumps(package), encoding="utf-8")
        (self.e2e / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        (self.e2e / "node_modules/@playwright/test/package.json").write_text(
            json.dumps({"version": "1.63.0"}), encoding="utf-8",
        )
        (self.e2e / "node_modules/playwright/package.json").write_text(
            json.dumps({"version": "1.63.0"}), encoding="utf-8",
        )
        (self.e2e / "node_modules/playwright-core/package.json").write_text(
            json.dumps({"version": "1.63.0"}), encoding="utf-8",
        )
        (self.e2e / "node_modules/playwright/cli.js").write_text("", encoding="utf-8")
        (self.root / ".cuaderno-runs").mkdir()
        hash_patch = patch.object(subject, "_sha256", return_value=subject.WINDOWS_NODE_SHA256)
        hash_patch.start()
        self.addCleanup(hash_patch.stop)

    @staticmethod
    def inspection(*, image=IMAGE, healthy=True, running=True, bindings=None):
        bindings = bindings or {
            "80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}],
        }
        return [{
            "Image": image,
            "Config": {"Image": image},
            "State": {"Running": running, "Health": {"Status": "healthy" if healthy else "unhealthy"}},
            "HostConfig": {"PortBindings": bindings},
            "NetworkSettings": {"Ports": bindings},
        }]

    def version_runner(self, argv, **kwargs):
        if argv[-1] == "--version" and len(argv) == 2:
            return subprocess.CompletedProcess(argv, 0, "v24.21.0\n", "")
        return subprocess.CompletedProcess(argv, 0, "Version 1.63.0\n", "")

    def test_valid_run_forces_exact_local_runner_environment_and_preserves_failure(self):
        calls = []
        inspections = [self.inspection(), self.inspection()]

        def inspect_runner(argv, **kwargs):
            calls.append(("inspect", argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, json.dumps(inspections.pop(0)), "")

        def browser_runner(argv, **kwargs):
            calls.append(("browser", argv, kwargs))
            return 7, ""

        with patch.dict(os.environ, {
            "CUADERNO_CANDIDATE_IMAGE": IMAGE,
            "BASE_URL": "https://attacker.invalid",
            "CUADERNO_E2E_OUTPUT_DIR": "outside",
            "CUADERNO_E2E_HTML_REPORT": "outside",
        }, clear=False):
            code = subject.run(
                root=self.root, runner=browser_runner, inspect_runner=inspect_runner,
                version_runner=self.version_runner, run_id="fixed",
            )

        self.assertEqual(code, 7)
        self.assertEqual([item[0] for item in calls], ["inspect", "browser", "inspect"])
        argv, kwargs = calls[1][1], calls[1][2]
        self.assertEqual(argv, [subject.node_executable(), str(self.e2e / "node_modules/playwright/cli.js"), "test", "--retries=0"])
        self.assertNotIn("npx", " ".join(argv).lower())
        self.assertEqual(kwargs["cwd"], self.e2e)
        self.assertEqual(kwargs["env"]["BASE_URL"], "http://127.0.0.1:18081")
        self.assertEqual(kwargs["env"]["CI"], "1")
        self.assertEqual(
            kwargs["env"]["CUADERNO_E2E_OUTPUT_DIR"],
            str(self.root / ".cuaderno-runs/e2e-final-fixed/test-results"),
        )
        self.assertEqual(
            kwargs["env"]["CUADERNO_E2E_HTML_REPORT"],
            str(self.root / ".cuaderno-runs/e2e-final-fixed/playwright-report"),
        )

    def test_valid_browser_success_is_returned_after_both_image_checks(self):
        inspections = [self.inspection(), self.inspection()]
        with patch.dict(os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}, clear=False):
            code = subject.run(
                root=self.root,
                runner=lambda argv, **kwargs: (0, ""),
                inspect_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, json.dumps(inspections.pop(0)), "",
                ),
                version_runner=self.version_runner,
            )
        self.assertEqual(code, 0)
        self.assertEqual(inspections, [])

    def test_image_mismatch_before_run_fails_closed(self):
        called = False

        def browser_runner(*_args, **_kwargs):
            nonlocal called
            called = True
            return 0, ""

        with patch.dict(os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}):
            code = subject.run(
                root=self.root, runner=browser_runner,
                inspect_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, json.dumps(self.inspection(image="sha256:" + "b" * 64)), "",
                ), version_runner=self.version_runner,
            )
        self.assertEqual(code, 125)
        self.assertFalse(called)

    def test_post_run_drift_overrides_browser_success_and_is_always_checked(self):
        inspections = [self.inspection(), self.inspection(image="sha256:" + "b" * 64)]
        with patch.dict(os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}):
            code = subject.run(
                root=self.root, runner=lambda argv, **kwargs: (0, ""),
                inspect_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, json.dumps(inspections.pop(0)), "",
                ), version_runner=self.version_runner,
            )
        self.assertEqual(code, 125)
        self.assertEqual(inspections, [])

    def test_unhealthy_stopped_or_wrong_binding_is_rejected(self):
        cases = [
            self.inspection(healthy=False),
            self.inspection(running=False),
            self.inspection(bindings={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18081"}]}),
            self.inspection(bindings={
                "80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}],
                "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18443"}],
            }),
        ]
        for inspection in cases:
            def inspect_runner(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, json.dumps(inspection), "")

            with self.subTest(inspection=inspection), patch.dict(
                os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}, clear=False,
            ):
                self.assertEqual(subject.run(
                    root=self.root,
                    runner=lambda *_args, **_kwargs: self.fail("browser must not run"),
                    inspect_runner=inspect_runner, version_runner=self.version_runner,
                ), 125)

    def test_package_lock_or_installed_runner_version_drift_is_rejected(self):
        mutations = [
            (self.e2e / "package-lock.json", lambda value: value["packages"]["node_modules/playwright"].update(version="1.62.0")),
            (self.e2e / "node_modules/@playwright/test/package.json", lambda value: value.update(version="1.62.0")),
            (self.e2e / "node_modules/playwright-core/package.json", lambda value: value.update(version="1.62.0")),
        ]
        for path, mutate in mutations:
            original = path.read_text(encoding="utf-8")
            value = json.loads(original)
            mutate(value)
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(path=path):
                with self.assertRaises(subject.ReleaseE2EFailure):
                    subject.validate_toolchain(self.root, version_runner=self.version_runner)
            path.write_text(original, encoding="utf-8")

        with self.assertRaises(subject.ReleaseE2EFailure):
            subject.validate_toolchain(
                self.root,
                version_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, "v24.21.0\n" if len(argv) == 2 else "Version 1.62.0\n", "",
                ),
            )

        with self.assertRaises(subject.ReleaseE2EFailure):
            subject.validate_toolchain(
                self.root,
                version_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, "v24.20.0\n" if len(argv) == 2 else "Version 1.63.0\n", "",
                ),
            )

    def test_missing_local_cli_is_rejected_without_npx_fallback(self):
        (self.e2e / "node_modules/playwright/cli.js").unlink()
        with self.assertRaises(subject.ReleaseE2EFailure):
            subject.validate_toolchain(self.root, version_runner=self.version_runner)

    def test_timeout_kills_only_owned_process_tree_and_postflight_still_runs(self):
        cleanup = []
        waits = []

        class Process:
            pid = 4312
            returncode = None

            def __init__(self):
                self.calls = 0

            def communicate(self, timeout=None):
                waits.append(timeout)
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(["node"], timeout, output="partial\n")
                return "tail\n", None

        with patch.object(subject.os, "name", "nt"), \
             patch.object(subject.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, create=True):
            code, output = subject.run_process(
                ["node"], cwd=self.e2e, env={}, timeout=3,
                process_factory=lambda argv, **kwargs: Process(),
                cleanup_runner=lambda argv, **kwargs: (
                    cleanup.append((argv, kwargs)) or subprocess.CompletedProcess(argv, 0)
                ),
            )
        self.assertEqual(code, 124)
        self.assertEqual(output, "partial\ntail\n\nTIMEOUT tras 3s\n")
        self.assertEqual(cleanup[0][0], ["taskkill", "/PID", "4312", "/T", "/F"])
        self.assertEqual(waits, [3, 60])

        inspections = [self.inspection(), self.inspection()]
        with patch.dict(os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}, clear=False):
            code = subject.run(
                root=self.root,
                runner=lambda argv, **kwargs: (124, "TIMEOUT\n"),
                inspect_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, json.dumps(inspections.pop(0)), "",
                ),
                version_runner=self.version_runner,
            )
        self.assertEqual(code, 124)
        self.assertEqual(inspections, [])

    def test_failed_or_unbounded_timeout_cleanup_returns_125(self):
        class Process:
            pid = 9876

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(["node"], timeout, output="partial")

        with patch.object(subject.os, "name", "nt"), \
             patch.object(subject.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, create=True):
            failed, failed_output = subject.run_process(
                ["node"], cwd=self.e2e, env={}, timeout=2,
                process_factory=lambda argv, **kwargs: Process(),
                cleanup_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1),
            )
            bounded, bounded_output = subject.run_process(
                ["node"], cwd=self.e2e, env={}, timeout=2,
                process_factory=lambda argv, **kwargs: Process(),
                cleanup_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0),
            )
        self.assertEqual(failed, 125)
        self.assertIn("taskkill", failed_output)
        self.assertEqual(bounded, 125)
        self.assertIn("no terminó tras taskkill", bounded_output)

        inspections = [self.inspection(), self.inspection()]
        with patch.dict(os.environ, {"CUADERNO_CANDIDATE_IMAGE": IMAGE}, clear=False):
            run_code = subject.run(
                root=self.root,
                runner=lambda argv, **kwargs: (125, failed_output),
                inspect_runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                    argv, 0, json.dumps(inspections.pop(0)), "",
                ),
                version_runner=self.version_runner,
            )
        self.assertEqual(run_code, 125)
        self.assertEqual(inspections, [])

    def test_link_or_junction_ancestor_in_toolchain_is_rejected(self):
        original = Path.is_junction

        def fake_junction(path):
            return path.name == "node_modules" or original(path)

        with patch.object(Path, "is_junction", fake_junction):
            with self.assertRaises(subject.ReleaseE2EFailure):
                subject.validate_toolchain(self.root, version_runner=self.version_runner)


if __name__ == "__main__":
    unittest.main()
