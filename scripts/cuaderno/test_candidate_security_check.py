"""Tests for the one-candidate security scan/proof/assessment orchestration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import candidate_security_check as subject
    from .test_image_security_assessment import FRESH_EXPECTED_MATCHES, alpine_metadata, scope_sources
else:
    import candidate_security_check as subject
    from test_image_security_assessment import FRESH_EXPECTED_MATCHES, alpine_metadata, scope_sources


IMAGE = "sha256:" + "c" * 64
SOURCE = "a" * 40 + "+worktree." + "b" * 64
BINDING = {"format": "oci", "config_digest": IMAGE,
           "manifest_digest": "sha256:" + "d" * 64,
           "chain": ["sha256:" + "d" * 64, IMAGE]}


class Fixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name).resolve()
        scope_sources(self.root)
        self.evidence = self.root / ".cuaderno-runs"; self.evidence.mkdir()
        source_inputs = self.root / "docker/runtime-security/source-inputs.json"
        source_inputs.parent.mkdir(parents=True); source_inputs.write_text('{"fixture":1}\n')
        self.alpine = alpine_metadata(hashlib.sha256(source_inputs.read_bytes()).hexdigest())
        self.context = {"schema_version": 1, "candidate_id": "7f90be2e-c663-43e7-914a-6efac5524841",
                        "git_commit": "a" * 40, "source_sha256": "b" * 64,
                        "source_identity": SOURCE, "image_id": IMAGE,
                        "environment_fingerprint": "e" * 64, "commands_registry_sha256": "f" * 64,
                        "environment": {"image": {"artifacts": {}}}}
        self.context_path = self.evidence / "candidate.json"
        self.context_path.write_text(json.dumps(self.context))
        self.scan_dir = self.root / "data/cuaderno/scans/candidate-fixture"
        (self.scan_dir / "linux-scanner").mkdir(parents=True)
        self.archive = self.scan_dir / "image.tar"; self.archive.write_bytes(b"archive")
        self.report = self.scan_dir / "linux-scanner/grype-linux.json"
        self.report.write_text(json.dumps({
            "source": {"target": {"userInput": subject.image_archive_audit.CONTAINER_ARCHIVE_INPUT}},
            "matches": FRESH_EXPECTED_MATCHES, "ignoredMatches": [],
        }))
        self.summary = self.scan_dir / "linux-scanner/summary-linux.json"; self.summary.write_text("{}")
        self.scan = {
            "status": "findings", "scanner_exit": 2, "archive_binding": BINDING,
            "paths": {"archive": self.archive.relative_to(self.root).as_posix(),
                      "report": self.report.relative_to(self.root).as_posix(),
                      "summary": self.summary.relative_to(self.root).as_posix()},
        }
        self.runtime = {"alpine_provenance": {
            "schema_version": 1, **{k: v for k, v in self.alpine.items() if k != "license_urls"},
            "verified": True,
        }}
        self.scan_calls = 0; self.runtime_calls = 0

    def close(self): self.temporary.cleanup()

    def scanner(self, *_args, **_kwargs):
        self.scan_calls += 1
        return 2, {"schema_version": 1, "candidate_id": self.context["candidate_id"],
                   "image_id": IMAGE, "source_identity": SOURCE,
                   "archive": self.archive.relative_to(self.root).as_posix(),
                   "archive_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                   "scan": self.scan}

    def assessor(self, **kwargs):
        proofs = [json.loads(path.read_text()) for path in kwargs["proof_paths"]]
        self.proofs = proofs
        self.asserted_runtime = kwargs["runtime_probe"](self.context, root=self.root)
        result = {"status": subject.security.ASSESSMENT_POLICY, "raw_scanner_exit": 2}
        kwargs["output_path"].write_text(json.dumps(result) + "\n")
        return result

    def run(self, **kwargs):
        with patch.object(subject.image_archive_audit, "_validate_archive_report",
                          return_value=(FRESH_EXPECTED_MATCHES, [], {"High": 11})):
            return subject.run(
                self.context_path, root=self.root, context_validator=kwargs.get("validator", lambda *_: None),
                scanner=kwargs.get("scanner", self.scanner),
                runtime_probe=kwargs.get("runtime_probe", self.probe),
                assessor=kwargs.get("assessor", self.assessor),
            )

    def probe(self, *_args, **_kwargs):
        self.runtime_calls += 1
        return self.runtime


class CandidateSecurityCheckTests(unittest.TestCase):
    def fixture(self):
        fixture = Fixture(); self.addCleanup(fixture.close); return fixture

    def test_findings_generate_exact_three_proofs_then_assess_same_candidate(self):
        fixture = self.fixture(); result = fixture.run()
        self.assertEqual(result["status"], "reviewed-no-unresolved")
        self.assertEqual(result["raw_scanner_exit"], 2)
        self.assertEqual({row["kind"]: len(row["fingerprints"]) for row in fixture.proofs},
                         subject.EXPECTED_COUNTS)
        self.assertEqual(len(result["proofs"]), 5)
        self.assertTrue((fixture.root / result["assessment"]).is_file())
        self.assertEqual((fixture.scan_calls, fixture.runtime_calls), (1, 1))
        self.assertIs(fixture.asserted_runtime, fixture.runtime)

    def test_real_grype_unprefixed_archive_input_retains_the_same_proofs(self):
        fixture = self.fixture()
        report = json.loads(fixture.report.read_text())
        report['source']['target']['userInput'] = '/scan-input/image.tar'
        fixture.report.write_text(json.dumps(report))
        result = fixture.run()
        self.assertEqual(result['status'], 'reviewed-no-unresolved')
        self.assertEqual(result['raw_scanner_exit'], 2)
        self.assertEqual(len(result['proofs']), 5)

    def test_clean_wrong_exit_or_missing_finding_is_never_accepted(self):
        fixture = self.fixture()
        def clean(*_args, **_kwargs):
            record = fixture.scanner()[1]; record["scan"] = {**record["scan"], "status": "clean", "scanner_exit": 0}
            return 0, record
        with self.assertRaisesRegex(subject.CandidateSecurityFailure, "exit 2"):
            fixture.run(scanner=clean)
        fixture = self.fixture()
        with patch.object(subject.image_archive_audit, "_validate_archive_report",
                          return_value=(FRESH_EXPECTED_MATCHES[:-1], [], {"High": 10})):
            with self.assertRaisesRegex(subject.CandidateSecurityFailure, "8 hallazgos"):
                subject.run(fixture.context_path, root=fixture.root,
                            context_validator=lambda *_: None, scanner=fixture.scanner,
                            runtime_probe=lambda *_args, **_kwargs: fixture.runtime,
                            assessor=fixture.assessor)

    def test_context_drift_stops_before_scan_and_after_partial_proofs(self):
        fixture = self.fixture()
        with self.assertRaisesRegex(ValueError, "drift"):
            fixture.run(validator=lambda *_: (_ for _ in ()).throw(ValueError("drift")),
                        scanner=lambda *_args, **_kwargs: self.fail("must not scan"))
        fixture = self.fixture(); calls = [0]
        def validator(*_args):
            calls[0] += 1
            if calls[0] >= 3: raise ValueError("drift after scan")
        with self.assertRaisesRegex(ValueError, "drift after scan"):
            fixture.run(validator=validator)

    def test_bad_runtime_provenance_and_duplicate_report_fail_closed(self):
        fixture = self.fixture()
        with self.assertRaisesRegex(subject.CandidateSecurityFailure, "Alpine"):
            fixture.run(runtime_probe=lambda *_args, **_kwargs: {"alpine_provenance": {"verified": True}})
        fixture = self.fixture()
        duplicate = [*FRESH_EXPECTED_MATCHES[:-1], FRESH_EXPECTED_MATCHES[0]]
        with patch.object(subject.image_archive_audit, "_validate_archive_report",
                          return_value=(duplicate, [], {"High": 11})):
            with self.assertRaises(subject.CandidateSecurityFailure):
                subject.run(fixture.context_path, root=fixture.root,
                            context_validator=lambda *_: None, scanner=fixture.scanner,
                            runtime_probe=lambda *_args, **_kwargs: fixture.runtime,
                            assessor=fixture.assessor)


if __name__ == "__main__":
    unittest.main()
