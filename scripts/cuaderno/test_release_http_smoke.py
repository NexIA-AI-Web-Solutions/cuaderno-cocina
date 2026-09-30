import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from urllib.request import Request

from scripts.cuaderno.release_http_smoke import (
    BASE_URL,
    NoRedirectHandler,
    SmokeFailure,
    _csrf_from_html,
    _decimal,
    _guard_base_url,
    _guard_environment,
    _safe_url,
    _validated_redirect,
)


class ReleaseHttpSmokeUnitTests(unittest.TestCase):
    def test_environment_requires_local_or_test_and_demo_password(self):
        with patch.dict(os.environ, {"CUADERNO_ENV": "local", "CUADERNO_DEMO_PASSWORD": "demo-password-123"}, clear=True):
            self.assertEqual(_guard_environment(), "demo-password-123")
        for environment in ("production", "development", ""):
            with self.subTest(environment=environment), patch.dict(
                os.environ,
                {"CUADERNO_ENV": environment, "CUADERNO_DEMO_PASSWORD": "demo-password-123"},
                clear=True,
            ):
                with self.assertRaises(SmokeFailure):
                    _guard_environment()
        with patch.dict(os.environ, {"CUADERNO_ENV": "test"}, clear=True):
            with self.assertRaises(SmokeFailure):
                _guard_environment()

    def test_url_guard_is_exact_loopback_and_paths_cannot_escape(self):
        _guard_base_url(BASE_URL)
        for base in ("http://localhost:18081", "http://127.0.0.1:8080", "https://127.0.0.1:18081", "http://127.0.0.1:18081/path"):
            with self.subTest(base=base):
                with self.assertRaises(SmokeFailure):
                    _guard_base_url(base)
        self.assertEqual(_safe_url("/health/ready/"), f"{BASE_URL}/health/ready/")
        for path in ("health/ready/", "//example.test/steal", "http://example.test/steal", "https://127.0.0.1:18081/"):
            with self.subTest(path=path):
                with self.assertRaises(SmokeFailure):
                    _safe_url(path)

    def test_redirect_location_must_remain_on_the_exact_loopback_origin(self):
        self.assertEqual(_validated_redirect("/"), f"{BASE_URL}/")
        self.assertEqual(_validated_redirect(f"{BASE_URL}/accounts/login/"), f"{BASE_URL}/accounts/login/")
        for location in (
            "//example.test/steal",
            "https://127.0.0.1:18081/",
            "http://127.0.0.1:8080/",
            "http://user:password@127.0.0.1:18081/",
            "",
        ):
            with self.subTest(location=location):
                with self.assertRaises(SmokeFailure):
                    _validated_redirect(location)

    def test_redirect_handler_never_builds_a_followup_request_for_307_or_308(self):
        handler = NoRedirectHandler()
        original = Request(
            f"{BASE_URL}/accounts/login/",
            data=b"login=demo-profesional&password=not-a-real-secret",
            method="POST",
        )
        for status in (307, 308):
            with self.subTest(status=status):
                self.assertIsNone(
                    handler.redirect_request(
                        original,
                        None,
                        status,
                        "redirect",
                        {"Location": "//example.test/steal"},
                        "http://example.test/steal",
                    )
                )

    def test_csrf_parser_requires_a_real_hidden_form_field(self):
        html = '<form><input type="hidden" name="csrfmiddlewaretoken" value="synthetic-token"></form>'
        self.assertEqual(_csrf_from_html(html), "synthetic-token")
        with self.assertRaises(SmokeFailure):
            _csrf_from_html('<input name="other" value="not-csrf">')

    def test_decimal_contract_does_not_accept_float_or_non_finite_values(self):
        self.assertEqual(_decimal("0.6400", "cost"), Decimal("0.6400"))
        for value in (0.64, None, "NaN", "Infinity", [], {}):
            with self.subTest(value=value):
                with self.assertRaises(SmokeFailure):
                    _decimal(value, "cost")


if __name__ == "__main__":
    unittest.main()
