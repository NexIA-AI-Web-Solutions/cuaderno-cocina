import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import candidate_recovery_check as subject
else:
    import candidate_recovery_check as subject


IMAGE = "sha256:" + "c" * 64
PRIOR_IMAGE = "sha256:" + "d" * 64
SOURCE_SHA = "b" * 64


class CandidateRecoveryCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / ".cuaderno-runs").mkdir()
        self.backups = self.root / "data/cuaderno/backups"
        self.backups.mkdir(parents=True)
        self.context = {"image_id": IMAGE, "source_sha256": SOURCE_SHA}
        self.context_path = self.root / ".cuaderno-runs/candidate.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")

    def bundle(self, name: str, image: str, *, candidate=False) -> Path:
        bundle = self.backups / name
        bundle.mkdir()
        manifest = {"image_id": image}
        if candidate:
            manifest.update({"source_target": "release", "checkout_source": {"sha256": SOURCE_SHA}})
        (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (bundle / "database.dump").write_bytes(b"dump")
        (bundle / "media.tar").write_bytes(b"media")
        return bundle

    def test_candidate_restore_backs_up_exact_preview_and_restores_new_namespace(self):
        bundle = self.bundle("candidate", IMAGE, candidate=True)
        validations = []
        report = {"passed": True, "target_database": "cuaderno_restore_unique",
                  "target_media": "data/cuaderno/restores/unique"}
        with patch.dict(os.environ, {"CUADERNO_ENV": "local"}, clear=False):
            result = subject.run(
                "restore", self.context_path, root=self.root,
                context_validator=lambda context, root: validations.append((context, root)),
                backup_creator=lambda: bundle, restore_runner=lambda received: report if received == bundle else None,
            )
        self.assertEqual(result["mode"], "candidate-round-trip")
        self.assertEqual(result["image_id"], IMAGE)
        self.assertEqual(result["restore"], report)
        self.assertEqual(len(validations), 2)

    def test_candidate_restore_rejects_backup_from_other_image_or_source(self):
        bundle = self.bundle("wrong", PRIOR_IMAGE, candidate=True)
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False):
            with self.assertRaisesRegex(subject.CandidateRecoveryFailure, "no pertenece"):
                subject.run("restore", self.context_path, root=self.root,
                            context_validator=lambda *_: None, backup_creator=lambda: bundle,
                            restore_runner=lambda _: self.fail("must not restore"))

    def test_prior_rollback_requires_distinct_verified_bundle_and_preserves_candidate(self):
        bundle = self.bundle("prior", PRIOR_IMAGE)
        validations = []
        rollback_report = {"passed": True, "image_id": PRIOR_IMAGE,
                           "mode": "isolated-full-restore-not-live-downgrade",
                           "target_database": "cuaderno_restore_rollback_unique"}
        with patch.dict(os.environ, {"CUADERNO_ENV": "development",
                                     "CUADERNO_PRIOR_RELEASE_BUNDLE": str(bundle)}, clear=False):
            result = subject.run(
                "rollback", self.context_path, root=self.root,
                context_validator=lambda context, root: validations.append((context, root)),
                rollback_runner=lambda received: rollback_report if received == bundle else None,
            )
        self.assertEqual(result["mode"], "prior-release-rollback")
        self.assertEqual(result["candidate_image_id"], IMAGE)
        self.assertEqual(result["prior_image_id"], PRIOR_IMAGE)
        self.assertEqual(len(validations), 2)

    def test_rollback_fails_closed_for_missing_outside_or_candidate_bundle(self):
        same = self.bundle("same", IMAGE)
        outside = self.root / "outside"
        outside.mkdir()
        for name in ("manifest.json", "database.dump", "media.tar"):
            (outside / name).write_text("{}", encoding="utf-8")
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=False):
            with self.assertRaisesRegex(subject.CandidateRecoveryFailure, "Define"):
                subject.run("rollback", self.context_path, root=self.root,
                            context_validator=lambda *_: None, prior_bundle_value="")
            with self.assertRaisesRegex(subject.CandidateRecoveryFailure, "dentro"):
                subject.run("rollback", self.context_path, root=self.root,
                            context_validator=lambda *_: None, prior_bundle_value=str(outside))
            with self.assertRaisesRegex(subject.CandidateRecoveryFailure, "distinta"):
                subject.run("rollback", self.context_path, root=self.root,
                            context_validator=lambda *_: None, prior_bundle_value=str(same),
                            rollback_runner=lambda _: self.fail("must not rollback"))


if __name__ == "__main__":
    unittest.main()
