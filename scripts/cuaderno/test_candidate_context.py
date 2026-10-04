import json
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from . import candidate_context as subject
else:
    import candidate_context as subject


IMAGE = "sha256:" + "c" * 64


class CandidateContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for relative in (*subject.INPUTS, "tooling/cuaderno/commands.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        for directory in subject.runtime_application.DIRECTORIES:
            path = self.root / directory / "fixture.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(directory, encoding="utf-8")
        for relative in subject.runtime_application.COPY_FILES.values():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "e2e@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "E2E"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=self.root, check=True)
        self.variant = 0

    def probe(self, _root, image_ref, _runner):
        source = subject.source_identity(self.root)
        artifacts = {"sbom_python": "a" * 64, "sbom_frontend": "b" * 64,
                     "frontend_provenance": "d" * 64, "version_info": "e" * 64, "runtime_application": "f" * 64}
        return {"image_id": image_ref, "os": "linux", "architecture": "amd64", "layers": [f"layer-{self.variant}"],
                "labels": {"io.cuaderno.source-identity": source["source_identity"]},
                "artifacts": artifacts,
                "runtime_application": subject.runtime_application.build(self.root, checkout=True),
                "release_manifest": {"schema_version": 1, "source_identity": source["source_identity"],
                                     "artifacts": artifacts}}

    def test_capture_and_revalidate_exact_candidate(self):
        context = subject.capture(self.root, IMAGE, image_probe=self.probe)
        self.assertEqual(context["source_identity"],
                         f"{context['git_commit']}+worktree.{context['source_sha256']}")
        self.assertEqual(subject.same_candidate(context, self.root, image_probe=self.probe), context)

    def test_source_image_environment_and_registry_drift_fail(self):
        context = subject.capture(self.root, IMAGE, image_probe=self.probe)
        (self.root / "vue3/yarn.lock").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(subject.CandidateFailure, "limpio"):
            subject.same_candidate(context, self.root, image_probe=self.probe)
        subprocess.run(["git", "checkout", "--", "vue3/yarn.lock"], cwd=self.root, check=True)
        self.variant = 1
        with self.assertRaisesRegex(subject.CandidateFailure, "derivado"):
            subject.same_candidate(context, self.root, image_probe=self.probe)

        self.variant = 0
        registry = self.root / "tooling/cuaderno/commands.json"
        registry.write_text("changed", encoding="utf-8")
        with self.assertRaises(subject.CandidateFailure):
            subject.same_candidate(context, self.root, image_probe=self.probe)

    def test_context_shape_is_closed(self):
        context = subject.capture(self.root, IMAGE, image_probe=self.probe)
        context["untrusted"] = True
        with self.assertRaisesRegex(subject.CandidateFailure, "inválido"):
            subject.same_candidate(context, self.root, image_probe=self.probe)

    def test_matching_image_label_cannot_hide_wrong_application_bytes(self):
        def wrong_application(root, image_ref, runner):
            image = self.probe(root, image_ref, runner)
            image["runtime_application"]["files"]["boot.sh"] = "0" * 64
            return image
        with self.assertRaisesRegex(subject.CandidateFailure, "bytes"):
            subject.capture(self.root, IMAGE, image_probe=wrong_application)


if __name__ == "__main__":
    unittest.main()
