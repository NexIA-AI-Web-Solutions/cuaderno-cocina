"""Pure boundary tests for the retained-archive Linux scanner."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

if __package__:
    from . import image_archive_audit as subject
else:
    import image_archive_audit as subject


SOURCE_REF = "b" * 40 + "+worktree." + "c" * 64


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def build_oci_archive(path, *, source_ref=SOURCE_REF, duplicate=None, link=None,
                      extra_platform=False, corrupt_config=False, wrong_docker_config=False,
                      platform_value=None):
    config = _json({"architecture": "amd64", "os": "linux", "config": {
        "Labels": {"io.cuaderno.source-identity": source_ref},
    }})
    config_id = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = _json({"schemaVersion": 2, "mediaType": subject.OCI_MANIFEST,
                      "config": {"mediaType": subject.OCI_CONFIG,
                                 "digest": config_id, "size": len(config)}, "layers": []})
    manifest_id = "sha256:" + hashlib.sha256(manifest).hexdigest()
    descriptors = [{"mediaType": subject.OCI_MANIFEST, "digest": manifest_id,
                    "size": len(manifest), "platform": {"os": "linux", "architecture": "amd64"}}]
    if platform_value is not None:
        descriptors[0]["platform"] = platform_value
    if extra_platform:
        descriptors.append(dict(descriptors[0]))
    nested = _json({"schemaVersion": 2, "mediaType": subject.OCI_INDEX,
                    "manifests": descriptors})
    nested_id = "sha256:" + hashlib.sha256(nested).hexdigest()
    index = _json({"schemaVersion": 2, "mediaType": subject.OCI_INDEX, "manifests": [
        {"mediaType": subject.OCI_INDEX, "digest": nested_id, "size": len(nested)},
    ]})
    files = {
        "oci-layout": _json({"imageLayoutVersion": "1.0.0"}), "index.json": index,
        "manifest.json": _json([{"Config": subject._blob_name(config_id), "RepoTags": None,
                                  "Layers": []}]),
        subject._blob_name(nested_id): nested, subject._blob_name(manifest_id): manifest,
        subject._blob_name(config_id): config + (b"tampered" if corrupt_config else b""),
    }
    if wrong_docker_config:
        files["manifest.json"] = _json([{"Config": "blobs/sha256/" + "f" * 64,
                                          "RepoTags": None, "Layers": []}])
    with tarfile.open(path, "w") as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
        if duplicate:
            raw = files[duplicate]
            info = tarfile.TarInfo(duplicate)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
        if link:
            info = tarfile.TarInfo(link)
            info.type = tarfile.SYMTYPE
            info.linkname = "index.json"
            archive.addfile(info)
    return {"config": config_id, "manifest": manifest_id, "index": nested_id}


def build_classic_archive(path, *, source_ref=SOURCE_REF, os_name="linux",
                          architecture="amd64", wrong_config_name=False,
                          partial_oci=None):
    config = _json({"architecture": architecture, "os": os_name, "config": {
        "Labels": {"io.cuaderno.source-identity": source_ref},
    }})
    config_hex = hashlib.sha256(config).hexdigest()
    config_name = (("f" * 64) if wrong_config_name else config_hex) + ".json"
    layer_name, layer = "a" * 64 + "/layer.tar", b"synthetic layer bytes"
    files = {
        "manifest.json": _json([{"Config": config_name, "RepoTags": ["example:latest"],
                                  "Layers": [layer_name]}]),
        config_name: config,
        layer_name: layer,
    }
    if partial_oci:
        files[partial_oci] = (_json({"imageLayoutVersion": "1.0.0"})
                              if partial_oci == "oci-layout" else _json({"schemaVersion": 2}))
    with tarfile.open(path, "w") as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    return "sha256:" + config_name.removesuffix(".json")


class FakeRunner:
    def __init__(self, paths, report_image_id, *, matches=True, mutate_archive=False,
                 mutate_database=False, report_input=None):
        self.paths = paths
        self.matches = matches
        self.mutate_archive = mutate_archive
        self.mutate_database = mutate_database
        self.report_image_id = report_image_id
        self.report_input = report_input
        self.calls = []

    def __call__(self, argv, **kwargs):
        argv = list(map(str, argv))
        self.calls.append((argv, kwargs))
        if argv[1:] == ["version"]:
            return subprocess.CompletedProcess(argv, 0, stdout=(
                "Application: grype\nVersion: 0.119.0\n"
                f"GitCommit: {subject.shared.GRYPE_COMMIT}\n"
            ), stderr="")
        if argv[1:] == ["db", "status", "-o", "json"]:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({
                "schemaVersion": subject.shared.DB_SCHEMA_VERSION,
                "from": subject.shared.DB_SOURCE,
                "built": subject.shared.DB_BUILT,
                "path": str(self.paths.database),
                "valid": True,
            }), stderr="")
        if "--fail-on" in argv:
            report = {
                "matches": ([{"vulnerability": {"id": "CVE-SYNTHETIC", "severity": "High"}}]
                            if self.matches else []),
                "ignoredMatches": [],
                "source": {"type": "image", "target": {
                    "userInput": self.report_input or f"docker-archive:{self.paths.archive}",
                    "imageID": self.report_image_id,
                }},
                "descriptor": {"name": "grype", "version": subject.shared.GRYPE_VERSION},
            }
            self.paths.report.write_text(json.dumps(report), encoding="utf-8")
            if self.mutate_archive:
                self.paths.archive.write_bytes(b"changed")
            if self.mutate_database:
                self.paths.database.write_bytes(b"changed db")
            return subprocess.CompletedProcess(argv, 2 if self.matches else 0, stdout="", stderr="")
        raise AssertionError(argv)


class ArchiveAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        scan = self.root / "data/cuaderno/scans/12345678-1234-4234-8234-123456789abc"
        tool = self.root / "data/cuaderno/tooling/grype-linux-0.119.0"
        database = self.root / "data/cuaderno/tooling/grype-db/6"
        scan.mkdir(parents=True)
        tool.mkdir(parents=True)
        database.mkdir(parents=True)
        self.ids = build_oci_archive(scan / "image.tar")
        (tool / "grype").write_bytes(b"linux grype")
        (tool / "grype_0.119.0_linux_amd64.tar.gz").write_bytes(b"official tar")
        (database / "vulnerability.db").write_bytes(b"offline db")
        (database / "import.json").write_text(json.dumps({
            "digest": subject.shared.DB_DIGEST, "source": subject.shared.DB_SOURCE,
            "client_version": subject.shared.DB_CLIENT_VERSION,
        }), encoding="utf-8")
        self.archive = scan / "image.tar"
        self.paths = subject.archive_paths(self.root, self.archive)
        self.hashes = {
            "expected_archive_sha256": subject._sha256(self.archive),
            "expected_tool_hash": hashlib.sha256(b"linux grype").hexdigest(),
            "expected_tool_archive_hash": hashlib.sha256(b"official tar").hexdigest(),
            "expected_db_hash": hashlib.sha256(b"offline db").hexdigest(),
        }

    def run_audit(self, runner, **changes):
        values = dict(archive=self.archive, image_id=self.ids["index"], source_ref=SOURCE_REF,
                      root=self.root, runner=runner, environ={"CUADERNO_ENV": "test"}, **self.hashes)
        values.update(changes)
        return subject.run_archive_audit(**values)

    def test_scans_existing_archive_without_docker_and_preserves_identity(self):
        runner = FakeRunner(self.paths, self.ids["config"])
        status, summary = self.run_audit(runner)
        self.assertEqual(status, 2)
        self.assertEqual(summary["image_id"], self.ids["index"])
        self.assertEqual(summary["archive_binding"]["config_digest"], self.ids["config"])
        self.assertEqual(summary["source_commit"], SOURCE_REF)
        self.assertEqual(summary["matches"], 1)
        self.assertTrue(self.paths.report.is_file())
        self.assertTrue(self.paths.summary.is_file())
        self.assertFalse(any(call[0][0] == "docker" for call in runner.calls))
        scan = next(call for call in runner.calls if "--fail-on" in call[0])
        self.assertEqual(scan[1]["env"]["GRYPE_DB_AUTO_UPDATE"], "false")
        self.assertEqual(scan[1]["env"]["GRYPE_EXTERNAL_SOURCES_ENABLE"], "false")

    def test_receipt_identity_is_rechecked_after_status_and_scan(self):
        runner = FakeRunner(self.paths, self.ids["config"])
        stamp = json.loads(self.paths.db_stamp.read_text())
        stamp["digest"] = "xxh64:0123456789abcdef"
        self.paths.db_stamp.write_text(json.dumps(stamp))
        receipt = {"import_metadata": stamp,
            "installed_database_sha256": self.hashes["expected_db_hash"],
            "import_metadata_sha256": subject._sha256(self.paths.db_stamp),
            "raw_database_sha256": subject.shared.VULNERABILITY_DB_RAW_SHA256,
            "archive_sha256": subject.shared.VULNERABILITY_DB_ARCHIVE_SHA256}
        with patch.object(subject.scanner_db_provenance, "verify", return_value=receipt) as verify:
            status, summary = self.run_audit(runner, expected_db_hash=None,
                expected_db_receipt_sha256="e" * 64)
        self.assertEqual(status, 2)
        self.assertEqual(verify.call_count, 4)
        self.assertTrue(all(call.args[1] == "e" * 64 for call in verify.call_args_list))
        self.assertEqual(summary["database"], stamp)
        self.assertEqual(summary["database_provision"]["receipt_sha256"], "e" * 64)
        self.assertEqual(sum(argv[1:] == ["db", "status", "-o", "json"]
            for argv, _ in runner.calls), 2)

    def test_clean_complete_report_is_accepted(self):
        status, summary = self.run_audit(FakeRunner(self.paths, self.ids["config"], matches=False))
        self.assertEqual(status, 0)
        self.assertEqual(summary["status"], "clean")

    def test_receipt_drift_after_status_aborts_before_scan(self):
        runner = FakeRunner(self.paths, self.ids["config"])
        receipt = {"import_metadata": json.loads(self.paths.db_stamp.read_text()),
            "installed_database_sha256": self.hashes["expected_db_hash"]}
        with patch.object(subject.scanner_db_provenance, "verify",
                          side_effect=[receipt, subject.shared.ImageAuditFailure("Receipt changed")]):
            with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "Receipt changed"):
                self.run_audit(runner, expected_db_hash=None, expected_db_receipt_sha256="e" * 64)
        self.assertFalse(any("--fail-on" in argv for argv, _ in runner.calls))
        self.assertFalse(self.paths.summary.exists())

    def test_stamp_only_mutation_during_scan_rejects_summary(self):
        class MutatingRunner(FakeRunner):
            def __call__(self, argv, **kwargs):
                result = super().__call__(argv, **kwargs)
                if "--fail-on" in argv:
                    self.paths.db_stamp.write_text('{}')
                return result
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "metadata"):
            self.run_audit(MutatingRunner(self.paths, self.ids["config"]))
        self.assertFalse(self.paths.summary.exists())

    def test_config_manifest_and_index_ids_bind_to_the_same_linux_image(self):
        for identity in (self.ids["config"], self.ids["manifest"], self.ids["index"]):
            binding = subject._archive_binding(
                self.archive, image_id=identity, source_ref=SOURCE_REF,
            )
            self.assertEqual(binding["config_digest"], self.ids["config"])
            self.assertIn(identity, binding["chain"])

    def test_classic_docker_save_binds_exact_config_and_regular_layers(self):
        image_id = build_classic_archive(self.archive)
        binding = subject._archive_binding(
            self.archive, image_id=image_id, source_ref=SOURCE_REF,
        )
        self.assertEqual(binding["format"], "docker")
        self.assertEqual(binding["config_digest"], image_id)
        self.assertEqual(binding["chain"][-1], image_id)

    def test_classic_docker_save_rejects_wrong_config_label_platform_and_partial_oci(self):
        cases = [
            ({"wrong_config_name": True}, "nombre de la config"),
            ({"source_ref": "d" * 40}, "identidad de fuente"),
            ({"os_name": "windows"}, "linux/amd64"),
            ({"architecture": "arm64"}, "linux/amd64"),
            ({"partial_oci": "oci-layout"}, "OCI parciales"),
            ({"partial_oci": "index.json"}, "OCI parciales"),
        ]
        for options, message in cases:
            image_id = build_classic_archive(self.archive, **options)
            with self.subTest(options=options), self.assertRaisesRegex(
                    subject.shared.ImageAuditFailure, message):
                subject._archive_binding(
                    self.archive, image_id=image_id, source_ref=SOURCE_REF,
                )
        build_oci_archive(self.archive)

    def test_oci_rejects_non_object_platform_before_traversal(self):
        ids = build_oci_archive(self.archive, platform_value="linux/amd64")
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "plataforma inválida"):
            subject._archive_binding(
                self.archive, image_id=ids["index"], source_ref=SOURCE_REF,
            )
        self.ids = build_oci_archive(self.archive)

    def test_archive_chain_rejects_wrong_identity_hash_label_and_docker_manifest(self):
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "Image ID"):
            subject._archive_binding(
                self.archive, image_id="sha256:" + "f" * 64, source_ref=SOURCE_REF,
            )
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "identidad de fuente"):
            subject._archive_binding(
                self.archive, image_id=self.ids["index"], source_ref="d" * 40,
            )
        for options, message in (({"corrupt_config": True}, "hash o tamaño"),
                                 ({"wrong_docker_config": True}, "manifest.json")):
            ids = build_oci_archive(self.archive, **options)
            with self.assertRaisesRegex(subject.shared.ImageAuditFailure, message):
                subject._archive_binding(
                    self.archive, image_id=ids["index"], source_ref=SOURCE_REF,
                )
        self.ids = build_oci_archive(self.archive)

    def test_archive_rejects_duplicate_links_traversal_and_ambiguous_linux_platform(self):
        cases = [
            ({"duplicate": "index.json"}, "duplicadas"),
            ({"link": "linked-index"}, "enlaces"),
            ({"link": "../outside"}, "ruta no confinada"),
            ({"extra_platform": True}, "ciclos|repetidos|\u00fanica"),
        ]
        for options, message in cases:
            ids = build_oci_archive(self.archive, **options)
            with self.subTest(options=options), self.assertRaisesRegex(
                    subject.shared.ImageAuditFailure, message):
                subject._archive_binding(
                    self.archive, image_id=ids["index"], source_ref=SOURCE_REF,
                )
        self.ids = build_oci_archive(self.archive)

    def test_report_accepts_only_exact_normalized_input_and_selected_config(self):
        source_input = "docker-archive:/scan-input/image.tar"
        binding = subject._archive_binding(
            self.archive, image_id=self.ids["index"], source_ref=SOURCE_REF,
        )
        def report(user_input, image_id=self.ids["config"]):
            return {"matches": [], "ignoredMatches": [],
                    "source": {"type": "image", "target": {
                        "userInput": user_input, "imageID": image_id,
                    }}, "descriptor": {"name": "grype", "version": subject.shared.GRYPE_VERSION}}
        for exact in (source_input, "/scan-input/image.tar"):
            subject._validate_archive_report(report(exact), binding=binding, source_input=source_input)
        omitted = report("/scan-input/image.tar")
        omitted.pop("ignoredMatches")
        subject._validate_archive_report(omitted, binding=binding, source_input=source_input)
        explicit_null = report(source_input)
        explicit_null["ignoredMatches"] = None
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "imagen exactos"):
            subject._validate_archive_report(explicit_null, binding=binding, source_input=source_input)
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "entrada exacta"):
            subject._validate_archive_report(
                report("docker-archive:/another/image.tar"), binding=binding,
                source_input=source_input,
            )
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "imagen exactos"):
            subject._validate_archive_report(
                report(source_input, "sha256:" + "e" * 64), binding=binding,
                source_input=source_input,
            )

    def test_default_runner_uses_only_pinned_offline_linux_container_mounts(self):
        calls = []
        def docker(argv, **kwargs):
            command = list(map(str, argv))
            calls.append((command, kwargs))
            guest = command[command.index(subject.SCANNER_IMAGE) + 1:]
            if guest == ["version"]:
                output = ("Application: grype\nVersion: 0.119.0\n"
                          f"GitCommit: {subject.shared.GRYPE_COMMIT}\n")
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
            if guest == ["db", "status", "-o", "json"]:
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
                    "schemaVersion": subject.shared.DB_SCHEMA_VERSION,
                    "from": subject.shared.DB_SOURCE, "built": subject.shared.DB_BUILT,
                    "path": subject.CONTAINER_DATABASE, "valid": True,
                }), stderr="")
            self.assertEqual(guest[-1], subject.CONTAINER_ARCHIVE_INPUT)
            report = {
                "matches": [{"vulnerability": {"id": "CVE-SYNTHETIC", "severity": "High"}}],
                "ignoredMatches": [],
                "source": {"type": "image", "target": {
                    "userInput": "/scan-input/image.tar", "imageID": self.ids["config"],
                }},
                "descriptor": {"name": "grype", "version": subject.shared.GRYPE_VERSION},
            }
            self.paths.report.write_text(json.dumps(report), encoding="utf-8")
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="findings")

        status, summary = subject.run_archive_audit(
            archive=self.archive, image_id=self.ids["index"], source_ref=SOURCE_REF,
            root=self.root, docker_runner=docker, environ={"CUADERNO_ENV": "test", "SECRET_KEY": "never"},
            **self.hashes,
        )
        self.assertEqual(status, 2)
        self.assertEqual(summary["matches"], 1)
        for command, kwargs in calls:
            self.assertEqual(command[:4], ["docker", "run", "--rm", "--name"])
            self.assertRegex(command[4], r"^cuaderno-grype-[0-9a-f]{12}$")
            self.assertEqual(command[5:9], ["--network", "none", "--read-only", "--cap-drop"])
            self.assertIn(subject.SCANNER_IMAGE, command)
            if hasattr(subject.os, "getuid") and hasattr(subject.os, "getgid"):
                self.assertIn("--user", command)
                self.assertEqual(command[command.index("--user") + 1],
                                 f"{subject.os.getuid()}:{subject.os.getgid()}")
            self.assertIn("HOME=/tmp", command)
            self.assertIn("XDG_CACHE_HOME=/tmp/.cache", command)
            self.assertNotIn("docker.sock", " ".join(command))
            self.assertNotIn(str(self.root) + ",target=/project", " ".join(command))
            self.assertNotIn("never", " ".join(command))
            mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]
            self.assertEqual(len(mounts), 4)
            self.assertTrue(any("target=/grype-tool,readonly" in mount for mount in mounts))
            self.assertTrue(any("target=/grype-db,readonly" in mount for mount in mounts))
            self.assertTrue(any("target=/scan-input/image.tar,readonly" in mount for mount in mounts))
            self.assertEqual(sum("target=/scanner-output" in mount and not mount.endswith(",readonly")
                                 for mount in mounts), 1)
            self.assertNotIn("env", kwargs)

    def test_portable_runner_timeout_removes_only_its_generated_container(self):
        self.paths.scanner_dir.mkdir()
        cleanup = []
        def timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        runner = subject.LinuxContainerRunner(
            self.paths, runner=timeout,
            cleanup_runner=lambda argv, **kwargs: cleanup.append((argv, kwargs)),
        )
        with patch.object(subject.uuid, "uuid4", return_value=SimpleNamespace(hex="abcdef1234567890")), \
             self.assertRaises(subprocess.TimeoutExpired):
            runner([str(self.paths.tool), "version"], timeout=17)
        self.assertEqual(cleanup[0][0], ["docker", "rm", "-f", "cuaderno-grype-abcdef123456"])
        self.assertEqual(cleanup[0][1]["timeout"], 60)

    def test_wrong_hash_outside_archive_and_mutation_fail_closed(self):
        with self.assertRaises(subject.shared.ImageAuditFailure):
            self.run_audit(FakeRunner(self.paths, self.ids["config"]), expected_archive_sha256="0" * 64)
        outside = self.root / "outside/image.tar"
        outside.parent.mkdir()
        outside.write_bytes(b"outside")
        with self.assertRaises(subject.shared.ImageAuditFailure):
            subject.archive_paths(self.root, outside)
        linked_directory = self.archive.parent.parent / "12345678-1234-4234-8234-000000000002"
        linked_directory.mkdir()
        linked = linked_directory / "image.tar"
        try:
            linked.symlink_to(self.archive)
        except OSError:
            linked = None
        if linked is not None:
            with self.assertRaises(subject.shared.ImageAuditFailure):
                subject.archive_paths(self.root, linked)

        # A fresh output location is needed because failed reports are retained for diagnosis.
        self.paths.report.unlink(missing_ok=True)
        self.paths.summary.unlink(missing_ok=True)
        with self.assertRaises(subject.shared.ImageAuditFailure):
            self.run_audit(FakeRunner(self.paths, self.ids["config"], mutate_archive=True))

    def test_database_mutation_after_scan_fails_closed(self):
        with self.assertRaisesRegex(subject.shared.ImageAuditFailure, "imagen o DB"):
            self.run_audit(FakeRunner(self.paths, self.ids["config"], mutate_database=True))


if __name__ == "__main__":
    unittest.main()
