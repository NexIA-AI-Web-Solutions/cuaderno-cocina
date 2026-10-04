from __future__ import annotations

import os
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.cuaderno import upgrade_smoke


RELEASE_IMAGE_ID = "sha256:" + "7" * 64
SUFFIX = "abcdef123456"
RETAINED_TAG = f"cuaderno-cocina:upgrade-{SUFFIX}"


class FakeDocker:
    def __init__(self, *, retained_image_id: str = RELEASE_IMAGE_ID):
        self.calls: list[list[str]] = []
        self.retained_image_id = retained_image_id

    def __call__(self, argv, **kwargs):
        command = list(argv)
        self.calls.append(command)
        if command[:4] == ["docker", "image", "inspect", upgrade_smoke.PIN_IMAGE]:
            stdout = upgrade_smoke.PIN_IMAGE_ID + "\n"
        elif command[:4] == ["docker", "image", "inspect", "cuaderno-cocina:local"]:
            stdout = RELEASE_IMAGE_ID + "\n"
        elif command[:4] == ["docker", "image", "inspect", RETAINED_TAG]:
            stdout = ("10001:10001\n" if command[-1] == "{{.Config.User}}"
                      else self.retained_image_id + "\n")
        elif command[:4] == ["docker", "image", "inspect", RELEASE_IMAGE_ID]:
            stdout = RELEASE_IMAGE_ID + "\n"
        else:
            stdout = ""
        return SimpleNamespace(stdout=stdout, returncode=0)


class UpgradeSmokeOrchestrationTests(unittest.TestCase):
    def run_main(self, docker: FakeDocker):
        uuids = [SimpleNamespace(hex="password-secret"), SimpleNamespace(hex=SUFFIX)]
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=True), patch.object(
            upgrade_smoke.uuid, "uuid4", side_effect=uuids
        ), patch.object(upgrade_smoke.subprocess, "run", side_effect=docker), patch.object(
            upgrade_smoke.time, "sleep"
        ):
            return upgrade_smoke.main()

    def test_retains_and_verifies_release_before_creating_network_or_database(self):
        docker = FakeDocker()

        self.assertEqual(self.run_main(docker), 0)

        tag_index = docker.calls.index(["docker", "tag", RELEASE_IMAGE_ID, RETAINED_TAG])
        verify_index = docker.calls.index(
            ["docker", "image", "inspect", RETAINED_TAG, "--format", "{{.Id}}"]
        )
        network_index = next(
            index
            for index, command in enumerate(docker.calls)
            if command[:3] == ["docker", "network", "create"]
        )
        database_index = next(
            index
            for index, command in enumerate(docker.calls)
            if command[:3] == ["docker", "run", "-d"]
        )
        self.assertLess(tag_index, verify_index)
        self.assertLess(verify_index, network_index)
        self.assertLess(verify_index, database_index)
        self.assertIn(["docker", "network", "create", "--internal", f"cuaderno-upgrade-{SUFFIX}"], docker.calls)

    def test_release_preflight_migration_and_assertions_use_only_retained_tag(self):
        docker = FakeDocker()

        self.run_main(docker)

        release_commands = [
            command
            for command in docker.calls
            if any("-release" in argument for argument in command)
            and command[1] in {"run", "create"}
        ]
        self.assertEqual(len(release_commands), 3)
        for command in release_commands:
            self.assertIn(RETAINED_TAG, command)
            self.assertNotIn("cuaderno-cocina:local", command)
            self.assertNotIn(RELEASE_IMAGE_ID, command)
        local_inspections = [
            command
            for command in docker.calls
            if command[:4] == ["docker", "image", "inspect", "cuaderno-cocina:local"]
        ]
        self.assertEqual(len(local_inspections), 1)
        assertion_command = next(
            command for command in release_commands
            if command[-3:-1] == ["shell", "-c"]
        )
        assertions = assertion_command[-1]
        self.assertIn("0017_release_integrity_and_allergen_audit", assertions)
        self.assertIn("cuaderno_package_positive_quantity", assertions)
        self.assertIn("cuaderno_price_current_cover", assertions)
        self.assertIn(
            ["docker", "image", "inspect", RETAINED_TAG, "--format", "{{.Config.User}}"],
            docker.calls,
        )

    def test_retained_image_mismatch_aborts_before_network_or_database_creation(self):
        docker = FakeDocker(retained_image_id="sha256:" + "8" * 64)

        with self.assertRaisesRegex(ValueError, "imagen retenida"):
            self.run_main(docker)

        self.assertIn(["docker", "tag", RELEASE_IMAGE_ID, RETAINED_TAG], docker.calls)
        self.assertFalse(
            any(command[:3] == ["docker", "network", "create"] for command in docker.calls)
        )
        self.assertFalse(any(command[:3] == ["docker", "run", "-d"] for command in docker.calls))

    def test_invalid_environment_aborts_without_invoking_docker(self):
        docker = FakeDocker()

        with patch.dict(os.environ, {"CUADERNO_ENV": "production"}, clear=True), patch.object(
            upgrade_smoke.subprocess, "run", side_effect=docker
        ):
            with self.assertRaisesRegex(ValueError, "entorno local aislado"):
                upgrade_smoke.main()

        self.assertEqual(docker.calls, [])

    def test_candidate_mode_requires_matching_context_and_uses_exact_image_id(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        evidence = root / ".cuaderno-runs"
        evidence.mkdir()
        source = "a" * 40 + "+worktree." + "b" * 64
        context = {"image_id": RELEASE_IMAGE_ID, "source_identity": source}
        context_path = evidence / "candidate.json"
        context_path.write_text(json.dumps(context), encoding="utf-8")
        validated = []
        docker = FakeDocker()
        environ = {
            "CUADERNO_ENV": "test", "CUADERNO_CANDIDATE_IMAGE": RELEASE_IMAGE_ID,
            "CUADERNO_SOURCE_IDENTITY": source, "CUADERNO_CANDIDATE_CONTEXT": str(context_path),
        }
        uuids = [SimpleNamespace(hex="password-secret"), SimpleNamespace(hex=SUFFIX)]
        with patch.object(upgrade_smoke, "ROOT", root), patch.object(
            upgrade_smoke.uuid, "uuid4", side_effect=uuids
        ), patch.object(upgrade_smoke.time, "sleep"):
            self.assertEqual(upgrade_smoke.main(
                environ=environ, process_runner=docker,
                context_validator=lambda document, checkout: validated.append((document, checkout)),
            ), 0)
        self.assertEqual(validated, [(context, root)])
        self.assertIn(
            ["docker", "image", "inspect", RELEASE_IMAGE_ID, "--format", "{{.Id}}"], docker.calls,
        )
        self.assertFalse(any("cuaderno-cocina:local" in command for command in docker.calls))

    def test_candidate_mode_rejects_context_mismatch_before_docker(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        evidence = root / ".cuaderno-runs"
        evidence.mkdir()
        path = evidence / "candidate.json"
        path.write_text(json.dumps({
            "image_id": "sha256:" + "8" * 64,
            "source_identity": "a" * 40 + "+worktree." + "b" * 64,
        }), encoding="utf-8")
        docker = FakeDocker()
        environ = {
            "CUADERNO_ENV": "test", "CUADERNO_CANDIDATE_IMAGE": RELEASE_IMAGE_ID,
            "CUADERNO_SOURCE_IDENTITY": "a" * 40 + "+worktree." + "b" * 64,
            "CUADERNO_CANDIDATE_CONTEXT": str(path),
        }
        with patch.object(upgrade_smoke, "ROOT", root), self.assertRaisesRegex(ValueError, "no coincide"):
            upgrade_smoke.main(environ=environ, process_runner=docker,
                               context_validator=lambda *_: self.fail("must not validate"))
        self.assertEqual(docker.calls, [])


if __name__ == "__main__":
    unittest.main()
