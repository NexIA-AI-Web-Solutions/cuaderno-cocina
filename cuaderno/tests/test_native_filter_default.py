from django.contrib.auth import get_user_model
from django.apps import apps
from django.db import connection
from django.test import TestCase
from django_scopes import scopes_disabled

from cookbook.models import CustomFilter, Space
import importlib


class NativeFilterDefaultTests(TestCase):
    def test_saved_filter_without_type_persists_the_recipe_choice(self):
        with scopes_disabled():
            space = Space.objects.create(name="Native default")
            user = get_user_model().objects.create_user(username="native-filter-default")
            saved = CustomFilter.objects.create(
                space=space, created_by=user, name="Filtro guardado", search="{}",
            )
            saved.refresh_from_db()
        self.assertEqual(saved.type, CustomFilter.RECIPE)

    def test_upgrade_repairs_tuple_defaults_and_preserves_search_and_explicit_types(self):
        migration = importlib.import_module("cookbook.migrations.0244_customfilter_recipe_default")
        with scopes_disabled():
            space = Space.objects.create(name="Historical defaults")
            user = get_user_model().objects.create_user(username="historical-filter-default")
            rows = [CustomFilter.objects.create(
                space=space, created_by=user, name=f"Filter {index}", search='{"private":true}', type=value,
            ) for index, value in enumerate([
                "('RECIPE', 'Recipe')", "('RECIPE', 'Receta')", "FOOD", "KEYWORD", "(unknown)",
            ])]
            with connection.schema_editor() as editor:
                migration.repair_tuple_defaults(apps, editor)
            for row, expected in zip(rows, ["RECIPE", "RECIPE", "FOOD", "KEYWORD", "(unknown)"]):
                row.refresh_from_db()
                self.assertEqual(row.type, expected)
                self.assertEqual(row.search, '{"private":true}')
                self.assertEqual(row.created_by_id, user.pk)
                self.assertEqual(row.space_id, space.pk)
