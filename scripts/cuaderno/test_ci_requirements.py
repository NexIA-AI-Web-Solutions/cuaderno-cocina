"""Execute the dependency extraction commands used by the backend CI jobs."""

from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml


class CIRequirementsTests(unittest.TestCase):
    def test_markdown_runtime_allows_its_exact_loopback_healthcheck_host(self):
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/cuaderno.yml").read_text(encoding="utf-8"))
        step = next(step for step in workflow["jobs"]["markdown-runtime"]["steps"]
                    if step.get("name") == "Arrancar runtime Markdown aislado")
        launch = step["run"].split('test "$(docker inspect', 1)[0].replace("\\\n", " ")
        arguments = shlex.split(launch)
        environment = dict(arguments[index + 1].split("=", 1)
                           for index, argument in enumerate(arguments) if argument == "-e")
        self.assertEqual(set(environment.get("ALLOWED_HOSTS", "").split(",")),
                         {"127.0.0.1", "localhost"})

    def test_typecheck_lockfile_has_the_exact_platform_independent_bytes(self):
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / "tooling/cuaderno/typecheck-toolchain.json").read_text(encoding="utf-8"))
        raw = (root / "vue3" / manifest["lockfile"]["path"]).read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["lockfile"]["sha256"])

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
