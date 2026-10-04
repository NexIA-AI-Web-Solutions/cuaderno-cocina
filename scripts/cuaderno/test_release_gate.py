"""Tests for same-candidate release evidence aggregation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from . import release_gate as subject
else:
    import release_gate as subject


COMMIT = "a" * 40
SOURCE_SHA = "b" * 64
IMAGE_ID = "sha256:" + "c" * 64
ENVIRONMENT = "d" * 64
CANDIDATE = "7f90be2e-c663-43e7-914a-6efac5524841"
REGISTRY = "e" * 64


class GitRunner:
    def __init__(self, *, dirty=False, head=COMMIT):
        self.dirty = dirty
        self.head = head

    def __call__(self, argv, **_kwargs):
        if argv[1:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, stdout=self.head + "\n", stderr="")
        if argv[1:] == ["status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(argv, 0, stdout=" M dirty\n" if self.dirty else "", stderr="")
        raise AssertionError(argv)


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.evidence = self.root / ".cuaderno-runs"
        self.evidence.mkdir()
        checks = {}
        identity = f"{COMMIT}+worktree.{SOURCE_SHA}"
        for name in subject.REQUIRED_CHECKS:
            log_raw = f"PASS {name}\n".encode()
            log_path = self.evidence / f"{name}.log"
            log_path.write_bytes(log_raw)
            record = {
                "command": name, "passed": True, "exit_code": 0, "git_commit": COMMIT,
                "source_sha256": SOURCE_SHA,
                "source_identity": identity, "image_id": IMAGE_ID,
                "environment_fingerprint": ENVIRONMENT, "candidate_id": CANDIDATE,
                "commands_registry_sha256": REGISTRY,
                "log": log_path.name, "log_bytes": len(log_raw),
                "log_sha256": hashlib.sha256(log_raw).hexdigest(),
            }
            raw = (json.dumps(record, sort_keys=True) + "\n").encode()
            path = self.evidence / f"{name}.json"
            path.write_bytes(raw)
            checks[name] = {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
        self.manifest = self.evidence / "candidate.json"
        self.document = {
            "schema_version": 1, "git_commit": COMMIT, "source_sha256": SOURCE_SHA,
            "source_identity": identity, "candidate_id": CANDIDATE,
            "image_id": IMAGE_ID, "environment_fingerprint": ENVIRONMENT,
            "commands_registry_sha256": REGISTRY, "environment": {}, "checks": checks,
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.document), encoding="utf-8")

    def test_accepts_complete_clean_single_candidate(self):
        summary = subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                                    context_validator=lambda context, root: None)
        self.assertTrue(summary["passed"])
        self.assertEqual(len(summary["checks"]), len(subject.REQUIRED_CHECKS))
        self.assertEqual(summary["source_identity"], f"{COMMIT}+worktree.{SOURCE_SHA}")
        self.assertEqual(len(subject.REQUIRED_CHECKS), 17)
        self.assertIn("schema-final", subject.REQUIRED_CHECKS)

    def test_missing_failed_or_cross_candidate_evidence_fails_closed(self):
        missing = next(iter(subject.REQUIRED_CHECKS))
        del self.document["checks"][missing]
        self.write_manifest()
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda context, root: None)

        self.setUp()
        changed = next(iter(subject.REQUIRED_CHECKS))
        reference = self.document["checks"][changed]
        path = self.evidence / reference["path"]
        record = json.loads(path.read_text())
        record["image_id"] = "sha256:" + "e" * 64
        raw = (json.dumps(record, sort_keys=True) + "\n").encode()
        path.write_bytes(raw)
        reference["sha256"] = hashlib.sha256(raw).hexdigest()
        self.write_manifest()
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda context, root: None)

    def test_dirty_checkout_hash_tamper_and_outside_path_fail(self):
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(dirty=True),
                              context_validator=lambda context, root: None)

        name = next(iter(subject.REQUIRED_CHECKS))
        self.document["checks"][name]["sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda context, root: None)

        self.document["checks"][name] = {"path": "../outside.json", "sha256": "0" * 64}
        self.write_manifest()
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda context, root: None)

    def test_current_candidate_context_drift_fails_before_acceptance(self):
        def drift(_context, _root):
            raise subject.candidate_context.CandidateFailure("image drift")
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "image drift"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(), context_validator=drift)

    def test_manifest_contract_check_set_and_source_identity_are_exact(self):
        self.document["unexpected"] = True
        self.write_manifest()
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "contrato exacto"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)

        del self.document["unexpected"]
        self.document["source_identity"] = "wrong"
        self.write_manifest()
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "source_identity"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)

        self.document["source_identity"] = f"{COMMIT}+worktree.{SOURCE_SHA}"
        self.document["checks"]["not-a-release-check"] = dict(next(iter(self.document["checks"].values())))
        self.write_manifest()
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "no exacta"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)

    def test_missing_or_modified_referenced_log_fails_closed(self):
        name = next(iter(subject.REQUIRED_CHECKS))
        reference = self.document["checks"][name]
        record_path = self.evidence / reference["path"]
        record = json.loads(record_path.read_text(encoding="utf-8"))
        log_path = self.evidence / record["log"]
        log_path.unlink()
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "log"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)

        log_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(subject.ReleaseGateFailure, "Bytes/hash"):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)

    def test_record_source_hash_tampering_is_rejected(self):
        name = next(iter(subject.REQUIRED_CHECKS))
        path = self.evidence / self.document["checks"][name]["path"]
        record = json.loads(path.read_text())
        record["source_sha256"] = "f" * 64
        raw = json.dumps(record, sort_keys=True).encode()
        path.write_bytes(raw)
        self.document["checks"][name]["sha256"] = hashlib.sha256(raw).hexdigest()
        self.write_manifest()
        with self.assertRaises(subject.ReleaseGateFailure):
            subject.aggregate(self.manifest, root=self.root, runner=GitRunner(),
                              context_validator=lambda *_: None)



if __name__ == "__main__":
    unittest.main()
