#!/usr/bin/env python3
"""Regression tests for the pinned oauthlib 3.3.1 PKCE backport."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.metadata
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("patch_oauthlib.py")
SPEC = importlib.util.spec_from_file_location("cuaderno_patch_oauthlib", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"No se puede cargar {SCRIPT}")
patch_oauthlib = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch_oauthlib)


class OAuthlibPatchTests(unittest.TestCase):
    RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    RFC_S256_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    @classmethod
    def setUpClass(cls):
        if importlib.metadata.version("oauthlib") != patch_oauthlib.TARGET_VERSION:
            raise RuntimeError("Estas pruebas deben ejecutarse en el venv aislado con oauthlib 3.3.1.")
        cls.first_run = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        if cls.first_run.returncode != 0:
            raise RuntimeError(cls.first_run.stderr or cls.first_run.stdout)

        from oauthlib.oauth2.rfc6749.grant_types import authorization_code

        cls.authorization_code = authorization_code

    def test_plain_and_s256_use_compare_digest(self):
        module = self.authorization_code
        with mock.patch.object(module.hmac, "compare_digest", wraps=hmac.compare_digest) as compare:
            self.assertTrue(module.code_challenge_method_plain(self.RFC_VERIFIER, self.RFC_VERIFIER))
            self.assertFalse(module.code_challenge_method_plain(self.RFC_VERIFIER, self.RFC_VERIFIER + "x"))
            self.assertTrue(module.code_challenge_method_s256(self.RFC_VERIFIER, self.RFC_S256_CHALLENGE))
            self.assertFalse(module.code_challenge_method_s256(self.RFC_VERIFIER, "wrong"))
        self.assertEqual(compare.call_count, 4)

    def test_rfc_7636_oracle_and_registry_point_to_patched_functions(self):
        module = self.authorization_code
        oracle = base64.urlsafe_b64encode(
            hashlib.sha256(self.RFC_VERIFIER.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(oracle, self.RFC_S256_CHALLENGE)
        registry = module.AuthorizationCodeGrant._code_challenge_methods
        self.assertIs(registry["plain"], module.code_challenge_method_plain)
        self.assertIs(registry["S256"], module.code_challenge_method_s256)
        self.assertTrue(registry["plain"](self.RFC_VERIFIER, self.RFC_VERIFIER))
        self.assertTrue(registry["S256"](self.RFC_VERIFIER, oracle))

    def test_patch_is_idempotent_and_reports_provenance(self):
        second = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("status=already-patched", second.stdout)
        self.assertIn(f"original_sha256={patch_oauthlib.ORIGINAL_SHA256}", second.stdout)
        self.assertIn(f"post_sha256={patch_oauthlib.PATCHED_SHA256}", second.stdout)
        self.assertIn(patch_oauthlib.ADVISORY_URL, second.stdout)

    def test_fail_closed_for_another_version_or_source(self):
        with self.assertRaises(patch_oauthlib.PatchError):
            patch_oauthlib.require_supported_version("3.3.2")
        with self.assertRaises(patch_oauthlib.PatchError):
            patch_oauthlib.build_patched_source(b"not the upstream wheel bytes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
