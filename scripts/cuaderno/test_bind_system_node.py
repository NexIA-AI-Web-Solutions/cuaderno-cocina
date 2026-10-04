"""Tests for the exact nodejs-wheel-to-Alpine runtime binding."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import bind_system_node as subject
else:
    import bind_system_node as subject


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "nodejs_wheel"
        (self.root / "bin").mkdir(parents=True)
        self.executable = self.root / "executable.py"; self.executable.write_text("# wrapper fixture\n")
        self.executable_sha = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        self.license = self.base / subject.WHEEL_LICENSE_RELATIVE
        self.license.parent.mkdir(parents=True); self.license.write_text("MIT fixture\n")
        self.license_sha = hashlib.sha256(self.license.read_bytes()).hexdigest()
        self.node = self.root / "bin/node"
        self.node.write_bytes(b"wheel node fixture")
        self.wheel_sha = hashlib.sha256(self.node.read_bytes()).hexdigest()
        self.system = self.base / "system-node"
        self.system.write_bytes(b"alpine node fixture")
        self.system_sha = hashlib.sha256(self.system.read_bytes()).hexdigest()
        self.zlib_real = self.base / "libz.so.1.3.2"
        self.zlib_real.write_bytes(b"patched zlib fixture")
        self.zlib_link = self.base / "libz.so.1"
        self.zlib_link.symlink_to(self.zlib_real)
        runtime_files = {"/bin/busybox": "1" * 64, "/usr/bin/ssl_client": "2" * 64,
                         subject.ZLIB_REAL_PATH: hashlib.sha256(self.zlib_real.read_bytes()).hexdigest()}
        self.provenance = self.base / "SECURITY.alpine-backports.json"
        self.provenance.write_text(json.dumps({
            "schema_version": 1, "alpine_aports_commit": "x", "alpine_image": "x",
            "architecture": "x86_64", "source_date_epoch": 1, "source_inputs_sha256": "3" * 64,
            "packages": {}, "patches": {}, "runtime_files": runtime_files, "verified": True,
        }))
        self.commands = []

    def close(self): self.temp.cleanup()

    def runner(self, command, **_kwargs):
        self.commands.append(command)
        if command[-1] == "--version": output = subject.SYSTEM_NODE_VERSION
        elif command[:3] == ["apk", "info", "--who-owns"]:
            output = f"{self.system} is owned by {subject.ALPINE_PACKAGE}"
        elif command[:3] == ["apk", "info", "-e"]: output = subject.ALPINE_PACKAGE
        elif command[0] == "scanelf" and "-r" in command: output = ""
        elif command[0] == "scanelf": output = "libcrypto.so.3,libz.so.1,libc.musl-x86_64.so.1 " + str(self.system)
        elif command[0] == "ldd": output = f"\tlibz.so.1 => {self.zlib_link} (0x1234)"
        else: output = '[5,"' + hashlib.sha256(b"cuaderno").hexdigest() + '","1.3.2"]'
        return SimpleNamespace(returncode=0, stdout=output + "\n", stderr="")

    def bind(self, **kwargs):
        env = patch.dict(os.environ, {"CUADERNO_NODE_BIND_TEST": "1"})
        hashes = patch.multiple(subject, WHEEL_NODE_SHA256=self.wheel_sha,
                                SYSTEM_NODE_SHA256=self.system_sha,
                                SYSTEM_NODE=self.system,
                                WHEEL_EXECUTABLE_SHA256=self.executable_sha,
                                WHEEL_LICENSE_SHA256=self.license_sha)
        with env, hashes:
            return subject.bind_system_node(
                self.root, wheel_version=kwargs.pop("wheel_version", subject.WHEEL_VERSION),
                system_node=self.system, runner=kwargs.pop("runner", self.runner),
                wheel_license=self.license,
                alpine_provenance=self.provenance, zlib_link=self.zlib_link,
                wrapper_probe=kwargs.pop("wrapper_probe", lambda _root: None), **kwargs)


class BindSystemNodeTests(unittest.TestCase):
    def fixture(self):
        value = Fixture(); self.addCleanup(value.close); return value

    def test_exact_binary_is_atomically_bound_and_idempotent(self):
        fixture = self.fixture()
        probed = []
        def wrapper(root):
            probed.append(root)
            self.assertTrue((root / "bin/node").is_symlink())
            self.assertEqual((root / "bin/node").resolve(), fixture.system.resolve())
        result = fixture.bind(wrapper_probe=wrapper)
        self.assertEqual(result["status"], "bound")
        self.assertTrue(fixture.node.is_symlink())
        self.assertEqual(fixture.node.resolve(), fixture.system.resolve())
        self.assertEqual(result["runtime"]["zlib_version"], "1.3.2")
        self.assertIn("libz.so.1", result["runtime"]["needed"])
        self.assertEqual(fixture.bind(wrapper_probe=wrapper)["status"], "already-bound")
        self.assertEqual(probed, [fixture.root.resolve(), fixture.root.resolve()])
        self.assertTrue(fixture.license.is_file())

    def test_unknown_wheel_version_hash_and_system_target_fail_before_mutation(self):
        fixture = self.fixture(); original = fixture.node.read_bytes()
        with self.assertRaises(subject.BindFailure): fixture.bind(wheel_version="24.21.0")
        self.assertEqual(fixture.node.read_bytes(), original)
        fixture.node.write_bytes(b"unknown wheel")
        with self.assertRaisesRegex(subject.BindFailure, "original"): fixture.bind()
        self.assertFalse(fixture.node.is_symlink())
        fixture = self.fixture(); fixture.system.write_bytes(b"unknown Alpine node")
        with self.assertRaisesRegex(subject.BindFailure, "SHA-256"): fixture.bind()
        self.assertFalse(fixture.node.is_symlink())

    def test_symlinked_roots_binary_or_system_node_are_refused(self):
        fixture = self.fixture(); outside = fixture.base / "outside"; outside.mkdir()
        linked_root = fixture.base / "linked-parent/nodejs_wheel"
        linked_root.parent.mkdir(); linked_root.symlink_to(fixture.root, target_is_directory=True)
        with patch.dict(os.environ, {"CUADERNO_NODE_BIND_TEST": "1"}), self.assertRaises(subject.BindFailure):
            subject.bind_system_node(linked_root, wheel_version=subject.WHEEL_VERSION,
                                     system_node=fixture.system, runner=fixture.runner)
        fixture = self.fixture(); other = fixture.base / "other-node"; other.write_bytes(b"other")
        fixture.node.unlink(); fixture.node.symlink_to(other)
        with self.assertRaises(subject.BindFailure): fixture.bind()
        fixture = self.fixture(); target = fixture.base / "target"; target.write_bytes(b"x")
        fixture.system.unlink(); fixture.system.symlink_to(target)
        with self.assertRaisesRegex(subject.BindFailure, "regular"): fixture.bind()

    def test_missing_shared_zlib_or_bad_node_behavior_is_refused(self):
        for bad in ("scanelf", "rpath", "runtime", "zlib"):
            fixture = self.fixture()
            if bad == "zlib": fixture.zlib_real.write_bytes(b"tampered")
            def runner(command, **kwargs):
                result = fixture.runner(command, **kwargs)
                if bad == "scanelf" and command[0] == "scanelf" and "-n" in command:
                    result.stdout = "libcrypto.so.3\n"
                if bad == "rpath" and command[0] == "scanelf" and "-r" in command:
                    result.stdout = "/private/node/lib\n"
                if bad == "runtime" and "--eval" in command: result.stdout = "[4,\"bad\",\"\"]\n"
                return result
            with self.subTest(bad=bad), self.assertRaises(subject.BindFailure):
                fixture.bind(runner=runner)
            self.assertFalse(fixture.node.is_symlink())

    def test_replace_or_wrapper_failure_restores_original_bytes(self):
        for failure in ("replace", "wrapper"):
            fixture = self.fixture(); original = fixture.node.read_bytes()
            kwargs = {}
            if failure == "wrapper":
                kwargs["wrapper_probe"] = lambda _root: (_ for _ in ()).throw(subject.BindFailure("wrapper"))
                context = patch("os.replace", wraps=os.replace)
            else:
                real_replace = os.replace; calls = [0]
                def replace(source, destination):
                    calls[0] += 1
                    if calls[0] == 1: raise OSError("write failed")
                    return real_replace(source, destination)
                context = patch("os.replace", side_effect=replace)
            with self.subTest(failure=failure), context, self.assertRaises(subject.BindFailure):
                fixture.bind(**kwargs)
            self.assertFalse(fixture.node.is_symlink())
            self.assertEqual(fixture.node.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
