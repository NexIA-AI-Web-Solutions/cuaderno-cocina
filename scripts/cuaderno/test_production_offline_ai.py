"""Cold production-profile imports must configure LiteLLM before native API imports.

The base settings and LiteLLM import loaders are doubles. The real profile and
native API's actual ``import litellm`` node execute, with no network or Django
installation required. Django-backed profile regressions remain separate.
"""
import ast
import importlib.abc
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FLAG = 'LITELLM_LOCAL_MODEL_COST_MAP'


class ImportProbe(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.base_import_flags = []
        self.litellm_import_flags = []
        self.external_requests = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'recipes.settings', 'litellm'}:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if module.__name__ == 'recipes.settings':
            self.base_import_flags.append(os.environ.get(FLAG))
            values = dict(DEBUG=False, SECRET_KEY='synthetic-profile-key-' * 4,
                          ALLOWED_HOSTS=['cocina.example.invalid'],
                          CSRF_TRUSTED_ORIGINS=['https://cocina.example.invalid'],
                          FORCE_SCRIPT_NAME='/cuaderno-cocina', SPACE_AI_ENABLED=True,
                          DISABLE_EXTERNAL_CONNECTORS=False)
            module.__dict__.update(values)
        else:
            self.litellm_import_flags.append(os.environ.get(FLAG))
            if os.environ.get(FLAG) != 'True':
                self.external_requests.append('remote-model-cost-map')
                raise AssertionError('LiteLLM would request its remote model-cost map')
            module.model_cost_source = 'local'


def cold_profile(environment, *, import_native_api=False):
    recipes = ModuleType('recipes')
    recipes.__path__ = [str(ROOT / 'recipes')]
    django = ModuleType('django')
    django.__path__ = []
    core = ModuleType('django.core')
    core.__path__ = []
    exceptions = ModuleType('django.core.exceptions')
    exceptions.ImproperlyConfigured = type('ImproperlyConfigured', (RuntimeError,), {})
    modules = {'recipes': recipes, 'django': django, 'django.core': core,
               'django.core.exceptions': exceptions}
    probe = ImportProbe()
    with patch.dict(os.environ, environment, clear=True), patch.dict(sys.modules, modules):
        # Ensure neither a previous test nor Django initialization can hide import ordering.
        sys.modules.pop('recipes.settings', None)
        sys.modules.pop('litellm', None)
        with patch.object(sys, 'meta_path', [probe, *sys.meta_path]):
            location = ROOT / 'recipes/cuaderno_production_settings.py'
            spec = importlib.util.spec_from_file_location('cold_cuaderno_production_profile', location)
            profile = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(profile)
            if import_native_api:
                tree = ast.parse((ROOT / 'cookbook/views/api.py').read_text())
                imports = [node for node in tree.body if isinstance(node, ast.Import)
                           and any(alias.name == 'litellm' for alias in node.names)]
                if len(imports) != 1:
                    raise AssertionError('Expected the single native API LiteLLM import')
                exec(compile(ast.Module(body=imports, type_ignores=[]), 'native-api-litellm-import', 'exec'), {})
    return profile, probe


class ProductionOfflineAiTests(unittest.TestCase):
    def test_local_model_map_is_forced_before_base_settings_import(self):
        for environment in ({}, {FLAG: 'False'}, {FLAG: 'False', 'CUADERNO_ALLOW_AI': '1'}):
            with self.subTest(environment=environment):
                profile, probe = cold_profile(environment)
                self.assertEqual(probe.base_import_flags, ['True'])
                self.assertFalse(profile.SPACE_AI_ENABLED)
                self.assertTrue(profile.DISABLE_EXTERNAL_CONNECTORS)

    def test_native_api_litellm_import_observes_local_map_without_remote_attempt(self):
        profile, probe = cold_profile({FLAG: 'False'}, import_native_api=True)
        self.assertEqual(probe.litellm_import_flags, ['True'])
        self.assertEqual(probe.external_requests, [])
        self.assertFalse(profile.SPACE_AI_ENABLED)

    def test_repeated_cold_imports_restore_the_callers_environment(self):
        before = dict(os.environ)
        for _ in range(2):
            _, probe = cold_profile({FLAG: 'False'}, import_native_api=True)
            self.assertEqual(probe.base_import_flags, ['True'])
            self.assertEqual(probe.external_requests, [])
            self.assertEqual(dict(os.environ), before)


if __name__ == '__main__':
    unittest.main()
