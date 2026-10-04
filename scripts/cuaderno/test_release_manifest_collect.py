"""Tests for fail-closed release manifest assembly."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from . import release_gate
    from . import release_manifest_collect as subject
else:
    import release_gate
    import release_manifest_collect as subject


COMMIT = "a" * 40
SOURCE_SHA = "b" * 64
SOURCE = f"{COMMIT}+worktree.{SOURCE_SHA}"
IMAGE = "sha256:" + "c" * 64
ENVIRONMENT = "d" * 64
REGISTRY = "e" * 64
CANDIDATE = "7f90be2e-c663-43e7-914a-6efac5524841"


class GitRunner:
    def __init__(self, *, tracked=False):
        self.tracked = tracked

    def __call__(self, argv, **_kwargs):
        if argv[1:3] == ["ls-files", "--error-unmatch"]:
            return subprocess.CompletedProcess(argv, 0 if self.tracked else 1, stdout="", stderr="")
        if argv[1:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, stdout=COMMIT + "\n", stderr="")
        if argv[1:] == ["status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(argv)


class Fixture:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.evidence = self.root / ".cuaderno-runs"
        self.evidence.mkdir()
        self.context = {
            "schema_version": 1, "candidate_id": CANDIDATE, "git_commit": COMMIT,
            "source_sha256": SOURCE_SHA, "source_identity": SOURCE, "image_id": IMAGE,
            "environment_fingerprint": ENVIRONMENT, "commands_registry_sha256": REGISTRY,
            "environment": {},
        }
        self.context_path = self.evidence / "candidate-context.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")
        self.records = []
        for name in sorted(release_gate.REQUIRED_CHECKS):
            log = self.evidence / f"{name}.log"
            log_raw = f"PASS {name}\n".encode()
            log.write_bytes(log_raw)
            record = {
                "schema_version": 1, "command": name, "passed": True, "exit_code": 0,
                "git_commit": COMMIT, "source_sha256": SOURCE_SHA, "source_identity": SOURCE,
                "image_id": IMAGE, "environment_fingerprint": ENVIRONMENT,
                "candidate_id": CANDIDATE, "commands_registry_sha256": REGISTRY,
                "log": log.name, "log_bytes": len(log_raw),
                "log_sha256": hashlib.sha256(log_raw).hexdigest(),
            }
            path = self.evidence / f"{name}.json"
            path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
            self.records.append(path)
        self.output = self.evidence / "manifest.json"

    def collect(self, **kwargs):
        return subject.collect(
            self.context_path, self.records, output_path=self.output, root=self.root,
            runner=kwargs.pop("runner", GitRunner()), context_validator=lambda *_: None,
            **kwargs,
        )

    def rewrite(self, index: int, **changes):
        path = self.records[index]
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(changes)
        path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")


class ManifestCollectTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Fixture(Path(temporary.name))

    def test_creates_exact_manifest_only_after_the_real_gate_accepts_it(self):
        fixture = self.fixture()
        output, summary = fixture.collect()
        document = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(summary["passed"])
        self.assertEqual(set(document), release_gate.MANIFEST_KEYS)
        self.assertEqual({key: document[key] for key in subject.CONTEXT_KEYS}, fixture.context)
        self.assertEqual(set(document["checks"]), release_gate.REQUIRED_CHECKS)
        for name, reference in document["checks"].items():
            record = fixture.evidence / reference["path"]
            self.assertEqual(reference["sha256"], hashlib.sha256(record.read_bytes()).hexdigest(), name)
        self.assertEqual(list(fixture.evidence.glob(".manifest.json.*.tmp")), [])

    def test_missing_duplicate_path_and_duplicate_command_are_rejected(self):
        fixture = self.fixture()
        fixture.records.pop()
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "Faltan evidencias"):
            fixture.collect()

        fixture = self.fixture()
        fixture.records[-1] = fixture.records[0]
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "más de una vez"):
            fixture.collect()

        fixture = self.fixture()
        first = json.loads(fixture.records[0].read_text(encoding="utf-8"))["command"]
        fixture.rewrite(1, command=first)
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "duplicadas"):
            fixture.collect()

    def test_failed_or_different_candidate_records_never_publish_output(self):
        for changes in (
            {"passed": False, "exit_code": 1},
            {"candidate_id": "4b8f0290-d761-446c-b853-33bba40ba84e"},
        ):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                fixture.rewrite(0, **changes)
                with self.assertRaisesRegex(subject.ManifestCollectFailure, "release gate"):
                    fixture.collect()
                self.assertFalse(fixture.output.exists())

    def test_tampered_log_source_registry_and_environment_are_rejected(self):
        mutations = (
            "log", "source_sha256", "source_identity", "commands_registry_sha256", "environment_fingerprint",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                if mutation == "log":
                    record = json.loads(fixture.records[0].read_text(encoding="utf-8"))
                    (fixture.evidence / record["log"]).write_text("TAMPERED\n", encoding="utf-8")
                else:
                    fixture.rewrite(0, **{mutation: "f" * 64})
                with self.assertRaisesRegex(subject.ManifestCollectFailure, "release gate"):
                    fixture.collect()
                self.assertFalse(fixture.output.exists())

    def test_path_escape_symlink_tracked_output_and_overwrite_fail_closed(self):
        fixture = self.fixture()
        outside = fixture.root / "outside.json"
        outside.write_text(fixture.records[0].read_text(encoding="utf-8"), encoding="utf-8")
        fixture.records[0] = outside
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "sale del directorio"):
            fixture.collect()

        fixture = self.fixture()
        link = fixture.evidence / "linked.json"
        try:
            link.symlink_to(fixture.records[0])
        except OSError:
            pass
        else:
            fixture.records[0] = link
            with self.assertRaisesRegex(subject.ManifestCollectFailure, "enlace"):
                fixture.collect()

        fixture = self.fixture()
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "versionada"):
            fixture.collect(runner=GitRunner(tracked=True))

        fixture = self.fixture()
        fixture.output.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "no se sobrescribe"):
            fixture.collect()
        self.assertEqual(fixture.output.read_text(encoding="utf-8"), "keep")

    def test_gate_failure_removes_temporary_file_and_does_not_publish(self):
        fixture = self.fixture()
        def reject(*_args, **_kwargs):
            raise release_gate.ReleaseGateFailure("forced rejection")
        with self.assertRaisesRegex(subject.ManifestCollectFailure, "forced rejection"):
            fixture.collect(gate=reject)
        self.assertFalse(fixture.output.exists())
        self.assertEqual(list(fixture.evidence.glob(".manifest.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
