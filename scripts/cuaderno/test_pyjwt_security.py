"""Characterize the published PyJWT payload fix without network or app data.

GHSA-42vr-xj54-vc7v; upstream fix 5fde08a6cf906aa7698de2d6391d88b73006b17b.
These synthetic tokens never authorize a Cuaderno user or contact a JWKS URL.
"""

import base64
import unittest
from unittest.mock import patch

import jwt


def recursive_token():
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    return b".".join([
        encode(b'{"alg":"HS256","typ":"JWT","kid":"synthetic-only"}'),
        encode(b"[" * 20000 + b"]" * 20000),
        encode(b"not-a-valid-signature"),
    ]).decode("ascii")


class PyJwtSecurityTests(unittest.TestCase):
    def test_recursive_unverified_payload_has_documented_decode_error(self):
        with self.assertRaises(jwt.DecodeError):
            jwt.decode(recursive_token(), options={"verify_signature": False})

    def test_recursive_jwks_lookup_fails_before_any_network_request(self):
        client = jwt.PyJWKClient("https://synthetic.invalid/jwks")
        with patch.object(client, "fetch_data") as fetch:
            with self.assertRaises(jwt.DecodeError):
                client.get_signing_key_from_jwt(recursive_token())
        fetch.assert_not_called()

    def test_signed_synthetic_token_still_verifies(self):
        secret = "local-unit-test-key-at-least-thirty-two-bytes"
        token = jwt.encode({"sub": "synthetic", "aud": "cuaderno-test"}, secret, algorithm="HS256")
        self.assertEqual(
            jwt.decode(token, secret, algorithms=["HS256"], audience="cuaderno-test"),
            {"sub": "synthetic", "aud": "cuaderno-test"},
        )
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(token, secret + "-wrong", algorithms=["HS256"], audience="cuaderno-test")

    def test_ordinary_explicit_unverified_payload_is_unchanged(self):
        token = jwt.encode({"sub": "synthetic"}, "local-unit-test-key-at-least-thirty-two-bytes", algorithm="HS256")
        self.assertEqual(jwt.decode(token, options={"verify_signature": False}), {"sub": "synthetic"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
