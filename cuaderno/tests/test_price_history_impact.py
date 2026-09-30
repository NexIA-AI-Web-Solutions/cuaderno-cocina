"""Integration contract for dated price history and recipe-local price impact."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Household, Ingredient, Recipe, SearchFields, Space, Step, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion, RecipeYield, SpaceProfile
from cuaderno.services.costing import _load_costing_context


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PriceHistoryImpactTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.space = Space.objects.create(name="Historial sintético")
            self.household = Household.objects.create(space=self.space, name="Equipo sintético")
            self.owner = self._user("price-history-owner", self.household)
            self.other = self._user("price-history-other", self.household)
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])
            self.profile = SpaceProfile.objects.create(
                space=self.space,
                edition=SpaceProfile.INTEGRAL,
                currency="EUR",
                price_policy=SpaceProfile.NET,
            )
            self.litre = Unit.objects.create(space=self.space, name="L", base_unit="l")
            self.millilitre = Unit.objects.create(space=self.space, name="mL", base_unit="ml")
            self.oil = Food.add_root(space=self.space, name="Aceite sintético")
            self.package = PackageFormat.objects.create(
                space=self.space,
                food=self.oil,
                unit=self.litre,
                label="Garrafa 5 L",
                quantity=Decimal("5"),
                is_reference=True,
            )
            now = timezone.now()
            self.old_price = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("32"),
                valid_from=now - timedelta(days=2),
                note="Precio anterior",
                created_by=self.owner,
            )
            self.current_price = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("35"),
                valid_from=now - timedelta(days=1),
                note="Precio actual",
                created_by=self.owner,
            )
            self.future_price = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("99"),
                valid_from=now + timedelta(days=2),
                note="Precio futuro",
                created_by=self.owner,
            )
            self.recipe = self._recipe_with_oil("Aliño privado", private=True)

        self.client = self._client(self.owner)

    def _user(self, username, household):
        user = get_user_model().objects.create_user(username=username, password="synthetic-only")
        membership = UserSpace.objects.create(
            user=user,
            space=self.space,
            household=household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name="user")[0])
        return user

    @staticmethod
    def _client(user):
        client = APIClient()
        client.force_login(user)
        return client

    def _recipe_with_oil(self, name, *, private=False, owner=None):
        recipe = Recipe.objects.create(
            space=self.space,
            name=name,
            servings=4,
            private=private,
            created_by=owner or self.owner,
        )
        step = Step.objects.create(space=self.space, name=f"Paso de {name}")
        step.ingredients.add(
            Ingredient.objects.create(
                space=self.space,
                food=self.oil,
                unit=self.millilitre,
                amount=Decimal("400"),
            )
        )
        recipe.steps.add(step)
        return recipe

    def _history_url(self, package=None):
        return f"/api/cuaderno/packages/{(package or self.package).pk}/prices/"

    def _impact_url(self, recipe=None, package=None, servings="4"):
        recipe = recipe or self.recipe
        package = package or self.package
        return f"/api/cuaderno/recipes/{recipe.pk}/price-impact/?package={package.pk}&servings={servings}"

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(
            response.get("Content-Type", "").startswith("application/json"),
            "La ruta de API no debe resolverse al HTML de la SPA.",
        )

    def test_history_orders_all_versions_and_marks_only_the_effective_one_current(self):
        response = self.client.get(self._history_url())
        self.assert_json(response)
        payload = response.data
        self.assertEqual(payload["package"], self.package.pk)
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(payload["count"], 3)
        self.assertIsNone(payload["next_offset"])
        self.assertEqual(
            [item["id"] for item in payload["items"]],
            [self.future_price.pk, self.current_price.pk, self.old_price.pk],
        )
        self.assertEqual([item["is_current"] for item in payload["items"]], [False, True, False])
        self.assertEqual(payload["current_price_id"], self.current_price.pk)
        as_of = datetime.fromisoformat(payload["as_of"])
        self.assertLessEqual(self.current_price.valid_from, as_of)
        self.assertGreater(self.future_price.valid_from, as_of)
        for item in payload["items"]:
            self.assertEqual(
                set(item),
                {"id", "amount", "explicit_free", "valid_from", "created_at", "created_by", "note", "is_current"},
            )
            self.assertIsInstance(item["amount"], str)
            self.assertEqual(item["created_by"], self.owner.pk)

    def test_history_paginates_and_rejects_non_ascii_or_out_of_range_numbers(self):
        page = self.client.get(self._history_url(), {"limit": "1", "offset": "1"})
        self.assert_json(page)
        self.assertEqual(page.data["count"], 3)
        self.assertEqual(page.data["next_offset"], 2)
        self.assertEqual([item["id"] for item in page.data["items"]], [self.current_price.pk])
        last = self.client.get(self._history_url(), {"limit": "1", "offset": "2"})
        self.assert_json(last)
        self.assertIsNone(last.data["next_offset"])
        self.assertEqual(self.client.get(self._history_url(), {"limit": "100", "offset": "0"}).status_code, 200)

        with scopes_disabled():
            for index in range(19):
                PriceVersion.objects.create(
                    space=self.space,
                    package=self.package,
                    amount=Decimal(index + 1),
                    valid_from=timezone.now() - timedelta(days=index + 10),
                    created_by=self.owner,
                )
        default_page = self.client.get(self._history_url())
        self.assert_json(default_page)
        self.assertEqual(default_page.data["count"], 22)
        self.assertEqual(len(default_page.data["items"]), 20)
        self.assertEqual(default_page.data["next_offset"], 20)
        last_historical = self.client.get(self._history_url(), {"limit": "1", "offset": "21"})
        self.assert_json(last_historical)
        self.assertEqual(last_historical.data["current_price_id"], self.current_price.pk)
        self.assertNotEqual(last_historical.data["items"][0]["id"], self.current_price.pk)
        self.assertFalse(last_historical.data["items"][0]["is_current"])

        for field, values in (
            ("offset", ("-1", "+1", "1.0", "١", "", "9223372036854775808")),
            ("limit", ("0", "101", "-1", "+1", "1.5", "١", "")),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.client.get(self._history_url(), {field: value})
                    self.assert_json(response, 400)

    def test_history_is_space_scoped_and_available_in_esencial(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.ESENCIAL
            self.profile.save(update_fields=["edition"])
            foreign_space = Space.objects.create(name="Espacio ajeno", created_by=self.owner)
            foreign_unit = Unit.objects.create(space=foreign_space, name="kg", base_unit="kg")
            foreign_food = Food.add_root(space=foreign_space, name="Producto ajeno")
            foreign_package = PackageFormat.objects.create(
                space=foreign_space,
                food=foreign_food,
                unit=foreign_unit,
                label="Formato ajeno",
                quantity=1,
            )
        self.assert_json(self.client.get(self._history_url()), 200)
        self.assert_json(self.client.get(self._history_url(foreign_package)), 404)
        self.assert_json(self.client.get(self._impact_url(package=foreign_package)), 404)

    def test_direct_impact_uses_the_two_latest_effective_versions_exactly(self):
        response = self.client.get(self._impact_url())
        self.assert_json(response)
        payload = response.data
        self.assertEqual(payload["recipe_id"], self.recipe.pk)
        self.assertEqual(payload["package"], self.package.pk)
        self.assertEqual(payload["current_price_id"], self.current_price.pk)
        self.assertEqual(payload["previous_price_id"], self.old_price.pk)
        self.assertTrue(payload["affected"])
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(payload["price_policy"], SpaceProfile.NET)
        self.assertEqual(payload["before"]["status"], "complete")
        self.assertEqual(payload["after"]["status"], "complete")
        self.assertEqual(Decimal(payload["before"]["unrounded"]), Decimal("2.56"))
        self.assertEqual(Decimal(payload["after"]["unrounded"]), Decimal("2.80"))
        self.assertEqual(Decimal(payload["difference"]), Decimal("0.24"))
        self.assertEqual(Decimal(payload["difference_per_serving"]), Decimal("0.06"))
        self.assertIsInstance(payload["difference"], str)

        with scopes_disabled():
            salt = Food.add_root(space=self.space, name="Control con precio vigente")
            control_package = PackageFormat.objects.create(
                space=self.space,
                food=salt,
                unit=self.litre,
                label="Control 1 L",
                quantity=Decimal("1"),
            )
            PriceVersion.objects.create(
                space=self.space,
                package=control_package,
                amount=Decimal("10"),
                valid_from=self.old_price.valid_from,
                created_by=self.owner,
            )
            PriceVersion.objects.create(
                space=self.space,
                package=control_package,
                amount=Decimal("20"),
                valid_from=self.current_price.valid_from,
                created_by=self.owner,
            )
            self.recipe.steps.get().ingredients.add(
                Ingredient.objects.create(
                    space=self.space,
                    food=salt,
                    unit=self.litre,
                    amount=Decimal("1"),
                    order=1,
                )
            )
        with_control = self.client.get(self._impact_url())
        self.assert_json(with_control)
        # Only the selected package is replaced. Other ingredients retain the
        # price current at the request's single as_of in both calculations.
        self.assertEqual(Decimal(with_control.data["before"]["unrounded"]), Decimal("22.56"))
        self.assertEqual(Decimal(with_control.data["after"]["unrounded"]), Decimal("22.80"))
        self.assertEqual(Decimal(with_control.data["difference"]), Decimal("0.24"))

    def test_announced_price_is_used_when_a_backdated_version_arrives_between_queries(self):
        inserted = []

        def load_after_backdated_insert(recipe_cache, space_id, as_of):
            # Deterministic interleaving at the query boundary, with real
            # PostgreSQL persistence and the original context loader/motor.
            with scopes_disabled():
                inserted.append(PriceVersion.objects.create(
                    space=self.space, package=self.package, amount=Decimal("80"),
                    valid_from=as_of - timedelta(seconds=1), created_by=self.owner,
                    note="Versión retroactiva concurrente sintética",
                ))
            return _load_costing_context(recipe_cache, space_id, as_of)

        with patch("cuaderno.services.price_history._load_costing_context", side_effect=load_after_backdated_insert):
            response = self.client.get(self._impact_url())
        self.assert_json(response)
        self.assertEqual(len(inserted), 1)
        with scopes_disabled():
            self.assertTrue(PriceVersion.objects.filter(pk=inserted[0].pk).exists())
        self.assertEqual(response.data["current_price_id"], self.current_price.pk)
        self.assertEqual(response.data["previous_price_id"], self.old_price.pk)
        self.assertEqual(Decimal(response.data["after"]["unrounded"]), Decimal("2.80"))
        self.assertEqual(Decimal(response.data["difference"]), Decimal("0.24"))

    def test_temporal_tie_prefers_higher_id_and_ignores_future_price(self):
        with scopes_disabled():
            tied = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("36"),
                valid_from=self.current_price.valid_from,
                created_by=self.owner,
            )
        response = self.client.get(self._impact_url())
        self.assert_json(response)
        self.assertEqual(response.data["current_price_id"], tied.pk)
        self.assertEqual(response.data["previous_price_id"], self.current_price.pk)
        self.assertEqual(Decimal(response.data["difference"]), Decimal("0.08"))
        self.assertEqual(Decimal(response.data["difference_per_serving"]), Decimal("0.02"))

    def test_missing_previous_is_unknown_and_missing_current_keeps_both_sheets_incomplete(self):
        with scopes_disabled():
            self.old_price.delete()
        missing_before = self.client.get(self._impact_url())
        self.assert_json(missing_before)
        self.assertIsNone(missing_before.data["previous_price_id"])
        self.assertEqual(missing_before.data["before"]["status"], "incomplete")
        self.assertIsNone(missing_before.data["before"]["unrounded"])
        self.assertEqual(missing_before.data["after"]["status"], "complete")
        self.assertIsNone(missing_before.data["difference"])
        self.assertIsNone(missing_before.data["difference_per_serving"])

        with scopes_disabled():
            self.current_price.delete()
        no_effective_price = self.client.get(self._impact_url())
        self.assert_json(no_effective_price)
        self.assertIsNone(no_effective_price.data["current_price_id"])
        self.assertIsNone(no_effective_price.data["previous_price_id"])
        self.assertEqual(no_effective_price.data["before"]["status"], "incomplete")
        self.assertEqual(no_effective_price.data["after"]["status"], "incomplete")
        self.assertIsNone(no_effective_price.data["difference"])

    def test_unused_package_is_not_reported_as_affecting_the_recipe(self):
        with scopes_disabled():
            salt = Food.add_root(space=self.space, name="Sal sintética")
            package = PackageFormat.objects.create(
                space=self.space, food=salt, unit=self.litre, label="Salmuera 1 L", quantity=1,
            )
            for amount, days in (("10", 2), ("20", 1)):
                PriceVersion.objects.create(
                    space=self.space,
                    package=package,
                    amount=Decimal(amount),
                    valid_from=timezone.now() - timedelta(days=days),
                    created_by=self.owner,
                )
        response = self.client.get(self._impact_url(package=package))
        self.assert_json(response)
        self.assertFalse(response.data["affected"])
        self.assertEqual(Decimal(response.data["before"]["unrounded"]), Decimal("2.80"))
        self.assertEqual(response.data["before"], response.data["after"])
        self.assertEqual(Decimal(response.data["difference"]), Decimal("0"))

        with scopes_disabled():
            non_reference = PackageFormat.objects.create(
                space=self.space,
                food=self.oil,
                unit=self.litre,
                label="Botella no usada",
                quantity=Decimal("1"),
                is_reference=False,
            )
            for amount, days in (("7", 2), ("9", 1)):
                PriceVersion.objects.create(
                    space=self.space,
                    package=non_reference,
                    amount=Decimal(amount),
                    valid_from=timezone.now() - timedelta(days=days),
                    created_by=self.owner,
                )
        non_reference_response = self.client.get(self._impact_url(package=non_reference))
        self.assert_json(non_reference_response)
        self.assertFalse(non_reference_response.data["affected"])
        self.assertEqual(non_reference_response.data["before"], non_reference_response.data["after"])
        self.assertEqual(Decimal(non_reference_response.data["before"]["unrounded"]), Decimal("2.80"))

    def test_impact_rejects_noncanonical_package_and_servings_without_leaking_lookup_state(self):
        for package in (None, "+1", "1.0", "١", "0", "-1", "9223372036854775808"):
            with self.subTest(package=package):
                query = {"servings": "4"}
                if package is not None:
                    query["package"] = package
                response = self.client.get(
                    f"/api/cuaderno/recipes/{self.recipe.pk}/price-impact/",
                    query,
                )
                self.assert_json(response, 400)

        invalid_servings = (
            "",
            "0",
            "-1",
            "1e1",
            "NaN",
            "Inf",
            "-Inf",
            "0.12345678901234567",
            "12345678901234567.1234567890123456",
        )
        for servings in invalid_servings:
            with self.subTest(servings=servings):
                response = self.client.get(
                    f"/api/cuaderno/recipes/{self.recipe.pk}/price-impact/",
                    {"package": str(self.package.pk), "servings": servings},
                )
                self.assert_json(response, 400)

    def test_extremely_long_integer_queries_fail_closed_before_python_integer_conversion(self):
        response = self.client.get(
            f"/api/cuaderno/recipes/{self.recipe.pk}/price-impact/", {"package": "1" * 10000},
        )
        self.assert_json(response, 400)
        self.assert_json(self.client.get(self._history_url(), {"offset": "1" * 10000}), 400)

    def test_header_and_excluded_lines_do_not_report_price_impact(self):
        with scopes_disabled():
            ingredient = self.recipe.steps.get().ingredients.get()
            ingredient.is_header = True
            ingredient.save(update_fields=["is_header"])
        header = self.client.get(self._impact_url())
        self.assert_json(header)
        self.assertFalse(header.data["affected"])
        self.assertEqual(header.data["before"], header.data["after"])
        self.assertEqual(Decimal(header.data["difference"]), Decimal("0"))
        with scopes_disabled():
            ingredient.is_header = False
            ingredient.no_amount = True
            ingredient.save(update_fields=["is_header", "no_amount"])
        excluded = self.client.get(self._impact_url())
        self.assert_json(excluded)
        self.assertFalse(excluded.data["affected"])
        self.assertEqual(excluded.data["before"], excluded.data["after"])

    def test_private_recipe_and_private_child_are_not_disclosed(self):
        other_client = self._client(self.other)
        self.assert_json(other_client.get(self._impact_url()), 404)
        self.assert_json(other_client.get(
            f"/api/cuaderno/recipes/{self.recipe.pk}/price-impact/", {"package": "+1", "servings": "NaN"},
        ), 404)
        secret = "SECRETO-HIJO-IMPACTO"
        with scopes_disabled():
            child = self._recipe_with_oil(secret, private=True)
            parent = Recipe.objects.create(
                space=self.space, name="Receta pública", servings=4, created_by=self.other,
            )
            parent_step = Step.objects.create(space=self.space, name="Subreceta reservada", step_recipe=child)
            parent.steps.add(parent_step)
        response = other_client.get(self._impact_url(recipe=parent))
        self.assertIn(response.status_code, (400, 404), response.content)
        self.assertNotIn(secret, response.content.decode("utf-8"))
        self.assertNotIn(self.oil.name, response.content.decode("utf-8"))

    def test_step_recipe_and_food_recipe_edges_both_propagate_price_impact(self):
        with scopes_disabled():
            child = self._recipe_with_oil("Base compartida")
            step_parent = Recipe.objects.create(
                space=self.space, name="Padre por paso", servings=4, created_by=self.owner,
            )
            linked_step = Step.objects.create(space=self.space, name="Incluir base", step_recipe=child)
            step_parent.steps.add(linked_step)

            portion = Unit.objects.create(space=self.space, name="porción", base_unit="")
            RecipeYield.objects.create(
                space=self.space,
                recipe=child,
                quantity=Decimal("1"),
                unit=portion,
                updated_by=self.owner,
            )
            prepared = Food.add_root(space=self.space, name="Base preparada", recipe=child)
            food_parent = Recipe.objects.create(
                space=self.space, name="Padre por alimento", servings=4, created_by=self.owner,
            )
            food_step = Step.objects.create(space=self.space, name="Añadir base")
            food_step.ingredients.add(
                Ingredient.objects.create(
                    space=self.space, food=prepared, unit=portion, amount=Decimal("1"),
                )
            )
            food_parent.steps.add(food_step)

        for recipe in (step_parent, food_parent):
            with self.subTest(edge=recipe.name):
                response = self.client.get(self._impact_url(recipe=recipe))
                self.assert_json(response)
                self.assertTrue(response.data["affected"])
                self.assertEqual(Decimal(response.data["difference"]), Decimal("0.24"))

    def test_confirmed_service_snapshot_is_unchanged_by_history_and_new_price(self):
        service_date = (timezone.localdate() + timedelta(days=1)).isoformat()
        created = self.client.post(
            "/api/cuaderno/services/",
            {"recipe": self.recipe.pk, "covers": "4", "service_date": service_date, "title": "Servicio congelado"},
            format="json",
        )
        self.assert_json(created, 201)
        service_url = f"/api/cuaderno/services/{created.data['id']}/"
        confirmed = self.client.post(service_url, {"action": "confirm"}, format="json")
        self.assert_json(confirmed)
        frozen = confirmed.data["snapshot"]
        created_price = self.client.post(
            self._history_url(),
            {"amount": "40", "explicit_free": False},
            format="json",
        )
        self.assert_json(created_price, 201)
        impact = self.client.get(self._impact_url())
        self.assert_json(impact)
        self.assertEqual(impact.data["current_price_id"], created_price.data["id"])
        self.assertEqual(impact.data["previous_price_id"], self.current_price.pk)
        self.assertEqual(Decimal(impact.data["difference"]), Decimal("0.40"))
        self.assertEqual(Decimal(impact.data["difference_per_serving"]), Decimal("0.10"))
        persisted = self.client.get(service_url)
        self.assert_json(persisted)
        self.assertEqual(persisted.data["snapshot"], frozen)

    def test_query_count_does_not_grow_with_repeated_ingredient_lines(self):
        with scopes_disabled():
            step = self.recipe.steps.get()
            for index in range(14):
                step.ingredients.add(
                    Ingredient.objects.create(
                        space=self.space,
                        food=self.oil,
                        unit=self.millilitre,
                        amount=Decimal("10"),
                        order=index + 1,
                    )
                )
        self.assert_json(self.client.get(self._impact_url()))
        with CaptureQueriesContext(connection) as fifteen_queries:
            first = self.client.get(self._impact_url())
        self.assert_json(first)

        with scopes_disabled():
            for index in range(15):
                step.ingredients.add(
                    Ingredient.objects.create(
                        space=self.space,
                        food=self.oil,
                        unit=self.millilitre,
                        amount=Decimal("10"),
                        order=index + 15,
                    )
                )
        with CaptureQueriesContext(connection) as thirty_queries:
            second = self.client.get(self._impact_url())
        self.assert_json(second)
        self.assertTrue(second.data["affected"])
        self.assertLessEqual(
            len(thirty_queries),
            25,
            f"El impacto ejecutó {len(thirty_queries)} consultas para treinta líneas repetidas.",
        )
        self.assertLessEqual(
            len(thirty_queries),
            len(fifteen_queries) + 2,
            f"El impacto escaló de {len(fifteen_queries)} a {len(thirty_queries)} consultas al duplicar líneas.",
        )
