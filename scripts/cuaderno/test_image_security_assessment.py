"""Fail-closed tests for the separate retained-finding assessment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

if __package__:
    from . import image_security_assessment as subject
else:
    import image_security_assessment as subject


IMAGE = "sha256:" + "c" * 64
SOURCE = "a" * 40 + "+worktree." + "b" * 64
BINDING = {"format": "oci", "config_digest": IMAGE,
           "manifest_digest": "sha256:" + "d" * 64,
           "chain": ["sha256:" + "d" * 64, IMAGE]}


def match(cve, name, version, kind, purl, locations):
    if name == "python":
        constraint, suggested = subject.PYTHON_CONSTRAINTS[cve]
        details = []
        for vendor in ("python", "python_software_foundation"):
            row = {"type": "cpe-match", "matcher": "stock-matcher",
                   "searchedBy": {"namespace": "nvd:cpe", "cpes": [f"cpe:2.3:a:{vendor}:python:3.13.16:*:*:*:*:*:*:*"],
                                  "package": {"name": name, "version": version}},
                   "found": {"vulnerabilityID": cve, "versionConstraint": constraint,
                             "cpes": [f"cpe:2.3:a:{vendor}:python:*:*:*:*:*:*:*:*"]}}
            if suggested: row["fix"] = {"suggestedVersion": suggested}
            details.append(row)
    else:
        vendor = "busybox" if name != "zlib" else "zlib"
        constraint = "<= 1.37.0 (unknown)" if vendor == "busybox" else ">= 1.3.1.2, <= 1.3.2 (unknown)"
        details = [{"type": "cpe-match", "matcher": "apk-matcher",
                    "searchedBy": {"namespace": "nvd:cpe", "cpes": [f"cpe:2.3:a:{vendor}:{vendor}:{version.split('-r')[0]}:*:*:*:*:*:*:*"],
                                   "package": {"name": name, "version": version}},
                    "found": {"vulnerabilityID": cve, "versionConstraint": constraint,
                              "cpes": [f"cpe:2.3:a:{vendor}:{vendor}:*:*:*:*:*:*:*:*"]}}]
    return {
        "vulnerability": {"id": cve, "namespace": "nvd:cpe", "severity": "High"},
        "artifact": {"name": name, "version": version, "type": kind, "purl": purl,
                     "locations": [{"path": path, "layerID": "sha256:" + "1" * 64}
                                   for path in locations]},
        "matchDetails": details,
    }


PYTHON = match(
    "CVE-2026-82049", "python", "3.13.16", "binary", "pkg:generic/python@3.13.16",
    ["/usr/local/bin/python3.13", "/usr/local/lib/libpython3.13.so.1.0"],
)
PYTHON_RELEASE_ROWS = [match(
    cve, "python", "3.13.16", "binary", "pkg:generic/python@3.13.16",
    ["/usr/local/bin/python3.13", "/usr/local/lib/libpython3.13.so.1.0"],
) for cve in sorted(subject.PYTHON_RELEASE_CVES)]
POPLIB = match(
    "CVE-2025-15367", "python", "3.13.16", "binary", "pkg:generic/python@3.13.16",
    ["/usr/local/bin/python3.13", "/usr/local/lib/libpython3.13.so.1.0"],
)
BUSYBOX = match(
    "CVE-2025-60876", "busybox", "1.37.0-r31", "apk",
    "pkg:apk/alpine/busybox@1.37.0-r31?arch=x86_64&distro=alpine-3.23.6",
    ["/lib/apk/db/installed"],
)
ALPINE_ROWS = [match(
    cve, name, version, "apk",
    f"pkg:apk/alpine/{name}@{version}?arch=x86_64&distro=alpine-3.23.6"
    + ("&upstream=busybox" if name in {"busybox-binsh", "ssl_client"} else ""),
    ["/lib/apk/db/installed"],
) for name, (version, cve) in subject.ALPINE_PACKAGES.items()]
FRESH_EXPECTED_MATCHES = [*PYTHON_RELEASE_ROWS, POPLIB, *ALPINE_ROWS]


def alpine_metadata(source_inputs_sha256="2" * 64):
    return {
        "alpine_aports_commit": subject.ALPINE_COMMIT, "alpine_image": subject.ALPINE_IMAGE,
        "architecture": "x86_64", "source_date_epoch": 1790981383,
        "source_inputs_sha256": source_inputs_sha256,
        "packages": {name: {"version": expected[0], "apk_sha256": str(index + 3) * 64}
                     for index, (name, expected) in enumerate(subject.ALPINE_PACKAGES.items())},
        "patches": {
            "CVE-2025-60876": ["3c8c5b48f53ceb2641bb60c5c43b2a623e72246f2b7c0a87c1367136f455a936"],
            "CVE-2026-85091": [
                "110ff14375733173d8aa54574473424fbd7dfe4b81f1ca34a759c6fe14b15b14",
                "96040ee84d0d187905283912dbd3f7b66ac2033976a2ceefe9b8cca63143d9c2",
                "6475806cdb6383788a03e7af5617188ef2692803889cded1fcb014825923d16c",
                "a786b2b08412686008c7fe1247e90701cebde564037806bd9935f84907737cc4",
            ],
        },
        "runtime_files": {path: str(index + 7) * 64
                          for index, path in enumerate(subject.ALPINE_RUNTIME_FILES)},
        "license_urls": {"busybox": "https://git.busybox.net/busybox/tree/LICENSE",
                         "zlib": "https://zlib.net/zlib_license.html"},
    }


class Fixture:
    def __init__(self, root: Path, matches=None):
        self.root = root.resolve(); self.evidence = self.root / ".cuaderno-runs"; self.evidence.mkdir()
        source_inputs = self.root / "docker/runtime-security/source-inputs.json"
        source_inputs.parent.mkdir(parents=True)
        source_inputs.write_text('{"fixture":"pinned"}\n', encoding="utf-8")
        self.source_inputs_sha256 = hashlib.sha256(source_inputs.read_bytes()).hexdigest()
        self.scan = self.root / "data/cuaderno/scans/fresh"; (self.scan / "linux-scanner").mkdir(parents=True)
        self.archive = self.scan / "image.tar"; self.archive.write_bytes(b"retained immutable image")
        self.report = self.scan / "linux-scanner/grype-linux.json"
        self.matches = list(FRESH_EXPECTED_MATCHES if matches is None else matches)
        self.write_report()
        self.alpine = alpine_metadata(self.source_inputs_sha256)
        alpine = self.alpine
        alpine_provenance = {"schema_version": 1, **{k: v for k, v in alpine.items() if k != "license_urls"}, "verified": True}
        python_provenance = self.python_provenance()
        self.node = self.node_provenance()
        self.context = {"schema_version": 1, "candidate_id": "7f90be2e-c663-43e7-914a-6efac5524841",
                        "git_commit": "a" * 40, "source_sha256": "b" * 64,
                        "source_identity": SOURCE, "image_id": IMAGE,
                        "environment_fingerprint": "e" * 64, "commands_registry_sha256": "f" * 64,
                        "environment": {"image": {"artifacts": {
                            "security_python_backports": hashlib.sha256(
                                (json.dumps(python_provenance, sort_keys=True) + "\n").encode()).hexdigest(),
                            "security_alpine_backports": hashlib.sha256(
                                (json.dumps(alpine_provenance, sort_keys=True) + "\n").encode()).hexdigest(),
                            "security_node_runtime": hashlib.sha256(
                                (json.dumps(self.node, sort_keys=True) + "\n").encode()).hexdigest(),
                        }}}}
        self.node_artifact_sha = self.context["environment"]["image"]["artifacts"]["security_node_runtime"]
        self.context_path = self.evidence / "candidate.json"
        self.context_path.write_text(json.dumps(self.context), encoding="utf-8")
        self.summary = self.scan / "linux-scanner/summary-linux.json"
        self.write_summary()
        self.proofs = []
        classified = {kind: [] for kind in subject.PROOF_KINDS}
        for row in self.matches:
            fp = subject.match_fingerprint(row)
            classified[subject._classify(fp)].append(fp["sha256"])
        metadata = {
            "python-release": {**subject.PYTHON_RELEASE, "cves": sorted(subject.PYTHON_RELEASE_CVES)},
            "poplib-backport": {
                "cve": subject.patch_runtime_security.CVE,
                "upstream_commit": subject.patch_runtime_security.UPSTREAM_COMMIT,
                "original_sha256": subject.patch_runtime_security.ORIGINAL_SHA256,
                "patched_sha256": subject.patch_runtime_security.PATCHED_SHA256,
                "original_url": subject.patch_runtime_security.ORIGINAL_URL,
                "patched_url": subject.patch_runtime_security.PATCHED_URL,
                "commit_url": subject.patch_runtime_security.COMMIT_URL,
                "license_url": subject.patch_runtime_security.LICENSE_URL,
            },
            "alpine-backports": self.alpine,
        }
        for kind in sorted(subject.PROOF_KINDS):
            path = self.evidence / f"proof-{kind}.json"
            path.write_text(json.dumps({"schema_version": 1, "kind": kind,
                                        "metadata": metadata[kind], "fingerprints": classified[kind]}),
                            encoding="utf-8")
            self.proofs.append(path)
        self.output = self.evidence / "assessment.json"

    def write_report(self):
        self.report.write_text(json.dumps({"source": {"target": {"userInput": subject.image_archive_audit.CONTAINER_ARCHIVE_INPUT}},
                                           "matches": self.matches, "ignoredMatches": []}), encoding="utf-8")

    def write_summary(self):
        raw = self.report.read_bytes()
        self.summary.write_text(json.dumps({
            "status": "findings", "scanner_exit": 2, "image_id": IMAGE, "source_commit": SOURCE,
            "matches": len(self.matches), "ignored_matches": 0, "severity_counts": {"High": len(self.matches)},
            "archive_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "archive_binding": BINDING, "report_sha256": hashlib.sha256(raw).hexdigest(),
            "grype": {"version": subject.image_audit.GRYPE_VERSION,
                      "git_commit": subject.image_audit.GRYPE_COMMIT,
                      "sha256": subject.image_archive_audit.LINUX_GRYPE_SHA256,
                      "platform": "linux_amd64"},
            "database": {"digest": "xxh64:0123456789abcdef",
                         "source": subject.image_audit.DB_SOURCE,
                         "client_version": subject.image_audit.DB_CLIENT_VERSION},
            "database_provision": {"receipt_sha256": "d" * 64,
                "installed_database_sha256": "1" * 64, "import_metadata_sha256": "2" * 64,
                "raw_database_sha256": subject.image_audit.VULNERABILITY_DB_RAW_SHA256,
                "archive_sha256": subject.image_audit.VULNERABILITY_DB_ARCHIVE_SHA256},
            "paths": {"archive": self.archive.relative_to(self.root).as_posix(),
                      "report": self.report.relative_to(self.root).as_posix(),
                      "summary": self.summary.relative_to(self.root).as_posix()},
        }), encoding="utf-8")

    @staticmethod
    def python_provenance():
        return {"status": "patched", "cve": subject.patch_runtime_security.CVE,
                "python": "3.13.16", "path": "/usr/local/lib/python3.13/poplib.py",
                "original_sha256": subject.patch_runtime_security.ORIGINAL_SHA256,
                "patched_sha256": subject.patch_runtime_security.PATCHED_SHA256,
                "upstream_commit": subject.patch_runtime_security.UPSTREAM_COMMIT,
                "sources": {"original": subject.patch_runtime_security.ORIGINAL_URL,
                            "patched": subject.patch_runtime_security.PATCHED_URL,
                            "commit": subject.patch_runtime_security.COMMIT_URL,
                            "license": subject.patch_runtime_security.LICENSE_URL}}

    def node_provenance(self):
        binder = subject.bind_system_node
        root = "/opt/recipes/venv/lib/python3.13/site-packages/nodejs_wheel"
        return {
            "schema_version": 1, "status": "bound",
            "wheel": {"distribution": binder.WHEEL_DISTRIBUTION, "version": binder.WHEEL_VERSION,
                      "root": root, "node_path": root + "/bin/node",
                      "original_node_sha256": binder.WHEEL_NODE_SHA256,
                      "executable_sha256": binder.WHEEL_EXECUTABLE_SHA256,
                      "license_path": root.rsplit("/", 1)[0] + "/nodejs_wheel_binaries-24.19.0.dist-info/licenses/LICENSE",
                      "license_sha256": binder.WHEEL_LICENSE_SHA256},
            "runtime": {"path": "/usr/bin/node", "sha256": binder.SYSTEM_NODE_SHA256,
                        "version": binder.SYSTEM_NODE_VERSION, "zlib_version": "1.3.2",
                        "needed": ["libz.so.1"],
                        "zlib": {"link": "/usr/lib/libz.so.1", "path": binder.ZLIB_REAL_PATH,
                                 "sha256": self.alpine["runtime_files"][binder.ZLIB_REAL_PATH]}},
            "package": {"name": "nodejs", "version": "24.18.1-r0",
                        "apk_url": binder.APK_URL, "apk_sha256": binder.APK_SHA256,
                        "apk_size": binder.APK_SIZE, "aports_commit": binder.APORTS_COMMIT,
                        "apkbuild_url": binder.APKBUILD_URL, "apkbuild_sha256": binder.APKBUILD_SHA256,
                        "source_url": binder.SOURCE_URL, "license": binder.LICENSE,
                        "license_url": binder.LICENSE_URL, "shared_zlib": True},
        }

    def runtime(self, _context, *, root):
        alpine = self.alpine
        provenance = {"schema_version": 1, **{k: v for k, v in alpine.items() if k != "license_urls"}, "verified": True}
        expected_js = [5, hashlib.sha256(b"cuaderno").hexdigest(), "1.3.2"]
        return {"schema_version": 1, "python_version": "3.13.16",
                "poplib_sha256": subject.patch_runtime_security.PATCHED_SHA256,
                "poplib_rejected": ["CR", "LF", "NUL", "DEL"],
                "poplib_sent": ["5553455220736166650d0a"],
                "apk_versions": {name: value[0] for name, value in subject.ALPINE_PACKAGES.items()},
                "runtime_files": alpine["runtime_files"],
                "busybox_rejected": ["20626164", "09626164", "0d626164", "0a626164"],
                "busybox_normal": {"returncode": 0, "stdout": "ok", "stderr": "",
                                   "server_finished": True},
                "python_provenance": self.python_provenance(),
                "python_provenance_sha256": self.context["environment"]["image"]["artifacts"]["security_python_backports"],
                "alpine_provenance": provenance,
                "alpine_provenance_sha256": self.context["environment"]["image"]["artifacts"]["security_alpine_backports"],
                "node_provenance": self.node,
                "node_provenance_sha256": self.node_artifact_sha,
                "node_runtime": {"wheel_node_is_link": True, "wheel_node_target": "/usr/bin/node",
                                 "system_node_is_regular": True,
                                 "system_node_sha256": subject.bind_system_node.SYSTEM_NODE_SHA256,
                                 "executable_sha256": subject.bind_system_node.WHEEL_EXECUTABLE_SHA256,
                                 "license_sha256": subject.bind_system_node.WHEEL_LICENSE_SHA256,
                                 "zlib_link_target": "libz.so.1.3.2",
                                 "zlib_sha256": alpine["runtime_files"][subject.bind_system_node.ZLIB_REAL_PATH],
                                 "ldd": "\tlibz.so.1 => /usr/lib/libz.so.1 (0x1234)\n",
                                 "direct": expected_js,
                                 "wrapper": {"returncode": 0,
                                             "stdout": json.dumps(expected_js, separators=(",", ":")) + "\n",
                                             "stderr": ""}}}

    def assess(self, **kwargs):
        calls = []
        def verify_database(paths, token, tool_hash, archive_hash):
            calls.append(token)
            if token != "d" * 64:
                raise subject.image_audit.ImageAuditFailure("Invalid trusted token")
            return {"installed_database_sha256": "1" * 64, "import_metadata_sha256": "2" * 64,
                "raw_database_sha256": subject.image_audit.VULNERABILITY_DB_RAW_SHA256,
                "archive_sha256": subject.image_audit.VULNERABILITY_DB_ARCHIVE_SHA256,
                "import_metadata": {"digest": "xxh64:0123456789abcdef",
                    "source": subject.image_audit.DB_SOURCE,
                    "client_version": subject.image_audit.DB_CLIENT_VERSION}}
        with patch.object(subject.image_archive_audit, "_archive_binding", return_value=BINDING), \
             patch.dict(subject.os.environ, {"CUADERNO_SCANNER_DB_RECEIPT_SHA256": "d" * 64}), \
             patch.object(subject.image_archive_audit, "_validate_archive_report",
                          return_value=(self.matches, [], {"High": len(self.matches)})):
            return subject.assess(context_path=self.context_path, archive=self.archive,
                                  report_path=self.report, summary_path=self.summary,
                                  proof_paths=self.proofs, output_path=self.output, root=self.root,
                                  context_validator=lambda *_: None,
                                  runtime_probe=kwargs.get("runtime_probe", self.runtime),
                                  database_verifier=kwargs.get("database_verifier", verify_database))


class SecurityAssessmentTests(unittest.TestCase):
    def fixture(self, matches=None):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        return Fixture(Path(temporary.name), matches)

    def test_reviewed_exact_sources_preserve_every_raw_match_and_raw_failure(self):
        fixture = self.fixture(); result = fixture.assess()
        self.assertEqual(result["status"], "reviewed-no-unresolved")
        self.assertEqual(result["raw_scanner_status"], "findings")
        self.assertEqual(result["raw_scanner_exit"], 2)
        self.assertEqual(result["raw_matches"], fixture.matches)
        self.assertEqual(result["ignored_matches"], [])
        self.assertEqual(len(result["fingerprints"]), 11)

    def test_untrusted_database_provision_prevents_assessment(self):
        fixture = self.fixture()
        def untrusted(*_):
            raise subject.image_audit.ImageAuditFailure("Changed receipt")
        with self.assertRaisesRegex(subject.AssessmentFailure, "provisión"):
            fixture.assess(database_verifier=untrusted)
        self.assertFalse(fixture.output.exists())

    def test_database_drift_after_evaluation_prevents_output(self):
        fixture = self.fixture()
        summary = json.loads(fixture.summary.read_text())
        calls = []
        def changed_on_second_check(*_):
            calls.append(True)
            if len(calls) == 2:
                raise subject.image_audit.ImageAuditFailure("Receipt changed")
            return {**summary["database_provision"], "import_metadata": summary["database"]}
        with self.assertRaisesRegex(subject.AssessmentFailure, "cambió durante"):
            fixture.assess(database_verifier=changed_on_second_check)
        self.assertEqual(len(calls), 2)
        self.assertFalse(fixture.output.exists())

    def test_extra_unknown_and_duplicate_findings_are_rejected(self):
        unknown = match("CVE-2099-0001", "mystery", "1", "apk", "pkg:apk/alpine/mystery@1", ["/lib/apk/db/installed"])
        for rows, message in (([PYTHON, unknown], "sin prueba"), ([PYTHON, PYTHON], "duplicada")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                if message == "sin prueba":
                    with self.assertRaisesRegex(subject.AssessmentFailure, message): Fixture(Path(temporary), rows)
                else:
                    fixture = Fixture(Path(temporary), [PYTHON])
                    fixture.matches.append(PYTHON); fixture.write_report(); fixture.write_summary()
                    with self.assertRaisesRegex(subject.AssessmentFailure, message): fixture.assess()

    def test_tampered_report_or_summary_is_rejected(self):
        fixture = self.fixture(); fixture.report.write_text("{}", encoding="utf-8")
        with self.assertRaises(subject.AssessmentFailure): fixture.assess()

    def test_wrong_fingerprint_digest_and_pretend_verified_patch_are_rejected(self):
        fixture = self.fixture()
        proof = next(path for path in fixture.proofs if "poplib" in path.name)
        value = json.loads(proof.read_text()); value["fingerprints"] = ["0" * 64]
        value["metadata"] = {"verified": True}; proof.write_text(json.dumps(value))
        with self.assertRaises(subject.AssessmentFailure): fixture.assess()

    def test_wrong_runtime_version_or_unproved_poplib_behavior_is_rejected(self):
        for mutation in ({"python_version": "3.13.15"}, {"poplib_rejected": ["CR", "LF"]}):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()
                def runtime(context, *, root): return {**fixture.runtime(context, root=root), **mutation}
                with self.assertRaisesRegex(subject.AssessmentFailure, "runtime"):
                    fixture.assess(runtime_probe=runtime)

    def test_mutated_match_details_and_old_or_development_apks_are_rejected(self):
        mutated = json.loads(json.dumps(PYTHON))
        mutated["matchDetails"][0]["matcher"] = "pretend-matcher"
        old_busybox = match(
            "CVE-2025-60876", "busybox", "1.37.0-r30", "apk",
            "pkg:apk/alpine/busybox@1.37.0-r30?arch=x86_64&distro=alpine-3.23.6",
            ["/lib/apk/db/installed"],
        )
        zlib_dev = match(
            "CVE-2026-85091", "zlib-dev", "1.3.2-r1", "apk",
            "pkg:apk/alpine/zlib-dev@1.3.2-r1?arch=x86_64&distro=alpine-3.23.6&upstream=zlib",
            ["/lib/apk/db/installed"],
        )
        for row in (mutated, old_busybox, zlib_dev):
            with self.subTest(artifact=row["artifact"]), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(subject.AssessmentFailure):
                    Fixture(Path(temporary), [row])

    def test_checkout_source_inputs_and_runtime_file_bytes_are_independently_bound(self):
        fixture = self.fixture()
        (fixture.root / "docker/runtime-security/source-inputs.json").write_text(
            '{"fixture":"changed"}\n', encoding="utf-8")
        with self.assertRaisesRegex(subject.AssessmentFailure, "source-inputs"):
            fixture.assess()
        fixture = self.fixture()
        def runtime(context, *, root):
            value = fixture.runtime(context, root=root)
            value["runtime_files"] = {**value["runtime_files"], "/bin/busybox": "0" * 64}
            return value
        with self.assertRaisesRegex(subject.AssessmentFailure, "runtime"):
            fixture.assess(runtime_probe=runtime)

    def test_docker_probe_uses_exact_immutable_sandbox_and_strict_json(self):
        fixture = self.fixture()
        runtime = fixture.runtime(fixture.context, root=fixture.root)
        commands = []
        def runner(command, **kwargs):
            commands.append(command)
            if command[:3] == ["docker", "image", "inspect"]:
                payload = [{"Id": IMAGE, "Config": {"Labels": {
                    "io.cuaderno.source-identity": SOURCE,
                }}}]
            else:
                payload = runtime
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        self.assertEqual(subject.docker_runtime_probe(fixture.context, root=fixture.root,
                                                      runner=runner), runtime)
        run = commands[1]
        self.assertIn("--network", run); self.assertIn("none", run)
        self.assertIn("--read-only", run); self.assertIn("--cap-drop", run)
        self.assertIn("no-new-privileges", run); self.assertNotIn("-v", run)
        self.assertIn("-I", run); self.assertIn("-S", run)
        def duplicate_runner(command, **kwargs):
            return SimpleNamespace(returncode=0, stdout='[{"Id":"x","Id":"y"}]', stderr="")
        with self.assertRaisesRegex(subject.AssessmentFailure, "duplicada"):
            subject.docker_runtime_probe(fixture.context, root=fixture.root,
                                         runner=duplicate_runner)

    def test_node_artifact_symlink_binary_zlib_and_wrapper_are_all_required(self):
        mutations = (
            ("wheel_node_target", "/tmp/untrusted-node"),
            ("system_node_sha256", "0" * 64),
            ("zlib_sha256", "0" * 64),
        )
        for key, value in mutations:
            fixture = self.fixture()
            def runtime(context, *, root, key=key, value=value):
                result = fixture.runtime(context, root=root)
                result["node_runtime"] = {**result["node_runtime"], key: value}
                return result
            with self.subTest(key=key), self.assertRaisesRegex(subject.AssessmentFailure, "Node"):
                fixture.assess(runtime_probe=runtime)
        fixture = self.fixture()
        fixture.context["environment"]["image"]["artifacts"]["security_node_runtime"] = "0" * 64
        fixture.context_path.write_text(json.dumps(fixture.context), encoding="utf-8")
        with self.assertRaisesRegex(subject.AssessmentFailure, "Node"):
            fixture.assess()
        fixture = self.fixture()
        def broken_wrapper(context, *, root):
            result = fixture.runtime(context, root=root)
            result["node_runtime"]["wrapper"]["returncode"] = 1
            return result
        with self.assertRaisesRegex(subject.AssessmentFailure, "Node"):
            fixture.assess(runtime_probe=broken_wrapper)


if __name__ == "__main__":
    unittest.main()
