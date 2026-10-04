from __future__ import annotations

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
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        compiler = self.root / "vue3/node_modules/vue-tsc/bin/vue-tsc.js"
        compiler.parent.mkdir(parents=True)
        compiler.write_text("", encoding="utf-8")
        (self.root / "vue3/tsconfig.app.json").write_text("{}\n", encoding="utf-8")

    def test_command_is_exact_pinned_offline_readonly_typecheck(self):
        argv = subject.command(root=self.root, container="cuaderno-typecheck-abcdef123456")
        self.assertEqual(argv[:8], ["docker", "run", "--rm", "--name", "cuaderno-typecheck-abcdef123456",
                                    "--network", "none", "--mount"])
        mount = argv[8]
        self.assertEqual(mount, f"type=bind,source={self.root / 'vue3'},target=/project,readonly")
        self.assertIn(subject.NODE_IMAGE, argv)
        self.assertEqual(argv[argv.index(subject.NODE_IMAGE) + 1:], [
            "node", "node_modules/vue-tsc/bin/vue-tsc.js", "--noEmit", "-p", "tsconfig.app.json",
            "--tsBuildInfoFile", "/tmp/cuaderno-typecheck.tsbuildinfo",
        ])
        self.assertNotIn("--skipLibCheck", argv)
        self.assertNotIn("typecheck_gate.py", argv)

    def test_preserves_compiler_exit_and_uses_repo_as_host_cwd(self):
        observed = {}

        def runner(argv, **kwargs):
            observed["argv"] = argv
            observed.update(kwargs)
            return subprocess.CompletedProcess(argv, 2)

        self.assertEqual(subject.run(root=self.root, runner=runner), 2)
        self.assertEqual(observed["cwd"], self.root)
        self.assertFalse(observed["check"])
        self.assertEqual(observed["timeout"], subject.TIMEOUT_SECONDS)

    def test_missing_toolchain_fails_before_docker_and_timeout_is_distinct(self):
        (self.root / "vue3/node_modules/vue-tsc/bin/vue-tsc.js").unlink()
        with self.assertRaises(subject.TypecheckContainerFailure):
            subject.run(root=self.root, runner=lambda *_args, **_kwargs: self.fail("must not run"))

        (self.root / "vue3/node_modules/vue-tsc/bin/vue-tsc.js").write_text("", encoding="utf-8")

        def timeout(argv, **_kwargs):
            raise subprocess.TimeoutExpired(argv, subject.TIMEOUT_SECONDS)

        cleanup = []
        with patch.object(subject.uuid, "uuid4", return_value=type("U", (), {"hex": "abcdef1234567890"})()):
            self.assertEqual(subject.run(
                root=self.root, runner=timeout,
                cleanup_runner=lambda argv, **kwargs: cleanup.append((argv, kwargs)),
            ), 124)
        self.assertEqual(cleanup[0][0], ["docker", "rm", "-f", "cuaderno-typecheck-abcdef123456"])
        self.assertEqual(cleanup[0][1]["timeout"], 60)


if __name__ == "__main__":
    unittest.main()
