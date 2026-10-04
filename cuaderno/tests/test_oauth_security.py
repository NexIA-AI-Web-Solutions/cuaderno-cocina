"""Exercise the installed OAuth library rather than a version-only assertion."""

from urllib.parse import urlencode

from django.test import SimpleTestCase
from oauthlib.oauth2 import RequestValidator
from oauthlib.oauth2.rfc6749.endpoints.revocation import RevocationEndpoint


class RejectingClientValidator(RequestValidator):
    def client_authentication_required(self, request, *args, **kwargs):
        return True

    def authenticate_client(self, request, *args, **kwargs):
        return False


class OAuthSecurityTests(SimpleTestCase):
    def test_revocation_cannot_reflect_javascript_even_with_legacy_jsonp_option(self):
        with self.assertRaises(TypeError):
            RevocationEndpoint(RejectingClientValidator(), enable_jsonp=True)
        endpoint = RevocationEndpoint(RejectingClientValidator())
        callback = "window.location='https://attacker.invalid/'//"
        headers, body, status = endpoint.create_revocation_response(
            "https://oauth.example.invalid/revoke", http_method="POST",
            body=urlencode({"token": "synthetic-token", "callback": callback}),
        )
        self.assertEqual(status, 401)
        self.assertNotIn(callback, body)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertJSONEqual(body, {"error": "invalid_client"})
