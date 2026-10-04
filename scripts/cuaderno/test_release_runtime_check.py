import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

if __package__:
    from . import release_runtime_check as subject
else:
    import release_runtime_check as subject


IMAGE = "sha256:" + "c" * 64
SOURCE = "a" * 40 + "+worktree." + "b" * 64


class RuntimeCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / ".cuaderno-runs").mkdir()
        (self.root / "cuaderno/tests").mkdir(parents=True)
        (self.root / "cookbook/tests").mkdir(parents=True)
        (self.root / "tooling/cuaderno").mkdir(parents=True)
        self.schema = self.root / "tooling/cuaderno/openapi.json"
        self.schema.write_text('{"openapi":"3.0.3","paths":{"/health":{}}}', encoding="utf-8")
        self.test_constraints = self.root / "tooling/cuaderno/python-test.constraints.txt"
        self.test_constraints.write_text("pytest==9.0.3\n", encoding="utf-8")
        (self.root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text(
            "Django==5.2.12\n# Development\npytest== 9.0.3\npytest-django==4.11.1\n",
            encoding="utf-8",
        )
        self.env_file = self.root / "local.env"
        self.password = "db-password-that-must-not-leak"
        self.secret = "secret-key-that-must-not-leak-123456"
        self.env_file.write_text(
            f"CUADERNO_LOCAL_DB_PASSWORD={self.password}\nCUADERNO_LOCAL_SECRET_KEY={self.secret}\n",
            encoding="utf-8",
        )
        artifacts = {"runtime_application": "2" * 64,
                     "sbom_python": "d" * 64, "sbom_frontend": "e" * 64,
                     "frontend_provenance": "f" * 64, "version_info": "1" * 64,
                     "security_python_backports": "3" * 64, "security_alpine_backports": "4" * 64,
                     "security_node_runtime": "5" * 64}
        labels = {"io.cuaderno.source-identity": SOURCE}
        self.context = {"image_id": IMAGE, "source_identity": SOURCE,
                        "environment": {"image": {"labels": labels, "artifacts": artifacts,
                                                   "release_manifest": {"schema_version": 1,
                                                                        "source_identity": SOURCE,
                                                                        "artifacts": artifacts}}}}
        self.context_path = self.root / ".cuaderno-runs/candidate.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    @staticmethod
    def valid(_context, _root):
        return None

    @staticmethod
    def preview(_root, _container):
        return IMAGE, "cuaderno-release_default"

    def test_test_check_uses_exact_image_private_network_readonly_sources_and_temp_overlay(self):
        observed = {}
        def runner(argv, **kwargs):
            observed["argv"] = argv
            env_path = Path(argv[argv.index("--env-file") + 1])
            observed["env"] = env_path.read_text(encoding="utf-8")
            observed.update(kwargs)
            return 0, f"PASS without {self.password}\n"
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, output = subject.execute(
                "integration-final", self.context_path, root=self.root, local_env=self.env_file,
                context_validator=self.valid, preview_inspector=self.preview, process_runner=runner,
            )
        self.assertEqual(code, 0)
        self.assertEqual(observed["argv"][-3:], [IMAGE, subject.BAKED_SCRIPT, "--inside", "integration-final"][-3:])
        joined = " ".join(observed["argv"])
        self.assertIn("readonly", joined)
        self.assertIn("target=/opt/recipes/cuaderno/tests", joined)
        self.assertIn("target=/opt/recipes/cookbook/tests", joined)
        self.assertIn("/release-tests/dev-requirements.txt", joined)
        self.assertIn("target=/release-tests/python-test.constraints.txt,readonly", joined)
        self.assertNotIn(self.password, joined)
        self.assertRegex(observed["env"], r"TEST_POSTGRES_DB=cuaderno_test_integration_[0-9a-f]{12}")
        self.assertNotIn(self.password, output)

    def test_preview_must_run_exact_candidate_and_labels_must_match(self):
        with patch.dict(os.environ, {"CUADERNO_ENV": "local"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            with self.assertRaisesRegex(subject.RuntimeCheckFailure, "imagen candidata exacta"):
                subject.execute("runtime-pip-check", self.context_path, root=self.root,
                                local_env=self.env_file, context_validator=self.valid,
                                preview_inspector=lambda *_: ("sha256:" + "9" * 64, "network"),
                                process_runner=lambda *_args, **_kwargs: self.fail("must not run"))
            self.context["environment"]["image"]["release_manifest"]["source_identity"] = "wrong"
            self.context_path.write_text(json.dumps(self.context), encoding="utf-8")
            with self.assertRaisesRegex(subject.RuntimeCheckFailure, "declaración"):
                subject.execute("runtime-pip-check", self.context_path, root=self.root,
                                local_env=self.env_file, context_validator=self.valid,
                                preview_inspector=self.preview,
                                process_runner=lambda *_args, **_kwargs: self.fail("must not run"))

    def test_timeout_floor_and_environment_guard_fail_closed(self):
        with patch.object(subject, "ROOT", self.root):
            with patch.dict(os.environ, {"CUADERNO_ENV": "production"}, clear=False):
                with self.assertRaisesRegex(subject.RuntimeCheckFailure, "local/test"):
                    subject.execute("runtime-pip-check", self.context_path, root=self.root,
                                    local_env=self.env_file, context_validator=self.valid,
                                    preview_inspector=self.preview)
            with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False):
                with self.assertRaisesRegex(subject.RuntimeCheckFailure, "3600"):
                    subject.execute("runtime-pip-check", self.context_path, root=self.root,
                                    local_env=self.env_file, timeout=3599,
                                    context_validator=self.valid, preview_inspector=self.preview)

    def test_internal_test_plan_checks_production_before_overlay(self):
        calls = []
        with patch.object(subject, "_run_inside", side_effect=lambda argv: calls.append(argv) or 0):
            self.assertEqual(subject.inside("performance-final"), 0)
        self.assertEqual(calls[0], ["/opt/recipes/venv/bin/pip", "check"])
        self.assertEqual(calls[1][1:5], ["-m", "venv", "--system-site-packages", "/tmp/cuaderno-release-test-venv"])
        self.assertIn("/release-tests/dev-requirements.txt", calls[2])
        self.assertIn("/opt/recipes/PYTHON-PRODUCTION.constraints.txt", calls[2])
        self.assertIn("/release-tests/python-test.constraints.txt", calls[2])
        self.assertIn("cuaderno.tests.test_performance", calls[3])

    def test_runtime_pip_check_also_checks_native_extension_links_and_propagates_errors(self):
        calls = []
        def run(argv):
            calls.append(argv)
            return 0 if "check" in argv else 7
        with patch.object(subject, "_run_inside", side_effect=run):
            self.assertEqual(subject.inside("runtime-pip-check"), 7)
        self.assertEqual(calls[0], ["/opt/recipes/venv/bin/pip", "check"])
        self.assertIn("import xmlsec", calls[1][-1])
        self.assertIn("PIL._imaging", calls[1][-1])

    def test_frontend_provenance_reconciles_every_built_asset(self):
        calls = []
        with patch.object(subject, "_run_inside", side_effect=lambda argv: calls.append(argv) or 0):
            self.assertEqual(subject.inside("frontend-provenance"), 0)
        self.assertIn("/opt/recipes/release-tools/frontend_assets.py", calls[0])
        self.assertEqual(calls[0][-2:], ["--report", "/opt/recipes/cookbook/static/vue3/cuaderno-build-provenance.json"])

    def test_security_validates_schema_before_creating_test_overlay(self):
        calls = []
        def run(argv):
            calls.append(argv)
            if "--file" in argv:
                Path(argv[argv.index("--file") + 1]).write_text(self.schema.read_text(), encoding="utf-8")
            return 0
        with patch.object(subject, "_run_inside", side_effect=run), \
             patch.object(subject, "SCHEMA_REFERENCE", self.schema):
            self.assertEqual(subject.inside("security-final"), 0)
        self.assertEqual(calls[0], ["/opt/recipes/venv/bin/pip", "check"])
        self.assertIn("spectacular", calls[1])
        self.assertIn("--fail-on-warn", calls[1])
        self.assertEqual(calls[2][1:4], ["-m", "venv", "--system-site-packages"])

    def test_standalone_schema_fails_on_warnings(self):
        calls = []
        def run(argv):
            calls.append(argv)
            Path(argv[argv.index("--file") + 1]).write_text(self.schema.read_text(), encoding="utf-8")
            return 0
        with patch.object(subject, "_run_inside", side_effect=run), \
             patch.object(subject, "SCHEMA_REFERENCE", self.schema):
            self.assertEqual(subject.inside("schema-final"), 0)
        self.assertIn("--validate", calls[0])
        self.assertIn("--fail-on-warn", calls[0])
        self.assertIn("openapi-json", calls[0])

    def test_migrations_runs_pin_upgrade_against_same_candidate_and_propagates_failure(self):
        observed = {}
        def upgrade(argv, **kwargs):
            observed["argv"] = argv
            observed.update(kwargs)
            return subprocess.CompletedProcess(argv, 7, stdout="synthetic upgrade failed\n")
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, output = subject.execute(
                "migrations-final", self.context_path, root=self.root, local_env=self.env_file,
                context_validator=self.valid, preview_inspector=self.preview,
                process_runner=lambda *_args, **_kwargs: (0, "migration checks passed\n"),
                upgrade_runner=upgrade,
            )
        self.assertEqual(code, 7)
        self.assertIn("synthetic upgrade failed", output)
        self.assertEqual(observed["argv"], [
            os.sys.executable, str(self.root / "scripts/cuaderno/upgrade_smoke.py"),
        ])
        self.assertEqual(observed["env"]["CUADERNO_CANDIDATE_IMAGE"], IMAGE)
        self.assertEqual(observed["env"]["CUADERNO_SOURCE_IDENTITY"], SOURCE)
        self.assertEqual(observed["env"]["CUADERNO_CANDIDATE_CONTEXT"], str(self.context_path))
        self.assertEqual(observed["timeout"], subject.TIMEOUT_MAXIMUM)

    def test_migrations_does_not_claim_upgrade_when_candidate_migration_check_fails(self):
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, output = subject.execute(
                "migrations-final", self.context_path, root=self.root, local_env=self.env_file,
                context_validator=self.valid, preview_inspector=self.preview,
                process_runner=lambda *_args, **_kwargs: (3, "migrate check failed\n"),
                upgrade_runner=lambda *_args, **_kwargs: self.fail("upgrade must not run"),
            )
        self.assertEqual(code, 3)
        self.assertEqual(output, "migrate check failed\n")

    def test_schema_requires_snapshot_equality_and_reproducible_sdk(self):
        def divergent(argv):
            Path(argv[argv.index("--file") + 1]).write_text(
                '{"openapi":"3.0.3","paths":{"/other":{}}}', encoding="utf-8")
            return 0
        with patch.object(subject, "_run_inside", side_effect=divergent), \
             patch.object(subject, "SCHEMA_REFERENCE", self.schema):
            self.assertEqual(subject.inside("schema-final"), 1)

        observed = {}
        def sdk(argv, **kwargs):
            observed["argv"] = argv
            observed.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="SDK reproducible\n")
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, output = subject.execute(
                "schema-final", self.context_path, root=self.root, local_env=self.env_file,
                context_validator=self.valid, preview_inspector=self.preview,
                process_runner=lambda *_args, **_kwargs: (0, "schema matches\n"), sdk_runner=sdk,
            )
        self.assertEqual(code, 0)
        self.assertIn("SDK reproducible", output)
        self.assertEqual(observed["argv"][-3:], ["--schema", str(self.schema), "--check"])
        self.assertEqual(observed["cwd"], self.root)

    def test_schema_mount_uses_a_linux_target_on_windows_hosts(self):
        with patch.object(subject, "ROOT", self.root):
            argv = subject.docker_argv(
                "schema-final", self.context, "private", self.env_file,
                self.root / "requirements.txt", self.test_constraints,
                "cuaderno-release-check-schema",
            )
        mount = next(item for item in argv if "target=/release-reference/openapi.json" in item)
        self.assertTrue(mount.endswith("target=/release-reference/openapi.json,readonly"))

    def test_secret_output_is_redacted(self):
        with patch.dict(os.environ, {"CUADERNO_ENV": "development"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, output = subject.execute(
                "runtime-pip-check", self.context_path, root=self.root, local_env=self.env_file,
                context_validator=self.valid, preview_inspector=self.preview,
                process_runner=lambda *_args, **_kwargs: (1, self.password + " " + self.secret),
            )
        self.assertEqual(code, 1)
        self.assertEqual(output, "[REDACTED] [REDACTED]")

    def test_default_environment_is_the_compose_environment(self):
        compose_env = self.root / "data/cuaderno/local/compose.env"
        compose_env.parent.mkdir(parents=True)
        compose_env.write_text(self.env_file.read_text(encoding="utf-8"), encoding="utf-8")
        observed = {}
        def runner(argv, **_kwargs):
            observed["env"] = Path(argv[argv.index("--env-file") + 1]).read_text(encoding="utf-8")
            return 0, "ok\n"
        with patch.dict(os.environ, {"CUADERNO_ENV": "local"}, clear=False), \
             patch.object(subject, "ROOT", self.root):
            code, _ = subject.execute(
                "runtime-pip-check", self.context_path, root=self.root,
                context_validator=self.valid, preview_inspector=self.preview, process_runner=runner,
            )
        self.assertEqual(code, 0)
        self.assertIn(f"POSTGRES_PASSWORD={self.password}", observed["env"])

    def test_timeout_forcibly_removes_unique_container(self):
        class Process:
            pid = 4242
            returncode = None
            calls = 0
            def communicate(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(["docker"], timeout, output="partial\n")
                return "tail\n", None
        cleanup = []
        with patch.object(subject.subprocess, "Popen", return_value=Process()), \
             patch.object(subject.subprocess, "run", side_effect=lambda argv, **_kwargs: cleanup.append(argv)), \
             patch.object(subject.subprocess, "CREATE_NEW_PROCESS_GROUP", 0), \
             patch.object(subject.subprocess, "DEVNULL", -3):
            code, output = subject.run_container(["docker", "run"], root=self.root, timeout=3600,
                                                 container="cuaderno-release-check-deadbeef")
        self.assertEqual(code, 124)
        self.assertIn("TIMEOUT tras 3600s", output)
        self.assertIn(["docker", "rm", "-f", "cuaderno-release-check-deadbeef"], cleanup)


if __name__ == "__main__":
    unittest.main()
