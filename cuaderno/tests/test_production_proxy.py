"""Exercise the real deployment settings and Django HTTPS interpretation."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings

from recipes import settings as base


def production_profile(**overrides):
    values = dict(DEBUG=False, SECRET_KEY="synthetic-deployment-test-" * 3,
                  ALLOWED_HOSTS=["cocina.example.invalid"],
                  CSRF_TRUSTED_ORIGINS=["https://cocina.example.invalid"])
    values.update(overrides)
    location = Path(base.__file__).with_name("cuaderno_production_settings.py")
    spec = importlib.util.spec_from_file_location("production_settings_test", location)
    profile = importlib.util.module_from_spec(spec)
    with patch.multiple(base, **values):
        spec.loader.exec_module(profile)
    return profile


class ProductionProxyTests(SimpleTestCase):
    def test_prefixed_internal_readiness_is_exactly_exempt_from_https_redirect(self):
        profile = production_profile(SCRIPT_NAME='/cuaderno-cocina', FORCE_SCRIPT_NAME='/cuaderno-cocina')
        names = ('SECURE_SSL_REDIRECT', 'SECURE_PROXY_SSL_HEADER', 'SECURE_REDIRECT_EXEMPT')
        with override_settings(**{name: getattr(profile, name) for name in names}):
            middleware = SecurityMiddleware(lambda _request: HttpResponse('{"ready":true}', content_type='application/json'))
            for path, expected in (('/cuaderno-cocina/health/ready/', 200),
                                   ('/health/ready/', 301), ('/cuaderno-cocina/health/ready/extra', 301),
                                   ('/cuaderno-cocina/api/cuaderno/edition/', 301)):
                with self.subTest(path=path):
                    response = middleware(RequestFactory().get(path))
                    self.assertEqual(response.status_code, expected)
                    if expected == 200:
                        self.assertEqual(response.content, b'{"ready":true}')

    def test_production_does_not_start_external_connectors_even_when_enabled_in_base(self):
        profile = production_profile(DISABLE_EXTERNAL_CONNECTORS=False)
        self.assertTrue(profile.DISABLE_EXTERNAL_CONNECTORS)
        self.assertFalse(profile.SPACE_AI_ENABLED)

    def test_https_proxy_does_not_redirect_again_but_plain_http_does(self):
        profile = production_profile()
        self.assertEqual(profile.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertTrue(profile.SESSION_COOKIE_SECURE)
        self.assertTrue(profile.CSRF_COOKIE_SECURE)
        names = ("ALLOWED_HOSTS", "SECURE_SSL_REDIRECT", "SECURE_PROXY_SSL_HEADER", "SECURE_REDIRECT_EXEMPT")
        with override_settings(**{name: getattr(profile, name) for name in names}):
            middleware = SecurityMiddleware(lambda _request: HttpResponse("ok"))
            for forwarded, expected in (("https", 200), ("http", 301), (None, 301)):
                kwargs = {"HTTP_X_FORWARDED_PROTO": forwarded} if forwarded else {}
                request = RequestFactory().get("/api/cuaderno/edition/", HTTP_HOST="cocina.example.invalid", **kwargs)
                self.assertEqual(middleware(request).status_code, expected)
            health = RequestFactory().get("/health/ready/", HTTP_HOST="cocina.example.invalid")
            self.assertEqual(middleware(health).status_code, 200)

    def test_unsafe_deployment_configuration_fails_at_import(self):
        for overrides in ({"DEBUG": True}, {"SECRET_KEY": "short"}, {"ALLOWED_HOSTS": ["*"]},
                          {"CSRF_TRUSTED_ORIGINS": ["http://cocina.example.invalid"]}):
            with self.subTest(overrides=list(overrides)):
                with self.assertRaises(ImproperlyConfigured):
                    production_profile(**overrides)
