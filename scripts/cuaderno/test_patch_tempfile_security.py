"""Pinned pair validation and ordinary cleanup; no attack or race reproduction."""
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from . import patch_tempfile_security as subject
except ImportError:
    import patch_tempfile_security as subject

ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = ROOT / "tooling/cuaderno/fixtures/cpython-3.13.16"


def load_pair(directory):
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    patched_shutil = load("cuaderno_fixture_shutil", directory / "shutil.py")
    with patch.dict(sys.modules, {"shutil": patched_shutil}):
        patched_tempfile = load("cuaderno_fixture_tempfile", directory / "tempfile.py")
    return patched_tempfile, patched_shutil


class TempfileSecurityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cuaderno-tempfile-pair-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stdlib = self.root / "stdlib"
        self.stdlib.mkdir()
        self.vendor = self.root / "vendor"
        shutil.copytree(subject.SOURCE_DIRECTORY, self.vendor)
        for name in subject.ORIGINAL_SHA256:
            shutil.copy2(ORIGINALS / name, self.stdlib / name)
        (self.stdlib / "tempfile.py").chmod(0o640)
        (self.stdlib / "shutil.py").chmod(0o644)

    def apply(self, **kwargs):
        return subject.patch_stdlib_pair(self.stdlib, source_directory=self.vendor,
                                        python_version=(3, 13, 16), python_implementation="CPython", **kwargs)

    def snapshot(self):
        return {name: ((self.stdlib / name).read_bytes(), stat.S_IMODE((self.stdlib / name).stat().st_mode))
                for name in subject.ORIGINAL_SHA256}

    def assert_no_staging(self):
        self.assertEqual(list(self.stdlib.glob(".cuaderno-tempfile-security-*")), [])

    def test_frozen_official_inputs_and_original_fixtures_match_every_pin(self):
        for name in subject.ORIGINAL_SHA256:
            self.assertEqual(hashlib.sha256((ORIGINALS / name).read_bytes()).hexdigest(), subject.ORIGINAL_SHA256[name])
            self.assertEqual(hashlib.sha256((subject.SOURCE_DIRECTORY / name).read_bytes()).hexdigest(), subject.PATCHED_SHA256[name])
        self.assertEqual(json.loads((subject.SOURCE_DIRECTORY / "provenance.json").read_text()), subject.provenance())
        self.assertEqual(hashlib.sha256((subject.SOURCE_DIRECTORY / "LICENSE").read_bytes()).hexdigest(), subject.LICENSE_SHA256)
        self.assertEqual(subject.provenance()["upstream_status"], "open-unmerged-backport")

    def test_validated_pair_is_patched_and_permissions_preserved(self):
        before = self.snapshot()
        result = self.apply()
        self.assertEqual(result["status"], "patched")
        self.assertEqual(result["files"], subject.provenance()["files"])
        for name, (_, mode) in before.items():
            self.assertEqual(hashlib.sha256((self.stdlib / name).read_bytes()).hexdigest(), subject.PATCHED_SHA256[name])
            self.assertEqual(stat.S_IMODE((self.stdlib / name).stat().st_mode), mode)
        self.assert_no_staging()

    def test_both_patched_is_idempotent_even_after_build_input_is_removed(self):
        self.apply()
        before = self.snapshot()
        inodes = {name: (self.stdlib / name).stat().st_ino for name in before}
        shutil.rmtree(self.vendor)
        with patch.object(subject.os, "replace") as replace:
            self.assertEqual(self.apply()["status"], "already-patched")
        replace.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({name: (self.stdlib / name).stat().st_ino for name in before}, inodes)

    def test_wrong_runtime_is_rejected_before_changes(self):
        before = self.snapshot()
        for version, implementation in [((3, 13, 15), "CPython"), ((3, 13, 17), "CPython"), ((3, 13, 16), "PyPy")]:
            with self.subTest(version=version, implementation=implementation), self.assertRaises(subject.PatchFailure):
                subject.patch_stdlib_pair(self.stdlib, source_directory=self.vendor,
                                          python_version=version, python_implementation=implementation)
            self.assertEqual(self.snapshot(), before)
        self.assert_no_staging()

    def test_mixed_and_tampered_pairs_refuse_before_any_staging_write(self):
        original = self.snapshot()
        for name in subject.ORIGINAL_SHA256:
            for data in ((self.vendor / name).read_bytes(), original[name][0] + b"\n# changed\n"):
                with self.subTest(name=name, patched=data == (self.vendor / name).read_bytes()):
                    (self.stdlib / name).write_bytes(data)
                    before = self.snapshot()
                    with patch.object(subject.os, "open", wraps=os.open) as opened, self.assertRaises(subject.PatchFailure):
                        self.apply()
                    self.assertFalse(any(call.args[1] & os.O_CREAT for call in opened.call_args_list))
                    self.assertEqual(self.snapshot(), before)
                    (self.stdlib / name).write_bytes(original[name][0])
        self.assert_no_staging()

    def test_vendor_pair_license_and_provenance_cannot_be_overridden(self):
        original = self.snapshot()
        for name in ("tempfile.py", "shutil.py", "LICENSE", "provenance.json"):
            with self.subTest(name=name):
                target = self.vendor / name
                before = target.read_bytes()
                target.write_bytes(before + b"tampered")
                with self.assertRaises(subject.PatchFailure):
                    self.apply()
                self.assertEqual(self.snapshot(), original)
                self.assert_no_staging()
                target.write_bytes(before)

    def test_duplicate_or_extra_provenance_fields_are_rejected(self):
        for raw in (b'{"schema_version":1,' + (self.vendor / "provenance.json").read_bytes()[1:],
                    json.dumps({**subject.provenance(), "extra": True}).encode(),
                    json.dumps({**subject.provenance(), "schema_version": True}).encode()):
            with self.subTest(raw_size=len(raw)), self.assertRaises(subject.PatchFailure):
                (self.vendor / "provenance.json").write_bytes(raw)
                self.apply()
        self.assert_no_staging()

    def test_destination_and_vendor_symlinks_cannot_modify_owned_external_files(self):
        external = self.root / "external.py"
        external.write_bytes(b"owned external content")
        external.chmod(0o640)
        for directory in (self.stdlib, self.vendor):
            for name in subject.ORIGINAL_SHA256:
                with self.subTest(directory=directory.name, name=name):
                    target = directory / name
                    before = target.read_bytes()
                    target.unlink()
                    target.symlink_to(external)
                    with self.assertRaises(subject.PatchFailure):
                        self.apply()
                    self.assertEqual(external.read_bytes(), b"owned external content")
                    self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o640)
                    target.unlink()
                    target.write_bytes(before)
        self.assert_no_staging()

    def test_symlink_ancestors_and_traversal_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        for destination in (alias / "stdlib", self.root / "stdlib/../stdlib", Path("stdlib")):
            with self.subTest(destination=str(destination)), self.assertRaises(subject.PatchFailure):
                subject.patch_stdlib_pair(destination, source_directory=self.vendor,
                                          python_version=(3, 13, 16), python_implementation="CPython")
        self.assert_no_staging()

    def test_hardlinked_destination_is_rejected_without_changes(self):
        linked = self.root / "second-link.py"
        os.link(self.stdlib / "shutil.py", linked)
        before = linked.read_bytes()
        with self.assertRaises(subject.PatchFailure):
            self.apply()
        self.assertEqual(linked.read_bytes(), before)
        self.assert_no_staging()

    def test_existing_staging_collision_never_cleans_an_uncreated_directory(self):
        directory = self.stdlib / ".cuaderno-tempfile-security-collision"
        directory.mkdir(mode=0o700)
        occupant = directory / "tempfile.py"
        occupant.write_bytes(b"owned preexisting staging content")
        with patch.object(subject.secrets, "token_hex", return_value="collision"), self.assertRaises(subject.PatchFailure):
            self.apply()
        self.assertTrue(occupant.exists())
        self.assertEqual(occupant.read_bytes(), b"owned preexisting staging content")

    def test_replacement_failure_restores_both_originals_and_cleans_private_staging(self):
        before = self.snapshot()
        replace = os.replace
        failed = False
        def fail_second(source, destination):
            nonlocal failed
            self.assertEqual(stat.S_IMODE(Path(source).parent.stat().st_mode), 0o700)
            if Path(destination).name == "shutil.py" and not failed:
                failed = True
                raise OSError("synthetic replacement failure")
            return replace(source, destination)
        with patch.object(subject.os, "replace", side_effect=fail_second), self.assertRaises(subject.PatchFailure):
            self.apply()
        self.assertEqual(self.snapshot(), before)
        self.assert_no_staging()

    def test_patched_pair_exposes_matching_cleanup_capability(self):
        self.apply()
        patched_tempfile, patched_shutil = load_pair(self.stdlib)
        self.assertIn("_onexc_kwargs", inspect.signature(patched_shutil.rmtree).parameters)
        self.assertIn("dir_fd", inspect.signature(patched_tempfile.TemporaryDirectory._rmtree).parameters)

    def test_normal_directory_cleanup_preserves_owned_outside_symlink_target(self):
        self.apply()
        patched_tempfile, _ = load_pair(self.stdlib)
        outside = self.root / "owned-outside"
        outside.mkdir()
        marker = outside / "marker.txt"
        marker.write_text("preserve", encoding="utf-8")
        marker.chmod(0o640)
        with patched_tempfile.TemporaryDirectory(dir=self.root) as name:
            directory = Path(name)
            (directory / "nested").mkdir()
            (directory / "nested/normal.txt").write_text("normal", encoding="utf-8")
            (directory / "outside-link").symlink_to(outside, target_is_directory=True)
        self.assertFalse(directory.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o640)

    def test_normal_files_close_and_nonexistent_cleanup_remains_supported(self):
        self.apply()
        patched_tempfile, patched_shutil = load_pair(self.stdlib)
        with patched_tempfile.NamedTemporaryFile(dir=self.root) as stream:
            descriptor = stream.fileno()
            name = stream.name
            stream.write(b"ordinary temporary file")
        self.assertFalse(Path(name).exists())
        with self.assertRaises(OSError):
            os.fstat(descriptor)
        missing = self.root / "nonexistent-owned-directory"
        patched_tempfile.TemporaryDirectory._rmtree(missing)
        errors = []
        patched_shutil.rmtree(missing, onexc=lambda *args: errors.append(args))
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(errors[0]), 3)  # Public callers retain the original callback contract.
        self.assertIsInstance(errors[0][2], FileNotFoundError)

    def test_ordinary_nested_cleanup_closes_native_directory_descriptors(self):
        self.apply()
        patched_tempfile, _ = load_pair(self.stdlib)
        opened, closed = [], []
        real_open, real_close = os.open, os.close
        def tracked_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def tracked_close(descriptor):
            real_close(descriptor)
            closed.append(descriptor)
        with patch.object(os, "open", side_effect=tracked_open), patch.object(os, "close", side_effect=tracked_close):
            with patched_tempfile.TemporaryDirectory(dir=self.root) as name:
                (Path(name) / "nested").mkdir()
                (Path(name) / "nested/file.txt").write_text("ordinary", encoding="utf-8")
        self.assertCountEqual(opened, closed)
        self.assertFalse(Path(name).exists())


if __name__ == "__main__":
    unittest.main()
