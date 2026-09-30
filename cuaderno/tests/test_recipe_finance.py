from decimal import Decimal, getcontext

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, FoodProperty, Ingredient, Property, PropertyType, Recipe, Space, Step, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
from cuaderno.services.costing import cost_recipe
from cuaderno.services.recipe_finance import (
    BUDGET_PER_PERSON_SLUG,
    SELLING_PRICE_PER_SERVING_SLUG,
    read_recipe_finance,
    write_recipe_finance,
)


class RecipeFinanceTests(TestCase):
    def test_derived_cost_accepts_64_significant_digits_without_rounding(self):
        values = (
            "0." + "3" * 64,
            "99999999999999999.99999999999999800000000000000000000000000000001",
            "99999999999999999999999999999999",
            "0.00000000000000000000000000000001",
            "0",
        )
        context_before = getcontext().copy()
        with scopes_disabled():
            for value in values:
                with self.subTest(value=value):
                    result = read_recipe_finance(
                        self.recipe,
                        {"status": "complete", "per_serving": value, "warnings": []},
                        self.profile,
                    )
                    self.assertEqual(result["ingredient_cost_per_serving"], value)
                    self.assertIsNone(result["net_profit"])
            self.assertFalse(Property.objects.filter(space=self.space).exists())
        self.assertEqual(getcontext().prec, context_before.prec)
        self.assertEqual(getcontext().flags, context_before.flags)

    def test_derived_cost_rejects_precision_and_magnitude_overflow_and_invalid_values(self):
        values = (
            "0." + "3" * 65,
            "100000000000000000000000000000000",
            "0.000000000000000000000000000000001",
            "-1", "NaN", "Infinity", "-Infinity", True, 0.1, "",
        )
        with scopes_disabled():
            for value in values:
                with self.subTest(value=value), self.assertRaises(DomainError) as error:
                    read_recipe_finance(
                        self.recipe,
                        {"status": "complete", "per_serving": value, "warnings": []},
                        self.profile,
                    )
                self.assertEqual(error.exception.code, "invalid_recipe_finance")
            with self.assertRaises(DomainError):
                write_recipe_finance(self.recipe, {"budget_per_person": "1.23456"}, self.user)
            self.assertFalse(Property.objects.filter(space=self.space).exists())

    def test_ratio_presentation_uses_half_up_on_exact_tie(self):
        with scopes_disabled():
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "1"}, self.user)
            cost = {"status": "complete", "per_serving": "0.12345", "warnings": []}
            self.assertEqual(read_recipe_finance(self.recipe, cost, self.profile)["food_cost_ratio"], "0.1235")

    def test_duplicate_reserved_native_property_is_rejected(self):
        with scopes_disabled():
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "1"}, self.user)
            existing = self.recipe.properties.get()
            duplicate = Property.objects.create(space=self.space, property_type=existing.property_type, property_amount="2")
            self.recipe.properties.add(duplicate)
            with self.assertRaises(DomainError):
                read_recipe_finance(self.recipe, self.real_cost(), self.profile)

    def setUp(self):
        with scopes_disabled():
            self.space = Space.objects.create(name="Finanzas de receta")
            self.user = get_user_model().objects.create_user(username="finance-user", password="local-test-only")
            self.space.created_by = self.user
            self.space.save(update_fields=["created_by"])
            self.profile = SpaceProfile.objects.create(
                space=self.space,
                edition=SpaceProfile.PROFESIONAL,
                price_policy=SpaceProfile.NET,
            )
            self.unit = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.food = Food.objects.create(space=self.space, name="Ingrediente")
            package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                label="Paquete 1 kg",
                quantity=Decimal("1"),
            )
            PriceVersion.objects.create(
                space=self.space,
                package=package,
                amount=Decimal("2"),
                explicit_free=False,
                valid_from=timezone.now(),
                created_by=self.user,
            )
            ingredient = Ingredient.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                amount=Decimal("1"),
            )
            step = Step.objects.create(space=self.space, name="Preparar")
            step.ingredients.add(ingredient)
            self.recipe = Recipe.objects.create(
                space=self.space,
                name="Receta financiera",
                servings=2,
                created_by=self.user,
            )
            self.recipe.steps.add(step)

    def real_cost(self):
        return cost_recipe(self.recipe, 2, user=self.user)

    def test_read_is_side_effect_free_and_unknown_references_are_not_zero(self):
        with scopes_disabled():
            before = (PropertyType.objects.count(), Property.objects.count())
            result = read_recipe_finance(self.recipe, self.real_cost(), self.profile)
            self.assertEqual(result["status"], "incomplete")
            self.assertIsNone(result["selling_price_per_serving"])
            self.assertIsNone(result["budget_per_person"])
            self.assertIsNone(result["difference_per_serving"])
            self.assertIsNone(result["food_cost_ratio"])
            self.assertIsNone(result["budget_gap_per_person"])
            self.assertIsNone(result["net_profit"])
            self.assertEqual((PropertyType.objects.count(), Property.objects.count()), before)

    def test_values_1_25_use_real_per_serving_cost_and_explicit_price_policy(self):
        with scopes_disabled():
            write_recipe_finance(
                self.recipe,
                {"selling_price_per_serving": "1.25", "budget_per_person": "1,25"},
                self.user,
            )
            result = read_recipe_finance(self.recipe, self.real_cost(), self.profile)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["ingredient_cost_per_serving"], "1")
            self.assertEqual(result["selling_price_per_serving"], "1.25")
            self.assertEqual(result["budget_per_person"], "1.25")
            self.assertEqual(result["difference_per_serving"], "0.25")
            self.assertEqual(result["food_cost_ratio"], "0.8000")
            self.assertEqual(result["budget_gap_per_person"], "0.25")
            self.assertEqual(result["price_policy"], "net")
            self.assertIsNone(result["net_profit"])
            types = {
                row.open_data_slug: (row.category, row.unit)
                for row in PropertyType.objects.filter(space=self.space)
            }
            self.assertEqual(types[SELLING_PRICE_PER_SERVING_SLUG], (PropertyType.PRICE, "EUR/persona"))
            self.assertEqual(types[BUDGET_PER_PERSON_SLUG], (PropertyType.GOAL, "EUR/persona"))

    def test_overwrite_and_exact_replay_keep_one_native_property_and_one_audit_event(self):
        with scopes_disabled():
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "1.25"}, self.user)
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "2.5"}, self.user)
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "2.5000"}, self.user)
            properties = self.recipe.properties.filter(
                property_type__open_data_slug=SELLING_PRICE_PER_SERVING_SLUG
            )
            self.assertEqual(properties.count(), 1)
            self.assertEqual(properties.get().property_amount, Decimal("2.5000"))
            logs = LogEntry.objects.filter(
                user=self.user,
                object_id=str(self.recipe.pk),
                action_flag=CHANGE,
            )
            self.assertEqual(logs.count(), 2)
            self.assertIn(SELLING_PRICE_PER_SERVING_SLUG, logs.latest("id").change_message)

    def test_zero_sale_is_persisted_but_never_used_as_a_divisor_or_profit(self):
        with scopes_disabled():
            write_recipe_finance(self.recipe, {"selling_price_per_serving": "0"}, self.user)
            result = read_recipe_finance(self.recipe, self.real_cost(), self.profile)
            self.assertEqual(result["selling_price_per_serving"], "0")
            self.assertEqual(result["status"], "incomplete")
            self.assertIsNone(result["difference_per_serving"])
            self.assertIsNone(result["food_cost_ratio"])
            self.assertIsNone(result["net_profit"])
            self.assertIn("selling_price_zero", result["warnings"])

    def test_incomplete_cost_does_not_turn_known_references_into_calculated_values(self):
        with scopes_disabled():
            write_recipe_finance(
                self.recipe,
                {"selling_price_per_serving": "4", "budget_per_person": "3"},
                self.user,
            )
            result = read_recipe_finance(
                self.recipe,
                {"status": "incomplete", "per_serving": None, "warnings": ["precio_desconocido"]},
                self.profile,
            )
            self.assertEqual(result["status"], "incomplete")
            self.assertIsNone(result["ingredient_cost_per_serving"])
            self.assertIsNone(result["difference_per_serving"])
            self.assertIsNone(result["food_cost_ratio"])
            self.assertIsNone(result["budget_gap_per_person"])
            self.assertIn("cost_incomplete", result["warnings"])

    def test_real_recurring_cost_is_not_forced_into_property_storage_precision(self):
        with scopes_disabled():
            self.recipe.servings = 3
            self.recipe.save(update_fields=["servings"])
            price = PriceVersion.objects.get(space=self.space)
            price.amount = Decimal("1")
            price.save(update_fields=["amount"])
            write_recipe_finance(self.recipe, {"budget_per_person": "1.25"}, self.user)
            cost = self.real_cost()
            self.assertTrue(cost["per_serving"].startswith("0.3333333333333333"))
            result = read_recipe_finance(self.recipe, cost, self.profile)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["ingredient_cost_per_serving"], cost["per_serving"])
            self.assertIsNotNone(result["budget_gap_per_person"])

    def test_invalid_money_is_rejected_before_creating_native_rows(self):
        invalid = ("-1", "NaN", "1.23456", "10000000000000000000000000000")
        with scopes_disabled():
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(DomainError):
                    write_recipe_finance(self.recipe, {"selling_price_per_serving": value}, self.user)
            self.assertFalse(PropertyType.objects.filter(space=self.space).exists())
            self.assertFalse(Property.objects.filter(space=self.space).exists())

    def test_read_rejects_cross_space_and_malformed_reserved_properties(self):
        with scopes_disabled():
            other_space = Space.objects.create(name="Otro espacio", created_by=self.user)
            cross_type = PropertyType.objects.create(
                space=other_space,
                name="Venta",
                category=PropertyType.PRICE,
                unit="EUR/persona",
                open_data_slug=SELLING_PRICE_PER_SERVING_SLUG,
            )
            cross_property = Property.objects.create(
                space=other_space,
                property_type=cross_type,
                property_amount=Decimal("2"),
            )
            self.recipe.properties.add(cross_property)
            with self.assertRaises(DomainError):
                read_recipe_finance(self.recipe, self.real_cost(), self.profile)
            self.recipe.properties.remove(cross_property)

            malformed_type = PropertyType.objects.create(
                space=self.space,
                name="Venta mal formada",
                category=PropertyType.GOAL,
                unit="EUR",
                open_data_slug=SELLING_PRICE_PER_SERVING_SLUG,
            )
            malformed = Property.objects.create(
                space=self.space,
                property_type=malformed_type,
                property_amount=Decimal("2"),
            )
            self.recipe.properties.add(malformed)
            with self.assertRaises(DomainError):
                read_recipe_finance(self.recipe, self.real_cost(), self.profile)

    def test_null_unlinks_but_does_not_delete_a_native_property_shared_elsewhere(self):
        with scopes_disabled():
            write_recipe_finance(self.recipe, {"budget_per_person": "3"}, self.user)
            shared = self.recipe.properties.get(property_type__open_data_slug=BUDGET_PER_PERSON_SLUG)
            other = Recipe.objects.create(
                space=self.space,
                name="Otra receta",
                servings=1,
                created_by=self.user,
            )
            other.properties.add(shared)
            write_recipe_finance(self.recipe, {"budget_per_person": None}, self.user)
            self.assertFalse(self.recipe.properties.filter(pk=shared.pk).exists())
            self.assertTrue(other.properties.filter(pk=shared.pk).exists())
            self.assertTrue(Property.objects.filter(pk=shared.pk).exists())
            self.assertFalse(FoodProperty.objects.filter(property=shared).exists())
