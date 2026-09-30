"""Portable exports must always fit the limits enforced by their own importer."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Recipe, SearchFields, Space, Step, Unit, UnitConversion, UserSpace
from cuaderno.models import RecipeYield


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeExportLimitTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.source = Space.objects.create(name="Origen límites de intercambio")
            self.target = Space.objects.create(name="Destino límites de intercambio")
            group = Group.objects.get_or_create(name="user")[0]
            self.source_user = get_user_model().objects.create_user(
                username="exchange-limit-source", password="local-test"
            )
            self.target_user = get_user_model().objects.create_user(
                username="exchange-limit-target", password="local-test"
            )
            for user, space in ((self.source_user, self.source), (self.target_user, self.target)):
                membership = UserSpace.objects.create(user=user, space=space, active=True)
                membership.groups.add(group)

        self.source_client = APIClient()
        self.source_client.force_login(self.source_user)
        self.target_client = APIClient()
        self.target_client.force_login(self.target_user)

    def recipe(self, name, *, instruction="Preparar"):
        with scopes_disabled():
            recipe = Recipe.objects.create(
                name=name,
                servings=1,
                private=True,
                created_by=self.source_user,
                space=self.source,
            )
            step = Step.objects.create(space=self.source, instruction=instruction)
            recipe.steps.add(step)
        return recipe

    def assert_export_limit(self, response, *, private_name):
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response["Content-Type"].split(";", 1)[0], "application/json")
        payload = response.json()
        self.assertEqual(set(payload), {"export_limit"})
        self.assertIsInstance(payload["export_limit"], str)
        self.assertIn("export", payload["export_limit"].lower())
        self.assertNotIn(private_name, str(payload))

    def test_get_rejects_document_larger_than_import_two_megabyte_limit(self):
        private_name = "Receta privada que no debe filtrarse"
        self.recipe(private_name, instruction="x" * 2_000_001)

        response = self.source_client.get("/api/cuaderno/exchange/")

        self.assert_export_limit(response, private_name=private_name)

    def test_get_rejects_more_than_one_thousand_visible_recipes(self):
        private_name = "Receta masiva privada 0000"
        with scopes_disabled():
            Recipe.objects.bulk_create(
                [
                    Recipe(
                        name=f"Receta masiva privada {index:04d}",
                        servings=1,
                        private=True,
                        created_by=self.source_user,
                        space=self.source,
                    )
                    for index in range(1001)
                ],
                batch_size=500,
            )

        response = self.source_client.get("/api/cuaderno/exchange/")

        self.assert_export_limit(response, private_name=private_name)

    def test_get_rejects_oversized_reachable_native_conversion_catalog(self):
        """10,001 reachable conversions exceed the catalog limit (and may also exceed 2 MB)."""
        private_name = "Receta privada con catálogo grande"
        recipe = self.recipe(private_name)
        with scopes_disabled():
            unit = Unit.objects.create(name="unidad sintética", space=self.source)
            RecipeYield.objects.create(
                space=self.source,
                recipe=recipe,
                quantity=Decimal("1"),
                unit=unit,
                updated_by=self.source_user,
            )
            UnitConversion.objects.bulk_create(
                [
                    UnitConversion(
                        space=self.source,
                        food=None,
                        base_amount=Decimal(index + 1),
                        base_unit=unit,
                        converted_amount=Decimal(index + 2),
                        converted_unit=unit,
                        created_by=self.source_user,
                    )
                    for index in range(10_001)
                ],
                batch_size=500,
            )

        response = self.source_client.get("/api/cuaderno/exchange/")

        self.assert_export_limit(response, private_name=private_name)

    def test_small_get_document_is_accepted_by_preview_without_writes(self):
        self.recipe("Receta portable pequeña", instruction="Mezclar")

        exported = self.source_client.get("/api/cuaderno/exchange/")
        self.assertEqual(exported.status_code, 200)
        preview = self.target_client.post(
            "/api/cuaderno/exchange/?preview=1", exported.json(), format="json"
        )

        self.assertEqual(preview.status_code, 200, getattr(preview, "data", None))
        self.assertEqual(preview.data["writes"], 0)
        self.assertEqual(preview.data["count"], 1)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())

    def test_disconnected_conversion_candidates_are_bounded_before_materialization(self):
        """Fail closed rather than read an arbitrarily large disconnected graph."""
        private_name = "Receta sin conexión al catálogo enorme"
        self.recipe(private_name)
        with scopes_disabled():
            disconnected = Unit.objects.create(name="unidad desconectada", space=self.source)
            UnitConversion.objects.bulk_create([
                UnitConversion(
                    space=self.source, food=None, base_unit=disconnected,
                    converted_unit=disconnected, base_amount=Decimal(index + 1),
                    converted_amount=Decimal(index + 2), created_by=self.source_user,
                ) for index in range(12_000)
            ], batch_size=500)
        with CaptureQueriesContext(connection) as queries:
            response = self.source_client.get("/api/cuaderno/exchange/")
        self.assert_export_limit(response, private_name=private_name)
        candidate_queries = [query["sql"] for query in queries.captured_queries
                             if 'FROM "cookbook_unitconversion"' in query["sql"]]
        self.assertTrue(candidate_queries)
        self.assertTrue(all("LIMIT 10001" in query for query in candidate_queries), candidate_queries)
