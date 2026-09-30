"""Exact serving-ratio contracts for confirmed and produced services."""

from decimal import Decimal, getcontext, localcontext

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    Household,
    Ingredient,
    InventoryEntry,
    InventoryLocation,
    Recipe,
    SearchFields,
    Space,
    Step,
    Unit,
    UserSpace,
)
from cuaderno.models import PackageFormat, PriceVersion, RecipeYield, ServicePlan, SpaceProfile, StockMovement
from cuaderno.domain.errors import DomainError
from cuaderno.services.costing import cost_recipe
from cuaderno.services.subrecipes import sheet_from_recipes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServiceRatioPrecisionTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = get_user_model().objects.create_user(
                username="service-ratio-owner", password="synthetic-only"
            )
            self.space = Space.objects.create(
                name="Service ratio precision", created_by=self.owner
            )
            self.household = Household.objects.create(
                space=self.space, name="Service ratio kitchen"
            )
            membership = UserSpace.objects.create(
                user=self.owner,
                space=self.space,
                household=self.household,
                active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.INTEGRAL)
            self.kg = Unit.objects.create(
                space=self.space, name="ratio-kg", base_unit="kg"
            )
            self.g = Unit.objects.create(
                space=self.space, name="ratio-g", base_unit="g"
            )
            self.location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Ratio stock",
                created_by=self.owner,
            )
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.assertEqual(
            connection.vendor,
            "postgresql",
            "Este contrato de precisión de producción requiere PostgreSQL real.",
        )

    def _food_with_price(self, name):
        food = Food.add_root(space=self.space, name=name)
        package = PackageFormat.objects.create(
            space=self.space,
            food=food,
            unit=self.kg,
            label=f"1 kg {name}",
            quantity=Decimal("1"),
            is_reference=True,
        )
        PriceVersion.objects.create(
            space=self.space,
            package=package,
            amount=Decimal("1"),
            valid_from=timezone.now(),
            created_by=self.owner,
        )
        return food

    def _recipe(self, name, *, servings=3):
        return Recipe.objects.create(
            space=self.space,
            name=name,
            servings=servings,
            created_by=self.owner,
        )

    def _ingredient_step(self, recipe, food, amount, *, basis="gross", ratio=None):
        ingredient = Ingredient.objects.create(
            space=self.space,
            food=food,
            unit=self.kg,
            amount=Decimal(amount),
            quantity_basis=basis,
            yield_ratio=ratio,
        )
        step = Step.objects.create(
            space=self.space, instruction=f"Preparar {recipe.name}"
        )
        step.ingredients.add(ingredient)
        recipe.steps.add(step)
        return ingredient

    def _create_and_confirm(self, recipe, title):
        created = self.client.post(
            "/api/cuaderno/services/",
            {
                "title": title,
                "covers": "1",
                "service_date": "2026-10-25",
                "recipe": recipe.pk,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        service_id = created.data["id"]
        confirmed = self.client.post(
            f"/api/cuaderno/services/{service_id}/", {"action": "confirm"}, format="json"
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["state"], ServicePlan.CONFIRMED)
        return service_id, confirmed.data["snapshot"]

    def _need(self, snapshot, food):
        rows = [row for row in snapshot["needs"] if row["food_id"] == food.pk]
        self.assertEqual(len(rows), 1, snapshot["needs"])
        self.assertEqual(rows[0]["unit_id"], self.kg.pk)
        return Decimal(rows[0]["quantity"])

    def _assert_exact_production(self, recipe, food, title, key):
        entry = InventoryEntry.objects.create(
            space=self.space,
            inventory_location=self.location,
            food=food,
            unit=self.kg,
            amount=Decimal("1"),
            created_by=self.owner,
        )
        service_id, snapshot = self._create_and_confirm(recipe, title)
        self.assertEqual(self._need(snapshot, food), Decimal("1"))
        self.assertEqual(Decimal(snapshot["cost"]["total"]), Decimal("1"))

        produced = self.client.post(
            f"/api/cuaderno/services/{service_id}/",
            {"action": "produce", "idempotency_key": key},
            format="json",
        )

        self.assertEqual(produced.status_code, 200, produced.data)
        self.assertEqual(produced.data["state"], ServicePlan.PRODUCED)
        self.assertTrue(produced.data["stock_changed"])
        self.assertEqual(len(produced.data["movement_ids"]), 1)
        with scopes_disabled():
            entry.refresh_from_db()
            plan = ServicePlan.objects.get(pk=service_id)
            movement = StockMovement.objects.get(pk=produced.data["movement_ids"][0])
        self.assertEqual(entry.amount, Decimal("0"))
        self.assertEqual(plan.state, ServicePlan.PRODUCED)
        self.assertEqual(movement.quantity, Decimal("1"))
        self.assertEqual(movement.balance_after, Decimal("0"))
        self.assertEqual(movement.metadata_snapshot["origin"]["id"], service_id)

    def test_direct_three_over_three_cancels_before_storage_and_produces(self):
        with scopes_disabled():
            food = self._food_with_price("Direct ratio food")
            recipe = self._recipe("Direct ratio recipe")
            self._ingredient_step(recipe, food, "3")

        self._assert_exact_production(
            recipe, food, "Direct 3 over 3", "service-ratio-direct-v1"
        )

    def test_food_recipe_yield_keeps_ratio_until_the_leaf_ingredient(self):
        with scopes_disabled():
            raw_food = self._food_with_price("Nested ratio raw food")
            child = self._recipe("Nested ratio child", servings=1)
            self._ingredient_step(child, raw_food, "3")
            RecipeYield.objects.create(
                space=self.space,
                recipe=child,
                quantity=Decimal("3"),
                unit=self.kg,
                updated_by=self.owner,
            )
            child_food = Food.add_root(
                space=self.space, name="Nested ratio output", recipe=child
            )
            parent = self._recipe("Nested ratio parent")
            self._ingredient_step(parent, child_food, "3")

        self._assert_exact_production(
            parent, raw_food, "Food recipe 3 over 3", "service-ratio-food-child-v1"
        )

    def test_step_recipe_inherits_the_root_ratio_without_predivision(self):
        with scopes_disabled():
            raw_food = self._food_with_price("Step ratio raw food")
            child = self._recipe("Step ratio child", servings=1)
            self._ingredient_step(child, raw_food, "3")
            parent = self._recipe("Step ratio parent")
            parent.steps.add(
                Step.objects.create(
                    space=self.space,
                    instruction="Preparar subreceta por paso",
                    step_recipe=child,
                )
            )

        self._assert_exact_production(
            parent, raw_food, "Step recipe 3 over 3", "service-ratio-step-child-v1"
        )

    def test_food_recipe_ratio_preserves_real_kg_to_g_conversion(self):
        with scopes_disabled():
            raw_food = self._food_with_price("Converted nested raw food")
            child = self._recipe("Converted nested child", servings=1)
            self._ingredient_step(child, raw_food, "3")
            RecipeYield.objects.create(
                space=self.space,
                recipe=child,
                quantity=Decimal("3000"),
                unit=self.g,
                updated_by=self.owner,
            )
            child_food = Food.add_root(
                space=self.space, name="Converted nested output", recipe=child
            )
            parent = self._recipe("Converted nested parent")
            self._ingredient_step(parent, child_food, "3")

        self._assert_exact_production(
            parent,
            raw_food,
            "Food recipe kg to g ratio",
            "service-ratio-food-converted-v1",
        )

    def test_genuine_recurring_ratio_and_single_yield_remain_unrounded(self):
        with scopes_disabled():
            food = self._food_with_price("Recurring useful food")
            recipe = self._recipe("Recurring useful recipe")
            ingredient = self._ingredient_step(
                recipe, food, "1", basis="net_usable", ratio=Decimal("0.8")
            )

        _, snapshot = self._create_and_confirm(recipe, "Recurring ratio")
        with localcontext() as context:
            context.prec = 64
            useful = Decimal("1") * Decimal("1") / Decimal("3")
            purchased = useful / Decimal("0.8")
            waste = purchased - useful

        self.assertEqual(self._need(snapshot, food), purchased)
        self.assertEqual(Decimal(snapshot["cost"]["total"]), purchased)
        traces = [
            row for row in snapshot["ingredient_yields"]
            if row["ingredient_id"] == ingredient.pk
        ]
        self.assertEqual(len(traces), 1)
        self.assertEqual(Decimal(traces[0]["useful_quantity"]), useful)
        self.assertEqual(Decimal(traces[0]["purchased_quantity"]), purchased)
        self.assertEqual(Decimal(traces[0]["waste_quantity"]), waste)
        self.assertGreater(-purchased.as_tuple().exponent, 16)

    def test_price_impact_uses_the_same_exact_ratio_as_current_cost(self):
        self.assertEqual(getcontext().prec, 28)
        with scopes_disabled():
            food = self._food_with_price("Price impact ratio food")
            recipe = self._recipe("Price impact ratio recipe")
            self._ingredient_step(recipe, food, "3")
            package = PackageFormat.objects.get(food=food, is_reference=True)
            current = PriceVersion.objects.create(
                space=self.space,
                package=package,
                amount=Decimal("2"),
                valid_from=timezone.now(),
                created_by=self.owner,
            )

        response = self.client.get(
            f"/api/cuaderno/recipes/{recipe.pk}/price-impact/",
            {"package": str(package.pk), "servings": "1"},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["current_price_id"], current.pk)
        self.assertTrue(response.data["affected"])
        self.assertEqual(Decimal(response.data["before"]["unrounded"]), Decimal("1"))
        self.assertEqual(Decimal(response.data["after"]["unrounded"]), Decimal("2"))
        self.assertEqual(Decimal(response.data["difference"]), Decimal("1"))
        self.assertEqual(Decimal(response.data["difference_per_serving"]), Decimal("1"))
        with scopes_disabled():
            current_cost = cost_recipe(recipe, Decimal("1"), user=self.owner)
        self.assertEqual(Decimal(current_cost["unrounded"]), Decimal("2"))
        self.assertEqual(response.data["after"], current_cost)
        self.assertEqual(getcontext().prec, 28)

    def test_legacy_factors_remain_compatible_and_unmapped_roots_default_to_one(self):
        with scopes_disabled():
            scaled_food = self._food_with_price("Legacy factor food")
            scaled_recipe = self._recipe("Legacy factor recipe")
            self._ingredient_step(scaled_recipe, scaled_food, "3")
            default_food = self._food_with_price("Default factor food")
            default_recipe = self._recipe("Default factor recipe")
            self._ingredient_step(default_recipe, default_food, "2")

            legacy = sheet_from_recipes(
                [scaled_recipe.pk],
                self.space,
                self.owner,
                factors={scaled_recipe.pk: Decimal("0.5")},
            )
            explicit_ratio = sheet_from_recipes(
                [scaled_recipe.pk],
                self.space,
                self.owner,
                factor_ratios={scaled_recipe.pk: (Decimal("1"), Decimal("2"))},
            )
            multiple = sheet_from_recipes(
                [scaled_recipe.pk, default_recipe.pk],
                self.space,
                self.owner,
                factor_ratios={scaled_recipe.pk: (Decimal("1"), Decimal("3"))},
            )

        # A positional Decimal scale can retain one extra trailing zero;
        # compatibility is exact numeric quantity, not textual exponent.
        self.assertEqual(
            {name: Decimal(value) for name, value in legacy["needs"].items()},
            {name: Decimal(value) for name, value in explicit_ratio["needs"].items()},
        )
        self.assertEqual(Decimal(legacy["needs"][scaled_food.name]), Decimal("1.5"))
        self.assertEqual(Decimal(multiple["needs"][scaled_food.name]), Decimal("1"))
        self.assertEqual(Decimal(multiple["needs"][default_food.name]), Decimal("2"))

    def test_factor_ratios_are_exclusive_and_reject_malformed_or_nonpositive_parts(self):
        with scopes_disabled():
            food = self._food_with_price("Invalid ratio food")
            recipe = self._recipe("Invalid ratio recipe")
            self._ingredient_step(recipe, food, "3")

            with self.assertRaises(DomainError) as exclusive:
                sheet_from_recipes(
                    [recipe.pk],
                    self.space,
                    self.owner,
                    factors={recipe.pk: Decimal("1")},
                    factor_ratios={recipe.pk: (Decimal("1"), Decimal("3"))},
                )
            self.assertEqual(exclusive.exception.code, "invalid_scale")

            invalid = (
                None,
                "1/3",
                (Decimal("1"),),
                (Decimal("0"), Decimal("3")),
                (Decimal("-1"), Decimal("3")),
                (Decimal("1"), Decimal("0")),
                (Decimal("1"), Decimal("NaN")),
                (Decimal("Infinity"), Decimal("3")),
                (True, Decimal("3")),
            )
            for factor_ratio in invalid:
                with self.subTest(factor_ratio=factor_ratio), self.assertRaises(DomainError) as rejected:
                    sheet_from_recipes(
                        [recipe.pk],
                        self.space,
                        self.owner,
                        factor_ratios={recipe.pk: factor_ratio},
                    )
                self.assertEqual(rejected.exception.code, "invalid_scale")
