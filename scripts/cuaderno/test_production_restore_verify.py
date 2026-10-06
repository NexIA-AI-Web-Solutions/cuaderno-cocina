import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

if __package__:
    from . import production_restore_verify as subject
    from .production_backup import media_manifest, sha256
    from .test_production_config_check import FakePostgresClients
else:
    import production_restore_verify as subject
    from production_backup import media_manifest, sha256
    from test_production_config_check import FakePostgresClients


def archive_bytes() -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo("./recipes/e2e.txt")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"demo"))
    return stream.getvalue()


class FakeRestore:
    def __init__(self, restored_media, *, fail_readiness=False):
        self.calls = []
        self.restored_media = restored_media
        self.fail_readiness = fail_readiness
        self.runtime_environment = None
        self.image_id = "sha256:" + "a" * 64
        self.foreign_ownership = False

    def exists(self, kind, name):
        self.calls.append((["exists", kind, name], None))
        return False

    def run(self, argv, *, data=None):
        self.calls.append((list(argv), data))
        joined = " ".join(argv)
        if argv[:2] == ["docker", "inspect"]:
            name = argv[-1]
            return json.dumps([{
                "Id": ("e" if name.endswith("-web") else "d") * 64, "Name": "/" + name,
                "Config": {"Labels": {"io.cuaderno.restore": "foreign" if self.foreign_ownership else name.rsplit("-", 1)[0]}},
            }]).encode()
        if "docker run -d" in joined and "-web" in joined:
            env_path = Path(argv[argv.index("--env-file") + 1])
            self.runtime_environment = env_path.read_text(encoding="utf-8")
        if self.fail_readiness and "urllib.request.urlopen" in joined:
            raise RuntimeError("synthetic readiness timeout")
        if "docker image inspect" in joined:
            return (self.image_id + "\n").encode()
        if "pg_tables" in joined:
            return b"demo\n"
        if data is not None and b"content_md5" in data:
            return b'{"table":"demo","rows":2,"content_md5":"0123456789abcdef0123456789abcdef"}\n'
        if "django_migrations" in joined:
            return b"cuaderno:0016:test\n"
        if "SHOW server_version" in joined:
            return b"16.9\n"
        if " tar -c " in f" {joined} ":
            return self.restored_media
        return b"created\n"


class RestoreVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        (self.bundle / "database.dump").write_bytes(b"DUMP")
        (self.bundle / "media.tar").write_bytes(archive_bytes())
        database = {
            "tables": {"demo": {"rows": 2, "content_md5": "0123456789abcdef0123456789abcdef"}},
            "migrations": ["cuaderno:0016:test"], "postgres_version": "16.9",
        }
        manifest = {
            "schema_version": 2, "kind": "cuaderno-production-backup", "compose_project": "cuaderno-prod",
            "database": database, "media": media_manifest(self.bundle / "media.tar"),
            "files": {name: sha256(self.bundle / name) for name in ("database.dump", "media.tar")},
            "source_commit": "a" * 40,
            "runtime": {"web_image_id": "sha256:" + "a" * 64},
        }
        (self.bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_restores_only_to_new_internal_unpublished_namespace(self):
        docker = FakeRestore(archive_bytes())
        report = subject.verify(self.bundle, boundary=docker)
        self.assertTrue(report["passed"])
        self.assertTrue(report["namespace"].startswith("cuaderno-restore-"))
        self.assertTrue(report["network_internal"])
        self.assertFalse(report["published_ports"])
        commands = [" ".join(argv) for argv, _ in docker.calls if argv[0] != "exists"]
        self.assertTrue(any("network create --internal" in row for row in commands))
        self.assertFalse(any(
            "cuaderno-prod" in row or " compose " in f" {row} " or " down " in f" {row} "
            for row in commands
        ))
        self.assertTrue(any("-media:/media" in row for row in commands))

    def test_rejects_tampering_before_any_docker_call(self):
        (self.bundle / "database.dump").write_bytes(b"TAMPERED")
        docker = FakeRestore(archive_bytes())
        with self.assertRaisesRegex(ValueError, "Hash incorrecto"):
            subject.verify(self.bundle, boundary=docker)
        self.assertEqual(docker.calls, [])

    def test_runtime_uses_https_csrf_and_bounded_readiness_poll(self):
        docker = FakeRestore(archive_bytes())
        report = subject.verify(self.bundle, boundary=docker, runtime_image="sha256:" + "a" * 64)
        self.assertIn("CSRF_TRUSTED_ORIGINS=https://127.0.0.1\n", docker.runtime_environment)
        commands = [" ".join(argv) for argv, _ in docker.calls]
        readiness = next(row for row in commands if "urllib.request.urlopen" in row)
        self.assertIn("range(120)", readiness)
        self.assertIn("time.sleep(2)", readiness)
        self.assertEqual(report["runtime_candidate"]["image_id"], "sha256:" + "a" * 64)

    def edit_manifest(self, **updates):
        path = self.bundle / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest.update(updates)
        path.write_text(json.dumps(manifest))

    def test_rejects_other_or_mutable_runtime_image_before_namespace_mutation(self):
        for supplied in ("", "candidate:latest", "sha256:" + "b" * 64):
            docker = FakeRestore(archive_bytes())
            with self.subTest(supplied=supplied), self.assertRaisesRegex(ValueError, "Image|imagen"):
                subject.verify(self.bundle, boundary=docker, runtime_image=supplied)
            self.assertFalse(any("create" in argv or "run" in argv for argv, _ in docker.calls))

    def test_restores_allowlisted_prefix_and_database_config_with_bounded_containers(self):
        config = {
            "SCRIPT_NAME": "/kitchen", "STATIC_URL": "/kitchen/static/", "MEDIA_URL": "/kitchen/media/",
            "SESSION_COOKIE_NAME": "cuaderno_sessionid", "CSRF_COOKIE_NAME": "cuaderno_csrftoken",
            "LANGUAGE_COOKIE_NAME": "cuaderno_language", "SESSION_COOKIE_PATH": "/kitchen/",
            "CSRF_COOKIE_PATH": "/kitchen/", "LANGUAGE_COOKIE_PATH": "/kitchen/",
            "DB_ENGINE": "django.db.backends.postgresql", "POSTGRES_DB": "cuaderno_saved", "POSTGRES_USER": "cuaderno_saved",
        }
        self.edit_manifest(schema_version=3, configuration={"runtime_environment": config})
        docker = FakeRestore(archive_bytes())
        report = subject.verify(self.bundle, boundary=docker, runtime_image="sha256:" + "a" * 64)
        for key, value in config.items():
            self.assertIn(f"{key}={value}\n", docker.runtime_environment)
        self.assertIn("GUNICORN_WORKERS=1\n", docker.runtime_environment)
        self.assertIn("GUNICORN_THREADS=2\n", docker.runtime_environment)
        runs = [argv for argv, _ in docker.calls if argv[:3] == ["docker", "run", "-d"]]
        self.assertEqual(len(runs), 2)
        for argv, memory in zip(runs, ("512m", "768m")):
            self.assertEqual(argv[argv.index("--memory") + 1], memory)
            self.assertEqual(argv[argv.index("--cpus") + 1], "0.5")
            self.assertIn("--restart=no", argv)
            self.assertNotIn("-p", argv)
            self.assertNotIn("-P", argv)
        self.assertTrue(report["containers_stopped"])

    def test_rejects_unsafe_manifest_configuration_before_docker_resources(self):
        for values in ({"SCRIPT_NAME": "/../other"}, {"SCRIPT_NAME": "/kitchen", "MEDIA_URL": "https://other.example/media/"},
                       {"POSTGRES_DB": "unsafe\nname"}, {"SECRET_KEY": "untrusted-secret"}):
            self.edit_manifest(schema_version=3, configuration={"runtime_environment": values})
            docker = FakeRestore(archive_bytes())
            with self.subTest(values=values), self.assertRaises(ValueError):
                subject.verify(self.bundle, boundary=docker)
            self.assertEqual(docker.calls, [])

    def test_accepts_v2_without_runtime_metadata_for_database_only_verification(self):
        path = self.bundle / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest.pop("runtime")
        path.write_text(json.dumps(manifest))
        self.assertTrue(subject.verify(self.bundle, boundary=FakeRestore(archive_bytes()))["passed"])

    def test_checks_optional_protected_env_hash_before_docker_calls(self):
        copied = self.bundle / "environment.env"
        copied.write_text("SECRET_KEY=never-print-this\n")
        copied.chmod(0o600)
        path = self.bundle / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"]["environment.env"] = sha256(copied)
        manifest["schema_version"] = 3
        manifest["configuration"] = {"runtime_environment": {}, "secrets_recorded": True}
        path.write_text(json.dumps(manifest))
        subject.trusted_bundle(self.bundle)
        copied.write_text("SECRET_KEY=tampered\n")
        docker = FakeRestore(archive_bytes())
        with self.assertRaisesRegex(ValueError, "Hash incorrecto"):
            subject.verify(self.bundle, boundary=docker)
        self.assertEqual(docker.calls, [])

    def test_stop_checks_namespace_ownership_and_uses_inspected_ids(self):
        docker = FakeRestore(archive_bytes())
        report = subject.verify(self.bundle, boundary=docker)
        stops = [argv for argv, _ in docker.calls if argv[:2] == ["docker", "stop"]]
        self.assertEqual(stops, [["docker", "stop", "d" * 64]])
        self.assertTrue(report["containers_stopped"])
        docker = FakeRestore(archive_bytes())
        docker.foreign_ownership = True
        with self.assertRaisesRegex(ValueError, "propiedad"):
            subject.verify(self.bundle, boundary=docker)
        self.assertFalse(any(argv[:2] == ["docker", "stop"] for argv, _ in docker.calls))

    def test_local_image_inspection_mismatch_fails_before_creating_resources(self):
        docker = FakeRestore(archive_bytes())
        docker.image_id = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ValueError, "ImageID"):
            subject.verify(self.bundle, boundary=docker, runtime_image="sha256:" + "a" * 64)
        self.assertEqual(len(docker.calls), 1)
        self.assertEqual(docker.calls[0][0][:3], ["docker", "image", "inspect"])

    def test_unprotected_env_copy_is_rejected_before_resource_mutation(self):
        copied = self.bundle / "environment.env"
        copied.write_text("SECRET_KEY=private\n")
        copied.chmod(0o644)
        path = self.bundle / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"]["environment.env"] = sha256(copied)
        manifest["configuration"] = {"secrets_recorded": True}
        path.write_text(json.dumps(manifest))
        docker = FakeRestore(archive_bytes())
        with self.assertRaisesRegex(ValueError, "0600"):
            subject.verify(self.bundle, boundary=docker)
        self.assertEqual(docker.calls, [])

    def test_missing_backup_image_metadata_cannot_claim_same_image_runtime_restore(self):
        self.edit_manifest(runtime={})
        docker = FakeRestore(archive_bytes())
        with self.assertRaisesRegex(ValueError, "ImageID"):
            subject.verify(self.bundle, boundary=docker, runtime_image="sha256:" + "a" * 64)
        self.assertEqual(docker.calls, [])

    def test_failed_readiness_preserves_isolated_resources(self):
        docker = FakeRestore(archive_bytes(), fail_readiness=True)
        with self.assertRaisesRegex(RuntimeError, "synthetic readiness timeout"):
            subject.verify(self.bundle, boundary=docker, runtime_image="sha256:" + "a" * 64)
        commands = [" ".join(argv) for argv, _ in docker.calls]
        self.assertFalse(any("docker rm" in row or "network rm" in row or "volume rm" in row
                             for row in commands))
        self.assertEqual(sum(row.startswith("docker stop ") for row in commands), 2)

    def database_probe_boundary(self, **kwargs):
        clients = FakePostgresClients(**kwargs)
        self.addCleanup(clients.cleanup)

        class DatabaseProbeRestore(FakeRestore):
            def run(self, argv, *, data=None):
                if argv[:2] == ["docker", "exec"] and "sh" in argv and "pg_isready" in argv[-1]:
                    self.calls.append((list(argv), data))
                    result = clients.run(argv[-1])
                    if result.returncode:
                        # The real boundary retains the failure; never expose client stderr here.
                        raise RuntimeError("synthetic database readiness failure")
                    return result.stdout
                if "pg_restore" in argv:
                    self.polls_before_restore = int((clients.root / "polls").read_text())
                return super().run(argv, data=data)

        return DatabaseProbeRestore(archive_bytes()), clients

    def test_waits_for_final_tcp_before_restoring_once(self):
        docker, clients = self.database_probe_boundary(tcp_at=2)
        self.assertTrue(subject.verify(self.bundle, boundary=docker)["passed"])
        self.assertEqual(docker.polls_before_restore, 2)
        self.assertEqual(sum("pg_restore" in argv for argv, _ in docker.calls), 1)
        self.assertEqual(sum(row.startswith("sql:") for row in clients.rows()), 1)
        self.assertEqual(clients.rows().count("sleep:1"), 1)

    def test_database_missing_or_failed_sql_prevents_restore(self):
        docker, clients = self.database_probe_boundary(sql_exit=1)
        with self.assertRaisesRegex(RuntimeError, "database readiness failure"):
            subject.verify(self.bundle, boundary=docker)
        self.assertFalse(any("pg_restore" in argv for argv, _ in docker.calls))
        self.assertEqual(sum(row.startswith("ready:") for row in clients.rows()), 120)
        self.assertEqual(clients.rows().count("sleep:1"), 120)

    def test_tcp_never_ready_does_not_query_or_restore(self):
        docker, clients = self.database_probe_boundary(tcp_at=121)
        with self.assertRaises(RuntimeError):
            subject.verify(self.bundle, boundary=docker)
        self.assertFalse(any("pg_restore" in argv for argv, _ in docker.calls))
        self.assertFalse(any(row.startswith("sql:") for row in clients.rows()))
        self.assertEqual(sum(row.startswith("ready:") for row in clients.rows()), 120)

    def test_wrong_sql_scalar_does_not_restore(self):
        docker, _ = self.database_probe_boundary(sql_result="0")
        with self.assertRaises(RuntimeError):
            subject.verify(self.bundle, boundary=docker)
        self.assertFalse(any("pg_restore" in argv for argv, _ in docker.calls))

    def test_allowlisted_saved_database_is_used_by_both_readiness_clients(self):
        self.edit_manifest(schema_version=3, configuration={"runtime_environment": {
            "POSTGRES_DB": "cuaderno_saved", "POSTGRES_USER": "cuaderno_saved_user"}})
        docker, clients = self.database_probe_boundary()
        subject.verify(self.bundle, boundary=docker)
        for prefix in ("ready:", "sql:"):
            row = next(row for row in clients.rows() if row.startswith(prefix))
            self.assertIn("-U cuaderno_saved_user -d cuaderno_saved", row)

    def test_database_probe_keeps_the_existing_poll_and_per_probe_budget(self):
        docker = FakeRestore(archive_bytes())
        subject.verify(self.bundle, boundary=docker)
        command = next(argv[-1] for argv, _ in docker.calls if "pg_isready" in argv[-1])
        self.assertIn("seq 1 120", command)
        self.assertIn("sleep 1", command)
        self.assertIn("-t 1", command)
        self.assertIn("timeout 2 psql", command)
        self.assertIn("PGCONNECT_TIMEOUT=2", command)
        self.assertIn("statement_timeout=1000", command)

    def test_probe_refuses_shell_syntax_or_overlong_identifiers(self):
        for invalid in ("name; exit 0", "name\nother", "-option", "a" * 64):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                subject.database_ready_probe(invalid, "cuaderno_prod")
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                subject.database_ready_probe("cuaderno_prod", invalid)


if __name__ == "__main__":
    unittest.main()
