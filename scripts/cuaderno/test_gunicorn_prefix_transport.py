"""Characterize the actual launcher environment and source prefix settings without a DB."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


from scripts.cuaderno.gunicorn_prefix_transport import launch_environment

def prefix_settings(root: Path, values: dict[str, str]) -> dict:
    names = {'SCRIPT_NAME', 'FORCE_SCRIPT_NAME', 'STATIC_URL', 'MEDIA_URL', 'SESSION_COOKIE_PATH',
             'CSRF_COOKIE_PATH', 'LANGUAGE_COOKIE_PATH'}
    tree = ast.parse((root / 'recipes/settings.py').read_text())
    selected = [node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    namespace = {'os': os}
    with patch.dict(os.environ, values, clear=True):
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'actual-prefix-settings', 'exec'), namespace)
    return {name: namespace[name] for name in names}


class GunicornPrefixTransportTests(unittest.TestCase):
    def test_launcher_separates_gunicorn_transport_from_django_prefix(self):
        result = launch_environment(ROOT, {'SCRIPT_NAME': '/cuaderno-cocina'})
        self.assertNotIn('SCRIPT_NAME', result)
        self.assertEqual(result['CUADERNO_APP_SCRIPT_NAME'], '/cuaderno-cocina')
        settings = prefix_settings(ROOT, result)
        self.assertEqual(settings['SCRIPT_NAME'], '/cuaderno-cocina')
        self.assertEqual(settings['FORCE_SCRIPT_NAME'], '/cuaderno-cocina')
        self.assertEqual(settings['STATIC_URL'], '/cuaderno-cocina/static/')
        self.assertEqual(settings['MEDIA_URL'], '/cuaderno-cocina/media/')
        for key in ('SESSION_COOKIE_PATH', 'CSRF_COOKIE_PATH', 'LANGUAGE_COOKIE_PATH'):
            self.assertEqual(settings[key], '/cuaderno-cocina/')

    def test_root_launcher_retains_empty_logical_prefix(self):
        result = launch_environment(ROOT, {})
        self.assertNotIn('SCRIPT_NAME', result)
        self.assertEqual(result['CUADERNO_APP_SCRIPT_NAME'], '')
        settings = prefix_settings(ROOT, result)
        self.assertIsNone(settings['FORCE_SCRIPT_NAME'])
        self.assertEqual(settings['STATIC_URL'], '/static/')
        self.assertEqual(settings['MEDIA_URL'], '/media/')

    def test_settings_keep_legacy_prefix_for_management_commands(self):
        self.assertEqual(prefix_settings(ROOT, {'SCRIPT_NAME': '/legacy'})['SCRIPT_NAME'], '/legacy')

    def test_explicit_application_prefix_wins_consistently(self):
        result = launch_environment(ROOT, {'SCRIPT_NAME': '/legacy', 'CUADERNO_APP_SCRIPT_NAME': '/configured'})
        self.assertNotIn('SCRIPT_NAME', result)
        self.assertEqual(result['CUADERNO_APP_SCRIPT_NAME'], '/configured')
        self.assertEqual(prefix_settings(ROOT, result)['FORCE_SCRIPT_NAME'], '/configured')
        self.assertEqual(prefix_settings(ROOT, {'SCRIPT_NAME': '/legacy', 'CUADERNO_APP_SCRIPT_NAME': ''})['SCRIPT_NAME'], '')

    def test_migration_and_collectstatic_precede_gunicorn_unsetting(self):
        source = (ROOT / 'boot.sh').read_text()
        self.assertLess(source.index('python manage.py migrate'), source.index('unset SCRIPT_NAME'))
        self.assertLess(source.index('python manage.py collectstatic'), source.index('unset SCRIPT_NAME'))


if __name__ == '__main__':
    unittest.main()
