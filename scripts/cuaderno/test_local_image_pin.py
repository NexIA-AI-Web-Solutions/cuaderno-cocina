import json
from pathlib import Path
import tempfile
import unittest

from scripts.cuaderno import local_up


class LocalImagePinTests(unittest.TestCase):
    def test_pins_verified_build_id_and_preserves_secret_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "compose.env"
            environment.write_text("# privado\nCUADERNO_LOCAL_SECRET_KEY=synthetic\nCUADERNO_LOCAL_IMAGE=old\n", encoding="utf-8")
            identity = "a" * 40 + "+worktree." + "b" * 64
            calls = []
            def inspect(argv, **kwargs):
                calls.append(argv)
                return json.dumps([{"Id": "sha256:" + "c" * 64,
                    "Config": {"Labels": {"io.cuaderno.source-identity": identity}}}])
            image = local_up.pin_image("cuaderno-cocina:unique", environment, identity=identity, inspector=inspect)
            self.assertEqual(calls[0], ["docker", "image", "inspect", "cuaderno-cocina:unique"])
            self.assertEqual(image, "sha256:" + "c" * 64)
            self.assertEqual(environment.read_text(), "# privado\nCUADERNO_LOCAL_SECRET_KEY=synthetic\nCUADERNO_LOCAL_IMAGE=" + image + "\n")

    def test_mismatched_build_cannot_rewrite_preview_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "compose.env"
            environment.write_text("private-source\n", encoding="utf-8")
            def inspect(*args, **kwargs):
                return json.dumps([{"Id": "sha256:" + "c" * 64,
                    "Config": {"Labels": {"io.cuaderno.source-identity": "wrong"}}}])
            with self.assertRaises(ValueError):
                local_up.pin_image("unique", environment, identity="expected", inspector=inspect)
            self.assertEqual(environment.read_text(), "private-source\n")

    def test_ambiguous_image_is_rejected_before_environment_write(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "compose.env"
            environment.write_text("unchanged\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                local_up.pin_image("unique", environment, inspector=lambda *_args, **_kwargs: "[]")
            self.assertEqual(environment.read_text(), "unchanged\n")
