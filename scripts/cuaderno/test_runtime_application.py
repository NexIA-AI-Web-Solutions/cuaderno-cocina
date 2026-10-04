import shutil
import os
from pathlib import Path
import tempfile
import unittest

from scripts.cuaderno import runtime_application as subject


class RuntimeApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.runtime = self.root / "source", self.root / "runtime"
        for name in subject.DIRECTORIES:
            path = self.source / name / "module.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"real source\r\n")
        for target, source in subject.COPY_FILES.items():
            path = self.source / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.encode() + b"\r\n")
        shutil.copytree(self.source, self.runtime)
        for target, source in subject.COPY_FILES.items():
            path = self.runtime / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.source / source, path)
        (self.runtime / "boot.sh").write_bytes((self.runtime / "boot.sh").read_bytes().replace(b"\r\n", b"\n"))
        (self.runtime / "boot.sh").chmod(0o755)

    def runtime_build(self):
        # Windows exposes synthesized Unix mode bits; the image-side mode
        # assertion is also exercised on Linux in CI and the real image.
        if os.name == "nt":
            from unittest.mock import patch
            with patch.object(subject.stat, "S_IMODE", return_value=0o755):
                return subject.build(self.runtime)
        return subject.build(self.runtime)

    def test_copied_sources_match_independently_with_expected_line_normalization(self):
        source = subject.build(self.source, checkout=True)
        self.assertEqual(self.runtime_build(), source)
        (self.runtime / "cuaderno/module.py").write_bytes(b"wrong image bytes\n")
        self.assertNotEqual(self.runtime_build(), source)

    def test_generated_files_are_separately_bound_but_unexpected_application_files_are_detected(self):
        original = self.runtime_build()
        for relative in ("cookbook/static/vue3/generated.js", "cookbook/version_info.py"):
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("generated", encoding="utf-8")
        self.assertEqual(self.runtime_build(), original)
        (self.runtime / "recipes/extra.py").write_text("unexpected", encoding="utf-8")
        self.assertNotEqual(self.runtime_build(), original)

    def test_image_side_rejects_tests_bytecode_and_prebuilt_nginx_configuration(self):
        for relative in ("cookbook/tests/test_demo.py", "cuaderno/__pycache__/compiled.pyc", "http.d/Recipes.conf"):
            with self.subTest(relative=relative):
                path = self.runtime / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("forbidden", encoding="utf-8")
                try:
                    with self.assertRaises(ValueError):
                        self.runtime_build()
                finally:
                    path.unlink()
                    path.parent.rmdir() if path.parent.name in {"tests", "__pycache__"} else None

    def test_missing_runtime_input_fails_closed(self):
        (self.runtime / "boot.sh").unlink()
        with self.assertRaisesRegex(ValueError, "boot.sh"):
            subject.build(self.runtime)
