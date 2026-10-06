import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

if __package__:
    from . import production_backup as subject
else:
    import production_backup as subject


def media_tar() -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo("./recipes/e2e.txt")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"demo"))
    return stream.getvalue()


class FakeDocker:
    def __init__(self, *, fail_dump=False, runtime_env=None):
        self.calls = []
        self.fail_dump = fail_dump
        self.runtime_env = runtime_env or {}

    def run(self, argv, *, data=None):
        self.calls.append((list(argv), data))
        joined = " ".join(argv)
        if " ps -q db" in joined:
            return b"db-id\n"
        if " ps -q web" in joined:
            return b"web-id\n"
        if argv[:2] == ["docker", "inspect"]:
            service = "db" if argv[-1] == "db-id" else "web"
            return json.dumps([{
                "Image": "sha256:" + ("d" if service == "db" else "e") * 64,
                "State": {"Running": True},
                "Config": {"Env": [f"{key}={value}" for key, value in self.runtime_env.items()], "Labels": {"com.docker.compose.project": "cuaderno-prod",
                                       "com.docker.compose.service": service}},
            }]).encode()
        if "pg_stat_activity" in joined:
            return b"0\n"
        if " pg_dump " in joined:
            if self.fail_dump:
                raise RuntimeError("dump failed")
            return b"DUMP"
        if argv[:2] == ["docker", "cp"]:
            return media_tar()
        if "pg_tables" in joined:
            return b"demo\n"
        if data is not None and b"content_md5" in data:
            return b'{"table":"demo","rows":2,"content_md5":"0123456789abcdef0123456789abcdef"}\n'
        if "django_migrations" in joined:
            return b"cuaderno:0016:test\n"
        if "SHOW server_version" in joined:
            return b"16.9\n"
        if argv[:3] == ["git", "-C", str(subject.ROOT)]:
            return ("a" * 40 + "\n").encode()
        return b""


class ProductionBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = self.root / "production.env"
        self.env.write_text("CUADERNO_DB_PASSWORD=never-print-this\n", encoding="utf-8")
        if os.name != "nt":
            self.env.chmod(0o600)
            self.root.chmod(0o700)

    def test_creates_new_hashed_bundle_and_restarts_previous_web(self):
        docker = FakeDocker()
        bundle = subject.create_backup(self.env, self.root, boundary=docker)
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "cuaderno-production-backup")
        self.assertEqual(manifest["database"]["tables"]["demo"]["rows"], 2)
        self.assertEqual(manifest["media"]["recipes/e2e.txt"]["bytes"], 4)
        commands = [" ".join(call[0]) for call in docker.calls]
        self.assertLess(next(i for i, row in enumerate(commands) if " stop web" in row),
                        next(i for i, row in enumerate(commands) if " pg_dump " in row))
        self.assertTrue(any(" up -d --no-deps web" in row for row in commands))
        self.assertNotIn("never-print-this", "\n".join(commands))
        self.assertFalse((bundle / "environment.env").exists())
        self.assertFalse(manifest["configuration"]["secrets_recorded"])

    def test_records_only_safe_runtime_prefix_and_database_configuration(self):
        docker = FakeDocker(runtime_env={
            "SCRIPT_NAME": "/cuaderno-cocina", "STATIC_URL": "/cuaderno-cocina/static/",
            "MEDIA_URL": "/cuaderno-cocina/media/", "SESSION_COOKIE_NAME": "cuaderno_sessionid",
            "CSRF_COOKIE_NAME": "cuaderno_csrftoken", "LANGUAGE_COOKIE_NAME": "cuaderno_language",
            "SESSION_COOKIE_PATH": "/cuaderno-cocina/", "CSRF_COOKIE_PATH": "/cuaderno-cocina/",
            "LANGUAGE_COOKIE_PATH": "/cuaderno-cocina/", "POSTGRES_DB": "cuaderno_prod",
            "POSTGRES_USER": "cuaderno_prod", "SECRET_KEY": "never-record-runtime-secret",
        })
        bundle = subject.create_backup(self.env, self.root, boundary=docker)
        manifest_text = (bundle / "manifest.json").read_text()
        manifest = json.loads(manifest_text)
        runtime = manifest["configuration"]["runtime_environment"]
        self.assertEqual(runtime["SCRIPT_NAME"], "/cuaderno-cocina")
        self.assertEqual(runtime["MEDIA_URL"], "/cuaderno-cocina/media/")
        self.assertEqual(runtime["POSTGRES_DB"], "cuaderno_prod")
        self.assertNotIn("SECRET_KEY", runtime)
        self.assertNotIn("never-record-runtime-secret", manifest_text)

    def test_rejects_unsafe_runtime_paths_before_stopping_writers_or_creating_bundle(self):
        for values in ({"SCRIPT_NAME": "/../other"}, {"SCRIPT_NAME": "/kitchen", "MEDIA_URL": "https://other.example/media/"},
                       {"SCRIPT_NAME": "/kitchen", "SESSION_COOKIE_PATH": "/"}):
            docker = FakeDocker(runtime_env=values)
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "configuraci|prefijo|cookie|media"):
                subject.create_backup(self.env, self.root, boundary=docker)
            self.assertFalse(any("stop" in argv for argv, _ in docker.calls))
            self.assertEqual(list(self.root.iterdir()), [self.env])

    def test_optional_env_copy_is_private_hashed_and_not_in_manifest(self):
        bundle = subject.create_backup(self.env, self.root, boundary=FakeDocker(), include_env=True)
        copied = bundle / "environment.env"
        self.assertEqual(copied.read_bytes(), self.env.read_bytes())
        if os.name != "nt":
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
        manifest_text = (bundle / "manifest.json").read_text()
        manifest = json.loads(manifest_text)
        self.assertEqual(manifest["files"]["environment.env"], subject.sha256(copied))
        self.assertTrue(manifest["configuration"]["secrets_recorded"])
        self.assertNotIn("never-print-this", manifest_text)

    def test_reproduces_valid_database_names_in_backup_commands(self):
        docker = FakeDocker(runtime_env={"POSTGRES_DB": "saved_db", "POSTGRES_USER": "saved_user"})
        bundle = subject.create_backup(self.env, self.root, boundary=docker)
        manifest = json.loads((bundle / "manifest.json").read_text())
        self.assertEqual(manifest["configuration"]["runtime_environment"]["POSTGRES_DB"], "saved_db")
        dump = next(argv for argv, _ in docker.calls if "pg_dump" in argv)
        self.assertEqual(dump[dump.index("-U") + 1], "saved_user")
        self.assertEqual(dump[dump.index("-d") + 1], "saved_db")

    def test_cookie_names_cannot_collide(self):
        with self.assertRaisesRegex(ValueError, "cookie"):
            subject.runtime_configuration({"SESSION_COOKIE_NAME": "same", "CSRF_COOKIE_NAME": "same"})

    def test_dump_failure_still_restarts_web_and_never_overwrites(self):
        docker = FakeDocker(fail_dump=True)
        with self.assertRaisesRegex(RuntimeError, "dump failed"):
            subject.create_backup(self.env, self.root, boundary=docker)
        self.assertTrue(any(" up -d --no-deps web" in " ".join(argv) for argv, _ in docker.calls))

    def test_env_file_permissions_are_fail_closed_on_posix(self):
        if os.name == "nt":
            self.assertEqual(subject.validate_private_file(self.env), self.env.resolve())
            return
        self.env.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            subject.validate_private_file(self.env)


if __name__ == "__main__":
    unittest.main()
