import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import candidate_image_archive_check as subject
else:
    import candidate_image_archive_check as subject


IMAGE = "sha256:" + "c" * 64
SOURCE = "a" * 40 + "+worktree." + "b" * 64


class CandidateImageArchiveCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / ".cuaderno-runs").mkdir()
        (self.root / "data/cuaderno/scans").mkdir(parents=True)
        self.context = {"candidate_id": "7f90be2e-c663-43e7-914a-6efac5524841",
                        "image_id": IMAGE, "source_identity": SOURCE}
        self.context_path = self.root / ".cuaderno-runs/candidate.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    def test_exports_exact_image_once_and_audits_retained_hash(self):
        validations, exports, audits = [], [], []
        def validate(context, root):
            validations.append((context, root))
        def export(image, destination, *, root):
            exports.append((image, destination, root))
            destination.write_bytes(b"immutable-image-archive")
        def audit(**kwargs):
            audits.append(kwargs)
            self.assertEqual(subject.sha256(kwargs["archive"]), kwargs["expected_archive_sha256"])
            return 0, {"status": "clean", "image_id": kwargs["image_id"]}
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False):
            status, report = subject.run(self.context_path, root=self.root,
                                         context_validator=validate, exporter=export, auditor=audit)
        self.assertEqual(status, 0)
        self.assertEqual([row[0] for row in exports], [IMAGE])
        self.assertEqual(len(validations), 3)
        self.assertEqual(audits[0]["image_id"], IMAGE)
        self.assertEqual(audits[0]["source_ref"], SOURCE)
        archive = self.root / report["archive"]
        self.assertTrue(archive.is_file())
        metadata = json.loads((archive.parent / "candidate-archive.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["archive_sha256"], report["archive_sha256"])

    def test_findings_status_is_not_converted_to_pass(self):
        def export(_image, destination, *, root):
            destination.write_bytes(b"archive")
        with patch.dict(os.environ, {"CUADERNO_ENV": "local"}, clear=False):
            status, report = subject.run(
                self.context_path, root=self.root, context_validator=lambda *_: None,
                exporter=export, auditor=lambda **_kwargs: (2, {"status": "findings"}),
            )
        self.assertEqual(status, 2)
        self.assertEqual(report["scan"]["status"], "findings")

    def test_context_drift_prevents_export_and_post_export_drift_preserves_archive(self):
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False):
            with self.assertRaisesRegex(Exception, "drift"):
                subject.run(
                    self.context_path, root=self.root,
                    context_validator=lambda *_: (_ for _ in ()).throw(ValueError("drift")),
                    exporter=lambda *_args, **_kwargs: self.fail("must not export"),
                )

            calls = 0
            def drift_after_export(*_args):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ValueError("drift after export")
            def export(_image, destination, *, root):
                destination.write_bytes(b"retained")
            with self.assertRaisesRegex(ValueError, "drift after export"):
                subject.run(self.context_path, root=self.root, context_validator=drift_after_export,
                            exporter=export, auditor=lambda **_: self.fail("must not scan"))
        archives = list((self.root / "data/cuaderno/scans").glob("candidate-*/image.tar"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), b"retained")


if __name__ == "__main__":
    unittest.main()
