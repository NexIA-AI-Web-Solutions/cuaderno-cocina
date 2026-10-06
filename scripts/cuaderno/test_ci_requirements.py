"""Execute the dependency extraction commands used by the backend CI jobs."""

from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml


class CIRequirementsTests(unittest.TestCase):
    def test_backend_jobs_extract_test_pins_from_the_checkout_directory(self):
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/cuaderno.yml").read_text(encoding="utf-8"))
        for job in ("backend-cuaderno-postgresql", "backend-native-postgresql"):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as temporary:
                checkout = Path(temporary)
                (checkout / "requirements.txt").write_text(
                    "Django==5.2.17\n# Development\npytest== 9.0.3\npytest-django==4.11.1\n",
                    encoding="utf-8",
                )
                commands = [line for step in workflow["jobs"][job]["steps"]
                            for line in step.get("run", "").splitlines() if "_dev_requirements" in line]
                self.assertEqual(len(commands), 1)
                command = shlex.split(commands[0])
                self.assertEqual(command[:2], ["python", "-c"])
                output = checkout / "test-requirements.txt"
                code = command[2].replace("/tmp/cuaderno-test-requirements.txt", output.as_posix())
                # Load the real helper from the repository while exercising the
                # command's relative paths from an independent checkout.
                code = f"import sys; sys.path.insert(0, {str(root)!r}); " + code
                result = subprocess.run([sys.executable, "-c", code], cwd=checkout,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(encoding="utf-8").splitlines(),
                                 ["pytest==9.0.3", "pytest-django==4.11.1"])


if __name__ == "__main__":
    unittest.main()
