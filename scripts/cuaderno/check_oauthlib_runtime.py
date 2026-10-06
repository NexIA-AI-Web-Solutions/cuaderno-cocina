"""Verify the upstream PKCE fix in the pinned OAuthlib production dependency."""

import base64
import hashlib
import hmac
import importlib.metadata
import unittest
from unittest.mock import patch

from oauthlib.oauth2.rfc6749.grant_types import authorization_code


class OAuthlibRuntimeTests(unittest.TestCase):
    VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    def test_production_version_is_pinned(self):
        self.assertEqual(importlib.metadata.version("oauthlib"), "4.0.0")

    def test_plain_and_s256_use_constant_time_comparison(self):
        with patch.object(authorization_code.hmac, "compare_digest", wraps=hmac.compare_digest) as compare:
            self.assertTrue(authorization_code.code_challenge_method_plain(self.VERIFIER, self.VERIFIER))
            self.assertFalse(authorization_code.code_challenge_method_plain(self.VERIFIER, self.VERIFIER + "x"))
            self.assertTrue(authorization_code.code_challenge_method_s256(self.VERIFIER, self.CHALLENGE))
            self.assertFalse(authorization_code.code_challenge_method_s256(self.VERIFIER, "wrong"))
        self.assertEqual(compare.call_count, 4)

    def test_rfc_7636_oracle_and_registry_use_the_verified_functions(self):
        oracle = base64.urlsafe_b64encode(hashlib.sha256(self.VERIFIER.encode("ascii")).digest())
        self.assertEqual(oracle.rstrip(b"=").decode("ascii"), self.CHALLENGE)
        registry = authorization_code.AuthorizationCodeGrant._code_challenge_methods
        self.assertIs(registry["plain"], authorization_code.code_challenge_method_plain)
        self.assertIs(registry["S256"], authorization_code.code_challenge_method_s256)
        self.assertTrue(registry["plain"](self.VERIFIER, self.VERIFIER))
        self.assertTrue(registry["S256"](self.VERIFIER, self.CHALLENGE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
