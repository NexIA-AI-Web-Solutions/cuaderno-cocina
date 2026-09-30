from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.cuaderno import delivery_rollback


IMAGE_ID = "sha256:" + "7" * 64
SUFFIX = "abcdef123456"


class FakeDocker:
    def __init__(self, functional: dict, *, inspected_image: str = IMAGE_ID,
                 runtime_image: str = IMAGE_ID, duplicate_marker: bool = False,
                 runtime_exists: bool = False, runtime_name: str | None = None,
                 runtime_state: dict | None = None, on_start=None):
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.functional = functional
        self.inspected_image = inspected_image
        self.runtime_image = runtime_image
        self.duplicate_marker = duplicate_marker
        self.runtime_exists = runtime_exists
        self.runtime_name = runtime_name
        self.runtime_state = runtime_state
        self.on_start = on_start

    def container_exists(self, name):
        self.calls.append((["docker", "container", "inspect", name], None))
        return self.runtime_exists

    def run(self, argv, *, data=None):
        command = list(argv)
        self.calls.append((command, data))
        if command[:3] == ["docker", "image", "inspect"]:
            return (self.inspected_image + "\n").encode()
        if command[:3] == ["docker", "inspect", "cuaderno-release-db"]:
            return json.dumps([{
                "Name": "/cuaderno-release-db",
                "State": {"Running": True, "Paused": False},
                "Config": {"Env": ["POSTGRES_PASSWORD=isolated-db-password"]},
                "NetworkSettings": {"Networks": {"cuaderno-release": {}}},
            }]).encode()
        if command[:2] == ["docker", "inspect"] and command[2].endswith("-web"):
            return json.dumps([{
                "Name": self.runtime_name or f"/{command[2]}",
                "Image": self.runtime_image,
                "State": self.runtime_state or {
                    "Status": "exited", "ExitCode": 0, "OOMKilled": False, "Error": "",
                },
            }]).encode()
        if "SELECT tablename FROM pg_tables" in (data or b"").decode(errors="ignore"):
            return b""
        if any("pg_sequences" in part for part in command):
            return b""
        if command[:3] == ["docker", "start", "-a"]:
            if self.on_start:
                self.on_start()
            marker = "CUADERNO_SMOKE=" + json.dumps(self.functional, sort_keys=True) + "\n"
            return (marker * (2 if self.duplicate_marker else 1)).encode()
        return b""


class RollbackFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        smoke = self.root / "scripts/cuaderno/restore_smoke.py"
        smoke.parent.mkdir(parents=True)
        smoke.write_text("# synthetic read-only smoke boundary\n", encoding="utf-8")
        self.bundle = self.root / "data/cuaderno/backups/old-release"
        self.bundle.mkdir(parents=True)
        self.dump = b"synthetic-custom-format-dump"
        (self.bundle / "database.dump").write_bytes(self.dump)
        with tarfile.open(self.bundle / "media.tar", "w") as archive:
            content = b"synthetic-media"
            info = tarfile.TarInfo("recipes/demo.txt")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        self.functional = {"passed": True, "sha256": "a" * 64, "accounts": 3}
        smoke_hash = hashlib.sha256(smoke.read_bytes()).hexdigest()
        checkout_files = {"scripts/cuaderno/restore_smoke.py": smoke_hash}
        self.manifest = {
            "schema_version": 1,
            "source_target": "release",
            "source_commit": "b" * 40,
            "image_id": IMAGE_ID,
            "database": {"tables": {}, "sequences": []},
            "functional": self.functional,
            "checkout_source": {
                "description": "Synthetic checkout source.",
                "files": checkout_files,
                "sha256": hashlib.sha256(
                    json.dumps(checkout_files, sort_keys=True).encode(),
                ).hexdigest(),
            },
            "media": {
                "recipes/demo.txt": {
                    "bytes": len(b"synthetic-media"),
                    "sha256": hashlib.sha256(b"synthetic-media").hexdigest(),
                },
            },
            "files": {
                "database.dump": hashlib.sha256(self.dump).hexdigest(),
                "media.tar": hashlib.sha256((self.bundle / "media.tar").read_bytes()).hexdigest(),
            },
            "write_pause_seconds": 0.25,
        }
        self.write_manifest()

    def write_manifest(self):
        (self.bundle / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8",
        )

    def local_environment(self):
        return patch.dict(os.environ, {
            "CUADERNO_ENV": "test",
            "CUADERNO_DEMO_PASSWORD": "synthetic-login-password",
        }, clear=True)


class RollbackPreflightTests(RollbackFixture):
    def test_rejects_bundle_outside_backup_root_and_symlink_before_docker(self):
        docker = FakeDocker(self.functional)
        outside = self.root / "outside"
        outside.mkdir()
        for source in (outside, self.root / "data/cuaderno/backups/link"):
            if source.name == "link":
                try:
                    source.symlink_to(self.bundle, target_is_directory=True)
                except OSError:
                    continue
            with self.subTest(source=source), self.local_environment():
                with self.assertRaises(ValueError):
                    delivery_rollback.preflight(source, docker, root=self.root)
        self.assertEqual(docker.calls, [])

    def test_media_extraction_revalidates_members_and_destination(self):
        destination = self.root / "destination"
        destination.mkdir()
        for name, kind in (
            ("../escape", tarfile.REGTYPE),
            ("/absolute", tarfile.REGTYPE),
            ("folder\\windows", tarfile.REGTYPE),
            ("C:/drive", tarfile.REGTYPE),
            ("link", tarfile.SYMTYPE),
        ):
            archive_path = self.root / f"unsafe-{len(list(self.root.glob('unsafe-*')))}.tar"
            with tarfile.open(archive_path, "w") as archive:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = 1 if kind == tarfile.REGTYPE else 0
                archive.addfile(info, io.BytesIO(b"x") if info.size else None)
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                delivery_rollback._extract_media(archive_path, destination)

        duplicate = self.root / "duplicate.tar"
        with tarfile.open(duplicate, "w") as archive:
            for name in ("same", "./same"):
                info = tarfile.TarInfo(name)
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
        with self.assertRaises(ValueError):
            delivery_rollback._extract_media(duplicate, destination)

        root_directory = self.root / "root-directory.tar"
        with tarfile.open(root_directory, "w") as archive:
            root_info = tarfile.TarInfo(".")
            root_info.type = tarfile.DIRTYPE
            archive.addfile(root_info)
            file_info = tarfile.TarInfo("./safe.txt")
            file_info.size = 1
            archive.addfile(file_info, io.BytesIO(b"x"))
        clean_destination = self.root / "root-directory-destination"
        clean_destination.mkdir()
        delivery_rollback._extract_media(root_directory, clean_destination)
        self.assertEqual((clean_destination / "safe.txt").read_bytes(), b"x")

        root_file = self.root / "root-file.tar"
        with tarfile.open(root_file, "w") as archive:
            root_info = tarfile.TarInfo(".")
            root_info.size = 1
            archive.addfile(root_info, io.BytesIO(b"x"))
        with self.assertRaises(ValueError):
            delivery_rollback._extract_media(root_file, clean_destination)

    def test_checkout_source_must_register_the_exact_restore_smoke(self):
        docker = FakeDocker(self.functional)
        files = self.manifest["checkout_source"]["files"]
        files["scripts/cuaderno/restore_smoke.py"] = "0" * 64
        self.manifest["checkout_source"]["sha256"] = hashlib.sha256(
            json.dumps(files, sort_keys=True).encode(),
        ).hexdigest()
        self.write_manifest()
        with self.local_environment(), self.assertRaisesRegex(ValueError, "restore_smoke"):
            delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])

    def test_hash_or_image_mismatch_aborts_before_any_mutation(self):
        for corrupt, docker in (
            ("hash", FakeDocker(self.functional)),
            ("image", FakeDocker(self.functional, inspected_image="sha256:" + "8" * 64)),
        ):
            with self.subTest(corrupt=corrupt):
                if corrupt == "hash":
                    self.manifest["files"]["database.dump"] = "0" * 64
                    self.write_manifest()
                with self.local_environment():
                    with self.assertRaises(ValueError):
                        delivery_rollback.rollback(
                            self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
                        )
                commands = [command for command, _data in docker.calls]
                self.assertFalse(any("CREATE DATABASE" in " ".join(command) for command in commands))
                self.assertFalse((self.root / "data/cuaderno/rollbacks").exists())
                self.manifest["files"]["database.dump"] = hashlib.sha256(self.dump).hexdigest()
                self.write_manifest()

    def test_manifest_rejects_unsafe_image_and_media_members(self):
        docker = FakeDocker(self.functional)
        self.manifest["image_id"] = "cuaderno-cocina:latest"
        self.write_manifest()
        with self.local_environment():
            with self.assertRaises(ValueError):
                delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])

        self.manifest["image_id"] = IMAGE_ID
        with tarfile.open(self.bundle / "media.tar", "w") as archive:
            content = b"escape"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        self.manifest["files"]["media.tar"] = hashlib.sha256(
            (self.bundle / "media.tar").read_bytes(),
        ).hexdigest()
        self.write_manifest()
        with self.local_environment():
            with self.assertRaises(ValueError):
                delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])

    def test_resolved_backup_root_must_remain_inside_workspace(self):
        outside = self.root.parent / "outside-backups"
        with self.assertRaisesRegex(ValueError, "workspace"):
            delivery_rollback._validate_backup_root(self.root, outside)

    def test_missing_password_or_untrusted_smoke_aborts_before_docker_and_targets(self):
        docker = FakeDocker(self.functional)
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CUADERNO_DEMO_PASSWORD"):
                delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])

        smoke = self.root / "scripts/cuaderno/restore_smoke.py"
        original_is_symlink = Path.is_symlink
        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda candidate: candidate == smoke or original_is_symlink(candidate),
        ), self.local_environment():
            with self.assertRaisesRegex(ValueError, "restore_smoke"):
                delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])
        self.assertFalse((self.root / "data/cuaderno/rollbacks").exists())

    def test_duplicate_json_keys_and_invalid_schema_identity_fail_closed(self):
        docker = FakeDocker(self.functional)
        manifest_path = self.bundle / "manifest.json"
        manifest_path.write_text(
            '{"schema_version":1,"schema_version":1}', encoding="utf-8",
        )
        with self.local_environment():
            with self.assertRaisesRegex(ValueError, "duplicada"):
                delivery_rollback.preflight(self.bundle, docker, root=self.root)
        self.assertEqual(docker.calls, [])

        for field, value in (("schema_version", True), ("source_commit", ["not-a-hash"])):
            with self.subTest(field=field):
                self.manifest[field] = value
                self.write_manifest()
                with self.local_environment():
                    with self.assertRaises(ValueError):
                        delivery_rollback.preflight(self.bundle, docker, root=self.root)
                self.manifest[field] = 1 if field == "schema_version" else "b" * 40
        self.assertEqual(docker.calls, [])


class RollbackOrchestrationTests(RollbackFixture):
    def test_uses_exact_old_image_and_only_new_retained_targets(self):
        docker = FakeDocker(self.functional)
        with patch.dict(os.environ, {
            "CUADERNO_ENV": "test",
            "CUADERNO_DEMO_PASSWORD": "synthetic-login-password",
        }, clear=True):
            report = delivery_rollback.rollback(
                self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
            )

        database = f"cuaderno_restore_rollback_{SUFFIX}"
        runtime = f"cuaderno-rollback-{SUFFIX}-web"
        commands = [command for command, _data in docker.calls]
        self.assertTrue(report["passed"])
        self.assertEqual(report["target_database"], database)
        self.assertEqual(report["runtime_container"], runtime)
        self.assertEqual(report["image_id"], IMAGE_ID)
        image_verify = ["docker", "image", "inspect", IMAGE_ID, "--format", "{{.Id}}"]
        self.assertIn(image_verify, commands)
        create_runtime = next(command for command in commands if command[:2] == ["docker", "create"])
        self.assertIn(IMAGE_ID, create_runtime)
        self.assertNotIn("cuaderno-release-web", create_runtime)
        self.assertNotIn("cuaderno-g0-t002-web", create_runtime)
        self.assertIn(runtime, create_runtime)
        create_database = next(command for command in commands if "CREATE DATABASE" in " ".join(command))
        self.assertIn(database, " ".join(create_database))
        for command in commands:
            if "psql" in command or "pg_restore" in command:
                if "-d" in command:
                    self.assertIn(command[command.index("-d") + 1], {"postgres", database})
                    self.assertNotEqual(command[command.index("-d") + 1], "cuaderno_demo")
        self.assertTrue((self.root / report["target_media"] / "recipes/demo.txt").is_file())
        self.assertTrue((self.root / report["report_path"]).is_file())

    def test_functional_mismatch_retains_database_media_and_runtime_for_diagnosis(self):
        docker = FakeDocker({"payload_sha256": "different"})
        with patch.dict(os.environ, {
            "CUADERNO_ENV": "test",
            "CUADERNO_DEMO_PASSWORD": "synthetic-login-password",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "se conservan"):
                delivery_rollback.rollback(
                    self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
                )
        target = self.root / "data/cuaderno/rollbacks" / f"rollback-{SUFFIX}"
        self.assertTrue((target / "media/recipes/demo.txt").is_file())
        commands = [command for command, _data in docker.calls]
        self.assertFalse(any(command[:2] == ["docker", "rm"] for command in commands))
        self.assertFalse(any("DROP DATABASE" in " ".join(command) for command in commands))

    def test_runtime_collision_aborts_before_database_or_directory_mutation(self):
        docker = FakeDocker(self.functional, runtime_exists=True)
        with self.local_environment(), self.assertRaisesRegex(ValueError, "runtime"):
            delivery_rollback.rollback(
                self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
            )
        commands = [command for command, _data in docker.calls]
        self.assertFalse(any("CREATE DATABASE" in " ".join(command) for command in commands))
        self.assertFalse((self.root / "data/cuaderno/rollbacks").exists())

    def test_runtime_identity_exit_and_single_marker_are_required(self):
        for docker in (
            FakeDocker(self.functional, runtime_image="sha256:" + "8" * 64),
            FakeDocker(self.functional, duplicate_marker=True),
            FakeDocker(self.functional, runtime_name="/another-runtime"),
            FakeDocker(self.functional, runtime_state={
                "Status": "running", "ExitCode": 0, "OOMKilled": False, "Error": "",
            }),
            FakeDocker(self.functional, runtime_state={
                "Status": "exited", "ExitCode": True, "OOMKilled": False, "Error": "",
            }),
            FakeDocker(self.functional, runtime_state={
                "Status": "exited", "ExitCode": 0, "OOMKilled": True, "Error": "oom",
            }),
        ):
            with self.subTest(runtime_image=docker.runtime_image, duplicate=docker.duplicate_marker):
                with self.local_environment(), self.assertRaisesRegex(RuntimeError, "se conservan"):
                    delivery_rollback.rollback(
                        self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
                    )
                target = self.root / "data/cuaderno/rollbacks" / f"rollback-{SUFFIX}"
                self.assertTrue(target.exists())
                shutil.rmtree(target)

    def test_bundle_changed_during_smoke_fails_before_success_report(self):
        def mutate_dump():
            (self.bundle / "database.dump").write_bytes(b"changed-after-restore")

        docker = FakeDocker(self.functional, on_start=mutate_dump)
        with self.local_environment(), self.assertRaisesRegex(RuntimeError, "se conservan"):
            delivery_rollback.rollback(
                self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
            )
        report = self.root / "data/cuaderno/rollbacks" / f"rollback-{SUFFIX}/rollback-result.json"
        self.assertFalse(report.exists())

    def test_restore_smoke_changed_during_runtime_fails_before_success_report(self):
        def mutate_smoke():
            (self.root / "scripts/cuaderno/restore_smoke.py").write_text(
                "# changed after create\n", encoding="utf-8",
            )

        docker = FakeDocker(self.functional, on_start=mutate_smoke)
        with self.local_environment(), self.assertRaisesRegex(RuntimeError, "se conservan"):
            delivery_rollback.rollback(
                self.bundle, boundary=docker, root=self.root, suffix=SUFFIX,
            )
        report = self.root / "data/cuaderno/rollbacks" / f"rollback-{SUFFIX}/rollback-result.json"
        self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
