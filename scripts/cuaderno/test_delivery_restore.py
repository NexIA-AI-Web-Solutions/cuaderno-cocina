"""Unit tests for restore bundle confinement; no Docker boundary is crossed."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

if __package__:
    from . import delivery_restore as subject
else:
    import delivery_restore as subject


class TrustedBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.backups = self.root / "data/cuaderno/backups"
        self.backups.mkdir(parents=True)

    def bundle(self, name="bundle"):
        path = self.backups / name
        path.mkdir()
        (path / "manifest.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        (path / "database.dump").write_bytes(b"dump")
        (path / "media.tar").write_bytes(b"tar")
        return path

    def test_accepts_complete_bundle_inside_workspace_backup_root(self):
        bundle = self.bundle()
        self.assertEqual(subject.trusted_bundle(Path("data/cuaderno/backups/bundle"), root=self.root), bundle)

    def test_rejects_outside_missing_and_incomplete_bundles(self):
        outside = self.root / "outside"
        outside.mkdir()
        for name in ("manifest.json", "database.dump", "media.tar"):
            (outside / name).write_bytes(b"x")
        with self.assertRaises(ValueError):
            subject.trusted_bundle(outside, root=self.root)
        with self.assertRaises(ValueError):
            subject.trusted_bundle(self.backups / "missing", root=self.root)
        incomplete = self.bundle("incomplete")
        (incomplete / "media.tar").unlink()
        with self.assertRaises(ValueError):
            subject.trusted_bundle(incomplete, root=self.root)

    def test_rejects_linked_bundle_or_bundle_member(self):
        real = self.bundle("real")
        link = self.backups / "linked"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("El sistema no permite symlinks en este entorno")
        with self.assertRaises(ValueError):
            subject.trusted_bundle(link, root=self.root)

        member_link = self.bundle("member-link")
        (member_link / "database.dump").unlink()
        (member_link / "database.dump").symlink_to(real / "database.dump")
        with self.assertRaises(ValueError):
            subject.trusted_bundle(member_link, root=self.root)


if __name__ == "__main__":
    unittest.main()
