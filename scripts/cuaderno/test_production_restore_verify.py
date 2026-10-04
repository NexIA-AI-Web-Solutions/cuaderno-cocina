import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

if __package__:
    from . import production_restore_verify as subject
    from .production_backup import media_manifest, sha256
else:
    import production_restore_verify as subject
    from production_backup import media_manifest, sha256


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

    def exists(self, kind, name):
        self.calls.append((["exists", kind, name], None))
        return False

    def run(self, argv, *, data=None):
        self.calls.append((list(argv), data))
        joined = " ".join(argv)
        if "docker run -d" in joined and "-web" in joined:
            env_path = Path(argv[argv.index("--env-file") + 1])
            self.runtime_environment = env_path.read_text(encoding="utf-8")
        if self.fail_readiness and "urllib.request.urlopen" in joined:
            raise RuntimeError("synthetic readiness timeout")
        if "docker image inspect" in joined:
            return ("sha256:" + "a" * 64 + "\n").encode()
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
        report = subject.verify(self.bundle, boundary=docker, runtime_image="candidate")
        self.assertIn("CSRF_TRUSTED_ORIGINS=https://127.0.0.1\n", docker.runtime_environment)
        commands = [" ".join(argv) for argv, _ in docker.calls]
        readiness = next(row for row in commands if "urllib.request.urlopen" in row)
        self.assertIn("range(120)", readiness)
        self.assertIn("time.sleep(2)", readiness)
        self.assertEqual(report["runtime_candidate"]["image_id"], "sha256:" + "a" * 64)

    def test_failed_readiness_preserves_isolated_resources(self):
        docker = FakeRestore(archive_bytes(), fail_readiness=True)
        with self.assertRaisesRegex(RuntimeError, "synthetic readiness timeout"):
            subject.verify(self.bundle, boundary=docker, runtime_image="candidate")
        commands = [" ".join(argv) for argv, _ in docker.calls]
        self.assertFalse(any("docker rm" in row or "network rm" in row or "volume rm" in row
                             for row in commands))


if __name__ == "__main__":
    unittest.main()
