"""Native Django state and runtime models must agree on theme display labels."""
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.template import Context, engines

from cookbook.models import Space, Storage, UserPreference


class BrandingMigrationStateTests(SimpleTestCase):
    def test_storage_state_matches_runtime_without_changing_connector_codes(self):
        state_apps = MigrationLoader(None).project_state().apps
        state_field = state_apps.get_model('cookbook', 'Storage')._meta.get_field('method')
        runtime_field = Storage._meta.get_field('method')
        self.assertEqual(list(state_field.choices), list(runtime_field.choices))
        self.assertEqual(state_field.default, runtime_field.default)
        self.assertEqual(state_field.max_length, runtime_field.max_length)
        self.assertEqual(set(dict(runtime_field.choices)), {'DB', 'NEXTCLOUD', 'LOCAL'})

    def test_system_template_displays_product_for_original_runtime_metadata(self):
        template = engines['django'].engine.get_template('system.html')
        for original_name in ['Tandoor ', 'Tandoor', 'Tandoor Recipes']:
            with self.subTest(original_name=original_name):
                rendered = template.render(Context({'version_info': [{
                    'name': original_name, 'branch': 'main', 'version': 'abc123',
                    'website': 'https://github.com/TandoorRecipes/recipes',
                    'commit_link': 'https://github.com/TandoorRecipes/recipes/commit/abc123',
                }]}))
                self.assertNotIn('Tandoor', rendered)
                self.assertIn('Cuaderno Cocina (main)', rendered)
                self.assertNotIn('github.com/TandoorRecipes', rendered)

    def test_theme_state_matches_runtime_without_changing_stored_codes(self):
        state_apps = MigrationLoader(None).project_state().apps
        for model, field_name in [(Space, 'space_theme'), (UserPreference, 'theme')]:
            with self.subTest(model=model.__name__):
                state_field = state_apps.get_model('cookbook', model.__name__)._meta.get_field(field_name)
                runtime_field = model._meta.get_field(field_name)
                self.assertEqual(list(state_field.choices), list(runtime_field.choices))
                self.assertEqual(state_field.default, runtime_field.default)
                self.assertEqual(state_field.max_length, runtime_field.max_length)
                self.assertEqual(dict(runtime_field.choices)['TANDOOR'], 'Cuaderno Cocina')
                self.assertEqual(set(dict(runtime_field.choices)) - {'BLANK'},
                                 {'TANDOOR', 'BOOTSTRAP', 'DARKLY', 'FLATLY', 'SUPERHERO', 'TANDOOR_DARK'})
