import hashlib
import json
from pathlib import Path
import tempfile
import unittest

if __package__:
    from . import release_manifest as subject
else:
    import release_manifest as subject


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for name, relative in subject.ARTIFACTS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        self.source = "a" * 40 + "+worktree." + "b" * 64

    def test_writes_exact_hashes_without_overwrite(self):
        document = subject.build(self.root, self.source, Path("RELEASE-MANIFEST.json"))
        expected = {name: hashlib.sha256(name.encode()).hexdigest() for name in subject.ARTIFACTS}
        self.assertEqual(document, {"schema_version": 1, "source_identity": self.source,
                                    "artifacts": expected})
        stored = json.loads((self.root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, document)
        with self.assertRaisesRegex(ValueError, "nuevo"):
            subject.build(self.root, self.source, Path("RELEASE-MANIFEST.json"))

    def test_rejects_invalid_source_and_linked_artifact(self):
        with self.assertRaisesRegex(ValueError, "identidad"):
            subject.build(self.root, "main", Path("RELEASE-MANIFEST.json"))
        target = self.root / "real"
        target.write_text("data", encoding="utf-8")
        artifact = self.root / subject.ARTIFACTS["version_info"]
        artifact.unlink()
        try:
            artifact.symlink_to(target)
        except OSError:
            self.skipTest("El host no permite symlinks de prueba.")
        with self.assertRaisesRegex(ValueError, "version_info"):
            subject.build(self.root, self.source, Path("RELEASE-MANIFEST.json"))


if __name__ == "__main__":
    unittest.main()
