"""Security regression tests for local backup media validation."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from delivery_backup import media_manifest
import local_up


class MediaValidationTest(unittest.TestCase):
    def archive(self, names, kind=tarfile.REGTYPE):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "media.tar"
        with tarfile.open(path, "w") as archive:
            for name in names:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "outside"
                info.size = 4 if kind == tarfile.REGTYPE else 0
                archive.addfile(info, io.BytesIO(b"demo") if info.size else None)
        return path

    def test_regular_file_content_hash(self):
        self.assertEqual(media_manifest(self.archive(["recipes/demo.txt"])), {
            "recipes/demo.txt": {"bytes": 4, "sha256": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"}})

    def test_traversal_and_windows_paths_rejected(self):
        for name in ("../secret", "/etc/passwd", "C:/private", "folder\\secret"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                media_manifest(self.archive([name]))

    def test_links_and_devices_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                media_manifest(self.archive(["file"], kind))

    def test_duplicate_media_rejected(self):
        with self.assertRaises(ValueError):
            media_manifest(self.archive(["same", "./same"]))


class SourceIdentityTest(unittest.TestCase):
    def test_source_identity_distinguishes_dirty_snapshots_at_the_same_commit(self):
        commit = "a" * 40
        first = local_up.build_identity(commit, "b" * 64)
        second = local_up.build_identity(commit, "c" * 64)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith(commit))
        self.assertIn("worktree", first)

    def test_untrusted_build_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            local_up.build_identity('unsafe";command', "b" * 64)


if __name__ == "__main__":
    unittest.main()
