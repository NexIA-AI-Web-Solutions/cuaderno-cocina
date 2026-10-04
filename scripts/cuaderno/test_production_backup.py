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
    def __init__(self, *, fail_dump=False):
        self.calls = []
        self.fail_dump = fail_dump

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
                "Config": {"Labels": {"com.docker.compose.project": "cuaderno-prod",
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
