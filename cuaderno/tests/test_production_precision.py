"""Precision contracts for native production-sheet aggregation."""

from decimal import Decimal, getcontext, setcontext

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django_scopes import scopes_disabled

from cookbook.models import (
    Food,
    Household,
    Ingredient,
    Recipe,
    SearchFields,
    Space,
    Step,
    Unit,
    UserSpace,
)
from cuaderno.models import RecipeYield
from cuaderno.services.subrecipes import sheet_from_recipes


MAX_AMOUNT = Decimal("9999999999999999.9999999999999999")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductionSheetPrecisionTests(TestCase):
    def setUp(self):
        self.original_context = getcontext().copy()
        getcontext().prec = 28
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = get_user_model().objects.create_user(
                username="production-precision-owner", password="synthetic-only"
            )
            self.space = Space.objects.create(
                name="Production precision", created_by=self.owner
            )
            self.household = Household.objects.create(
                space=self.space, name="Production precision kitchen"
            )
            membership = UserSpace.objects.create(
                user=self.owner,
                space=self.space,
                household=self.household,
                active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.grams = Unit.objects.create(
                space=self.space, name="precision-g", base_unit="g"
            )
        self.assertEqual(
            connection.vendor,
            "postgresql",
            "Este contrato de integración requiere PostgreSQL real.",
        )

    def tearDown(self):
        setcontext(self.original_context)

    def _recipe(self, name):
        return Recipe.objects.create(
            space=self.space,
            created_by=self.owner,
            name=name,
            servings=1,
        )

    def _add_ingredients(self, recipe, *ingredients):
        step = Step.objects.create(
            space=self.space, instruction=f"Preparar {recipe.name}"
        )
        step.ingredients.add(*ingredients)
        recipe.steps.add(step)

    def _sheet_read_only(self, recipe):
        with CaptureQueriesContext(connection) as queries:
            with scopes_disabled():
                sheet = sheet_from_recipes(
                    [recipe.pk], self.space, user=self.owner
                )
        self.assertGreater(len(queries), 0)
        for query in queries:
            self.assertTrue(
                query["sql"].lstrip().upper().startswith("SELECT"),
                f"La ficha de necesidades intentó escribir: {query['sql']}",
            )
        return sheet

    def test_two_max_precision_ingredients_sum_without_losing_the_33rd_digit(self):
        with scopes_disabled():
            food = Food.add_root(
                space=self.space, name="Precision ordinary ingredient"
            )
            recipe = self._recipe("Precision direct production")
            ingredients = [
                Ingredient.objects.create(
                    space=self.space,
                    food=food,
                    unit=self.grams,
                    amount=MAX_AMOUNT,
                )
                for _ in range(2)
            ]
            self._add_ingredients(recipe, *ingredients)

        sheet = self._sheet_read_only(recipe)

        self.assertEqual(
            sheet["needs"][food.name],
            "19999999999999999.9999999999999998",
        )
        self.assertEqual(getcontext().prec, 28)
        with scopes_disabled():
            stored = list(
                Ingredient.objects.filter(pk__in=[row.pk for row in ingredients])
                .order_by("pk")
                .values_list("amount", flat=True)
            )
        self.assertEqual(stored, [MAX_AMOUNT, MAX_AMOUNT])

    def test_subrecipe_factor_preserves_the_full_64_digit_finite_result(self):
        with scopes_disabled():
            raw_food = Food.add_root(
                space=self.space, name="Precision child raw ingredient"
            )
            child = self._recipe("Precision child recipe")
            child_ingredient = Ingredient.objects.create(
                space=self.space,
                food=raw_food,
                unit=self.grams,
                amount=MAX_AMOUNT,
            )
            self._add_ingredients(child, child_ingredient)
            RecipeYield.objects.create(
                space=self.space,
                recipe=child,
                quantity=Decimal("1000000000000000"),
                unit=self.grams,
                updated_by=self.owner,
            )
            child_food = Food.add_root(
                space=self.space,
                name="Precision child output",
                recipe=child,
            )
            parent = self._recipe("Precision parent recipe")
            parent_ingredient = Ingredient.objects.create(
                space=self.space,
                food=child_food,
                unit=self.grams,
                amount=MAX_AMOUNT,
            )
            self._add_ingredients(parent, parent_ingredient)

        sheet = self._sheet_read_only(parent)

        self.assertEqual(
            sheet["needs"][raw_food.name],
            "99999999999999999.99999999999999800000000000000000000000000000001",
        )
        self.assertEqual(getcontext().prec, 28)
        with scopes_disabled():
            child_ingredient.refresh_from_db()
            parent_ingredient.refresh_from_db()
            declared = RecipeYield.objects.get(recipe=child)
        self.assertEqual(child_ingredient.amount, MAX_AMOUNT)
        self.assertEqual(parent_ingredient.amount, MAX_AMOUNT)
        self.assertEqual(declared.quantity, Decimal("1000000000000000"))
