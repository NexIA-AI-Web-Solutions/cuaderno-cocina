"""Tests for the byte-pinned CPython poplib runtime backport."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import patch_runtime_security as subject
else:
    import patch_runtime_security as subject


VULNERABLE = b'''import re
import sys

CRLF = b'\\r\\n'

class POP3:
    encoding = 'UTF-8'

    def _putline(self, line):
        if self._debugging > 1: print('*put*', repr(line))
        sys.audit("poplib.putline", self, line)
        self.sock.sendall(line + CRLF)

    def _putcmd(self, line):
        if self._debugging: print('*cmd*', repr(line))
        line = bytes(line, self.encoding)
        self._putline(line)
'''


class Transport:
    def __init__(self):
        self.sent = []

    def sendall(self, value):
        self.sent.append(value)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeSecurityPatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / "poplib.py"
        self.path.write_bytes(VULNERABLE)
        self.original_hash = hashlib.sha256(VULNERABLE).hexdigest()
        self.patched_bytes = VULNERABLE.replace(subject.ORIGINAL_BLOCK, subject.PATCHED_BLOCK)
        self.patched_hash = hashlib.sha256(self.patched_bytes).hexdigest()
        self.hashes = patch.multiple(
            subject, ORIGINAL_SHA256=self.original_hash, PATCHED_SHA256=self.patched_hash,
        )

    def test_real_pop3_transport_allows_safe_command_and_blocks_crlf_injection(self):
        vulnerable = load(self.path, "synthetic_poplib_before")
        before = vulnerable.POP3.__new__(vulnerable.POP3)
        before._debugging, before.sock = 0, Transport()
        before._putcmd("USER attacker\r\nDELE 1")
        self.assertEqual(before.sock.sent, [b"USER attacker\r\nDELE 1\r\n"])

        mode = stat.S_IMODE(self.path.stat().st_mode)
        with self.hashes:
            result = subject.patch_poplib(self.path, python_version=(3, 13, 16))
        self.assertEqual(result["status"], "patched")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), mode)
        patched = load(self.path, "synthetic_poplib_after")
        client = patched.POP3.__new__(patched.POP3)
        client._debugging, client.sock = 0, Transport()
        client._putcmd("USER safe")
        self.assertEqual(client.sock.sent, [b"USER safe\r\n"])
        for malicious in ("USER attacker\r\nDELE 1", "USER nul\x00suffix", "USER del\x7f"):
            with self.subTest(malicious=repr(malicious)), self.assertRaisesRegex(
                    ValueError, "Control characters"):
                client._putcmd(malicious)
        self.assertEqual(client.sock.sent, [b"USER safe\r\n"])

    def test_patch_is_idempotent_and_preserves_the_exact_patched_bytes(self):
        with self.hashes:
            first = subject.patch_poplib(self.path, python_version=(3, 13, 16))
            first_bytes = self.path.read_bytes()
            second = subject.patch_poplib(self.path, python_version=(3, 13, 16))
        self.assertEqual(first["status"], "patched")
        self.assertEqual(second["status"], "already-patched")
        self.assertEqual(first_bytes, self.patched_bytes)
        self.assertEqual(self.path.read_bytes(), first_bytes)

    def test_unknown_bytes_wrong_version_relative_path_and_links_fail_closed(self):
        original = self.path.read_bytes()
        with self.hashes, self.assertRaisesRegex(subject.PatchFailure, "3.13.16"):
            subject.patch_poplib(self.path, python_version=(3, 13, 17))
        with self.hashes, self.assertRaisesRegex(subject.PatchFailure, "CPython"):
            subject.patch_poplib(
                self.path, python_version=(3, 13, 16), python_implementation="PyPy",
            )
        self.assertEqual(self.path.read_bytes(), original)
        with self.hashes, self.assertRaisesRegex(subject.PatchFailure, "absoluta"):
            subject.patch_poplib(Path("poplib.py"), python_version=(3, 13, 16))
        self.path.write_bytes(b"unknown poplib source")
        with self.hashes, self.assertRaisesRegex(subject.PatchFailure, "bytes originales"):
            subject.patch_poplib(self.path, python_version=(3, 13, 16))
        self.assertEqual(self.path.read_bytes(), b"unknown poplib source")
        target = self.path.parent / "target.py"
        target.write_bytes(VULNERABLE)
        self.path.unlink()
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.hashes, self.assertRaisesRegex(subject.PatchFailure, "enlace"):
            subject.patch_poplib(self.path, python_version=(3, 13, 16))

    def test_production_pins_match_verified_cpython_sources_and_trace_license(self):
        self.assertEqual(subject.PYTHON_VERSION, (3, 13, 16))
        self.assertEqual(subject.ORIGINAL_SHA256,
                         "527e714523264093910a0a0b1a55c6583f952835c89061537fc40ad98c347056")
        self.assertEqual(subject.PATCHED_SHA256,
                         "a6ffff188814b56d95b043c31d9e0dfee51ac6d6e92afe74ab070cb6136b076f")
        self.assertIn(subject.UPSTREAM_COMMIT, subject.PATCHED_URL)
        self.assertIn(subject.UPSTREAM_COMMIT, subject.COMMIT_URL)
        self.assertIn("v3.13.16", subject.ORIGINAL_URL)
        self.assertIn("LICENSE", subject.LICENSE_URL)


if __name__ == "__main__":
    unittest.main()
