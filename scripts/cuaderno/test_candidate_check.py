import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import candidate_check as subject
else:
    import candidate_check as subject


class CandidateCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "tooling/cuaderno").mkdir(parents=True)
        (self.root / ".gitignore").write_text(".cuaderno-runs/\n", encoding="utf-8")
        self.registry = self.root / "tooling/cuaderno/commands.json"
        self.registry.write_text(json.dumps({"schema_version": 1, "commands": {
            "demo": {"verified": True, "argv": ["demo", "--safe"], "cwd": ".",
                     "timeout_seconds": 10, "isolated_mutations": False},
        }}), encoding="utf-8")
        self.context = {
            "schema_version": 1, "candidate_id": "7f90be2e-c663-43e7-914a-6efac5524841", "git_commit": "a" * 40,
            "source_sha256": "b" * 64, "source_identity": "a" * 40 + "+worktree." + "b" * 64,
            "image_id": "sha256:" + "c" * 64, "environment_fingerprint": "d" * 64,
            "commands_registry_sha256": "e" * 64, "environment": {},
        }
        (self.root / ".cuaderno-runs").mkdir()
        self.context_path = self.root / ".cuaderno-runs/candidate.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    @staticmethod
    def valid(_context, _root):
        return None

    def test_pass_record_contains_candidate_and_log_hash(self):
        observed = {}
        def run(argv, cwd, timeout, env):
            observed.update(env)
            return 0, "PASS\n"
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}):
            code, path = subject.execute(
                "demo", self.context_path, root=self.root,
                process_runner=run, context_validator=self.valid,
            )
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertTrue(record["passed"])
        self.assertEqual(record["candidate_id"], "7f90be2e-c663-43e7-914a-6efac5524841")
        log = path.parent / record["log"]
        self.assertEqual(record["log_bytes"], log.stat().st_size)
        self.assertEqual(len(record["log_sha256"]), 64)
        self.assertEqual(observed["CUADERNO_CANDIDATE_CONTEXT"], str(self.context_path))

    def test_after_command_drift_records_failure_even_when_command_passes(self):
        calls = 0
        def validate(_context, _root):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise subject.candidate_context.CandidateFailure("image changed")
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}):
            code, path = subject.execute(
                "demo", self.context_path, root=self.root,
                process_runner=lambda argv, cwd, timeout, env: (0, "command pass\n"), context_validator=validate,
            )
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 125)
        self.assertFalse(record["passed"])
        self.assertIn("image changed", record["failure"])

    def test_missing_registry_command_fails_before_execution(self):
        with self.assertRaisesRegex(subject.CandidateCheckFailure, "no verificado"):
            subject.execute("missing", self.context_path, root=self.root,
                            process_runner=lambda *_args: self.fail("must not execute"), context_validator=self.valid)


if __name__ == "__main__":
    unittest.main()
