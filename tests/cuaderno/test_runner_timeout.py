import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


CHECK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "cuaderno" / "check.py"
SPEC = importlib.util.spec_from_file_location("cuaderno_check", CHECK_PATH)
assert SPEC and SPEC.loader
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class RunnerTimeoutTests(unittest.TestCase):
    def test_timeout_preserves_sanitized_partial_output_and_records_failure(self):
        secret = "runner-secret-value"
        samples = (
            (f"avance uno\nTOKEN={secret}\n".encode("utf-8") + b"byte-invalido:\xff", "byte-invalido:\ufffd"),
            (f"avance dos\nTOKEN={secret}\n", "avance dos"),
        )
        for partial, expected in samples:
            with self.subTest(output_type=type(partial).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry_dir = root / "tooling" / "cuaderno"
                registry_dir.mkdir(parents=True)
                (registry_dir / "commands.json").write_text(json.dumps({
                    "schema_version": 1,
                    "commands": {
                        "slow": {
                            "verified": True,
                            "argv": ["synthetic-slow-check"],
                            "cwd": ".",
                            "timeout_seconds": 3,
                            "verified_at_commit": "fixture",
                            "purpose": "Probar salida parcial de timeout",
                        }
                    },
                }), encoding="utf-8")
                timeout = subprocess.TimeoutExpired(["synthetic-slow-check"], 3, output=partial)
                git_result = subprocess.CompletedProcess(["git", "rev-parse", "HEAD"], 0, stdout="abc123\n")

                console = io.StringIO()
                with patch.dict(check.os.environ, {"CUADERNO_TEST_TOKEN": secret, "CUADERNO_ENV": "test"}), patch.object(
                    check.subprocess, "run", side_effect=[timeout, git_result]
                ), redirect_stdout(console):
                    code = check.execute(root, "slow")

                self.assertEqual(code, 124)
                records = list((root / ".cuaderno-runs").glob("*.json"))
                logs = list((root / ".cuaderno-runs").glob("*.log"))
                self.assertEqual(len(records), 1)
                self.assertEqual(len(logs), 1)
                record = json.loads(records[0].read_text(encoding="utf-8"))
                log = logs[0].read_text(encoding="utf-8")
                self.assertEqual(record["exit_code"], 124)
                self.assertFalse(record["passed"])
                self.assertIn(expected, log)
                self.assertIn("TIMEOUT:", log)
                self.assertIn("[REDACTED]", log)
                self.assertNotIn(secret, log)
                self.assertNotIn(secret, console.getvalue())
                self.assertIn("[REDACTED]", console.getvalue())


if __name__ == "__main__":
    unittest.main()
