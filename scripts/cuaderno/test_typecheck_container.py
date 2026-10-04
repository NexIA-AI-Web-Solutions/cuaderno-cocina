from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import typecheck_container as subject
else:
    import typecheck_container as subject


class TypecheckContainerTests(unittest.TestCase):
    IMAGE_ID = "sha256:" + "a" * 64

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "vue3").mkdir()
        (self.root / "vue3/package.json").write_text("{}\n", encoding="utf-8")
        (self.root / "vue3/tsconfig.app.json").write_text("{}\n", encoding="utf-8")
        (self.root / "vue3/yarn.lock").write_text("# frozen\n", encoding="utf-8")
        verifier = self.root / subject.VERIFIER_RELATIVE
        verifier.parent.mkdir(parents=True)
        verifier.write_text("// verifier\n", encoding="utf-8")
        (self.root / subject.MANIFEST_RELATIVE).write_text("{}\n", encoding="utf-8")
        (self.root / subject.DOCKERIGNORE_RELATIVE).write_text("**/node_modules\n", encoding="utf-8")
        dockerfile = self.root / subject.DOCKERFILE_RELATIVE
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text(
            f"FROM {subject.NODE_IMAGE} AS frontend\n"
            "WORKDIR /build/vue3\n"
            "COPY vue3/package.json vue3/yarn.lock ./\n"
            "RUN yarn install --frozen-lockfile --non-interactive\n"
            "COPY vue3/ ./\n",
            encoding="utf-8",
        )

    def test_builds_frontend_stage_and_runs_immutable_image_offline_readonly(self):
        dockerfile = self.root / subject.DOCKERFILE_RELATIVE
        self.assertEqual(subject.build_command(dockerfile=dockerfile, tag="source:test"), [
            "docker", "build", "--file", str(dockerfile), "--target", "frontend",
            "--tag", "source:test", ".",
        ])
        argv = subject.typecheck_command(
            image_id=self.IMAGE_ID,
            verifier=self.root / subject.VERIFIER_RELATIVE,
            manifest=self.root / subject.MANIFEST_RELATIVE,
            container="cuaderno-typecheck-abcdef123456",
        )
        self.assertEqual(argv[:8], ["docker", "run", "--rm", "--name", "cuaderno-typecheck-abcdef123456",
                                    "--network", "none", "--read-only"])
        mounts = [argv[index + 1] for index, value in enumerate(argv) if value == "--mount"]
        self.assertEqual(mounts, [
            f"type=bind,source={self.root / subject.VERIFIER_RELATIVE},target=/tooling/verify-typecheck-toolchain.mjs,readonly",
            f"type=bind,source={self.root / subject.MANIFEST_RELATIVE},target=/tooling/typecheck-toolchain.json,readonly",
        ])
        self.assertNotIn(str(self.root / "vue3"), " ".join(argv))
        self.assertEqual(argv[argv.index("--tmpfs") + 1], "/tmp:rw,noexec,nosuid,nodev,size=64m")
        self.assertEqual(argv[argv.index(self.IMAGE_ID) + 1:], [
            "sh", "-eu", "-c",
            "node /tooling/verify-typecheck-toolchain.mjs --project /build/vue3 "
            "--manifest /tooling/typecheck-toolchain.json && "
            "exec node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json "
            "--tsBuildInfoFile /tmp/cuaderno-typecheck.tsbuildinfo",
        ])
        shell = argv[-1]
        self.assertLess(shell.index("verify-typecheck-toolchain.mjs"), shell.index("vue-tsc.js"))
        self.assertNotIn("--skipLibCheck", argv)
        self.assertNotIn("typecheck_gate.py", argv)

    def test_build_inspect_run_sequence_uses_immutable_id_and_preserves_exit(self):
        observed = []

        def runner(argv, **kwargs):
            observed.append((argv, kwargs))
            if argv[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(argv, 0, stdout=f"{self.IMAGE_ID}\n")
            if argv[:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(argv, 2)
            return subprocess.CompletedProcess(argv, 0)

        cleanup = []
        with patch.object(subject.uuid, "uuid4", return_value=type("U", (), {"hex": "abcdef1234567890"})()):
            self.assertEqual(subject.run(
                root=self.root, runner=runner,
                cleanup_runner=lambda argv, **kwargs: cleanup.append((argv, kwargs)),
            ), 2)
        self.assertEqual([call[0][:2] for call in observed], [
            ["docker", "build"], ["docker", "image"], ["docker", "run"],
        ])
        run_argv = observed[2][0]
        self.assertIn(self.IMAGE_ID, run_argv)
        self.assertNotIn("cuaderno-typecheck-source:abcdef123456", run_argv)
        self.assertTrue(all(call[1]["cwd"] == self.root and call[1]["check"] is False for call in observed))
        self.assertEqual(cleanup[-1][0], ["docker", "image", "rm", "cuaderno-typecheck-source:abcdef123456"])

    def test_host_node_modules_is_irrelevant_and_dockerfile_pin_fails_closed(self):
        self.assertFalse((self.root / "vue3/node_modules").exists())
        subject.checkout(self.root)
        (self.root / subject.DOCKERFILE_RELATIVE).write_text(
            "FROM node:latest AS frontend\n", encoding="utf-8",
        )
        with self.assertRaises(subject.TypecheckContainerFailure):
            subject.run(root=self.root, runner=lambda *_args, **_kwargs: self.fail("must not run"))

    def test_frozen_install_source_copy_and_node_modules_exclusion_fail_closed(self):
        dockerfile = self.root / subject.DOCKERFILE_RELATIVE
        original = dockerfile.read_text(encoding="utf-8")
        dockerfile.write_text(original.replace("yarn install --frozen-lockfile", "yarn install"), encoding="utf-8")
        with self.assertRaises(subject.TypecheckContainerFailure):
            subject.checkout(self.root)
        dockerfile.write_text(original, encoding="utf-8")

        (self.root / subject.DOCKERIGNORE_RELATIVE).write_text(
            "**/node_modules\n!vue3/node_modules\n", encoding="utf-8",
        )
        with self.assertRaises(subject.TypecheckContainerFailure):
            subject.checkout(self.root)

    def test_build_failure_stops_pipeline_and_propagates(self):
        observed = []

        def runner(argv, **_kwargs):
            observed.append(argv)
            return subprocess.CompletedProcess(argv, 17)

        self.assertEqual(subject.run(
            root=self.root, runner=runner, cleanup_runner=lambda *_args, **_kwargs: None,
        ), 17)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][:2], ["docker", "build"])

    def test_timeout_is_distinct_and_cleans_container_and_tag(self):
        calls = 0

        def timeout(argv, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return subprocess.CompletedProcess(argv, 0)
            if calls == 2:
                return subprocess.CompletedProcess(argv, 0, stdout=f"{self.IMAGE_ID}\n")
            raise subprocess.TimeoutExpired(argv, subject.TIMEOUT_SECONDS)

        cleanup = []
        with patch.object(subject.uuid, "uuid4", return_value=type("U", (), {"hex": "abcdef1234567890"})()):
            self.assertEqual(subject.run(
                root=self.root, runner=timeout,
                cleanup_runner=lambda argv, **kwargs: cleanup.append((argv, kwargs)),
            ), 124)
        self.assertEqual(cleanup[0][0], ["docker", "rm", "-f", "cuaderno-typecheck-abcdef123456"])
        self.assertEqual(cleanup[0][1]["timeout"], 60)
        self.assertEqual(cleanup[1][0], ["docker", "image", "rm", "cuaderno-typecheck-source:abcdef123456"])


class TypecheckToolchainVerifierTests(unittest.TestCase):
    VERIFIER = Path(__file__).resolve().parents[2] / subject.VERIFIER_RELATIVE

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "vue3"
        self.project.mkdir()
        (self.project / "yarn.lock").write_text("# exact frozen lock\n", encoding="utf-8")
        self.package("vue-tsc", "3.3.5", dependencies={"dep-a": "1.0.0"},
                     peerDependencies={"typescript": ">=5"}, files={"bin/vue-tsc.js": "compiler\n"})
        self.package("typescript", "5.9.3", files={"lib/typescript.js": "typescript\n"})
        self.package("dep-a", "1.0.0", dependencies={"dep-b": "1.0.0"}, files={"index.js": "a\n"})
        self.package("dep-b", "1.0.0", files={"index.js": "b\n"})
        self.manifest = self.root / "manifest.json"
        generated = self.run_verifier("--generate")
        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.manifest.write_text(generated.stdout, encoding="utf-8")

    def package(self, name, version, *, dependencies=None, peerDependencies=None, files=None):
        directory = self.project / "node_modules" / Path(*name.split("/"))
        directory.mkdir(parents=True, exist_ok=True)
        document = {"name": name, "version": version}
        if dependencies is not None:
            document["dependencies"] = dependencies
        if peerDependencies is not None:
            document["peerDependencies"] = peerDependencies
        (directory / "package.json").write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        for relative, contents in (files or {}).items():
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents, encoding="utf-8")
        return directory

    def run_verifier(self, *extra):
        argv = ["node", str(self.VERIFIER), "--project", str(self.project)]
        if "--generate" not in extra:
            argv.extend(["--manifest", str(self.manifest)])
        argv.extend(extra)
        return subprocess.run(argv, check=False, capture_output=True, text=True, encoding="utf-8")

    def assert_rejected(self):
        completed = self.run_verifier()
        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("TYPECHECK TOOLCHAIN ERROR", completed.stderr)

    def test_accepts_exact_recursive_runtime_closure(self):
        completed = self.run_verifier()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["packages"], 4)

    def test_rejects_compiler_and_transitive_dependency_tamper(self):
        for target in (
            self.project / "node_modules/vue-tsc/bin/vue-tsc.js",
            self.project / "node_modules/dep-b/index.js",
        ):
            original = target.read_bytes()
            with self.subTest(target=target.name):
                target.write_bytes(original + b"tamper")
                self.assert_rejected()
                target.write_bytes(original)

    def test_rejects_version_missing_and_extra_closure_dependency(self):
        package_json = self.project / "node_modules/dep-a/package.json"
        original = package_json.read_text(encoding="utf-8")
        document = json.loads(original)
        document["version"] = "2.0.0"
        package_json.write_text(json.dumps(document), encoding="utf-8")
        self.assert_rejected()
        package_json.write_text(original, encoding="utf-8")

        dependency = self.project / "node_modules/dep-b"
        hidden = self.root / "missing-dep-b"
        dependency.rename(hidden)
        self.assert_rejected()
        hidden.rename(dependency)

        self.package("dep-extra", "1.0.0", files={"index.js": "extra\n"})
        document = json.loads(original)
        document["dependencies"]["dep-extra"] = "1.0.0"
        package_json.write_text(json.dumps(document), encoding="utf-8")
        self.assert_rejected()

    def test_rejects_lock_drift_and_symlink(self):
        lockfile = self.project / "yarn.lock"
        lockfile.write_text("# drift\n", encoding="utf-8")
        self.assert_rejected()
        lockfile.write_text("# exact frozen lock\n", encoding="utf-8")

        link = self.project / "node_modules/dep-a/linked.js"
        target = self.project / "node_modules/dep-a/index.js"
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"El host no permite crear symlinks de prueba: {exc}")
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
