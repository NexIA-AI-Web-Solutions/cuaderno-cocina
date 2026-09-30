from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, Ingredient, Recipe, Space, Step, Unit, UnitConversion
from cuaderno.models import PackageFormat, PriceVersion
from cuaderno.services.costing import _convert_native_quantity, _load_costing_context, cost_recipe
from cuaderno.services.subrecipes import convert_native_quantity, native_recipe_graph


class CostingQueryTests(TestCase):
    """The number of ingredient lines must not determine the query count."""

    def setUp(self):
        with scopes_disabled():
            self.user = get_user_model().objects.create_user(username="cost-query-owner")
            self.space = Space.objects.create(name="Costes por lotes", created_by=self.user)
            self.unit = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.recipe = Recipe.objects.create(
                space=self.space,
                name="Receta con quince ingredientes",
                servings=1,
                created_by=self.user,
            )
            step = Step.objects.create(space=self.space, name="Preparar")
            now = timezone.now()
            for index in range(15):
                food = Food.objects.create(space=self.space, name=f"Ingrediente {index:02d}")
                ingredient = Ingredient.objects.create(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    amount=Decimal("0.1"),
                    order=index,
                )
                step.ingredients.add(ingredient)
                package = PackageFormat.objects.create(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    label=f"Formato {index:02d}",
                    quantity=Decimal("1"),
                    is_reference=True,
                )
                PriceVersion.objects.create(
                    space=self.space,
                    package=package,
                    amount=Decimal("10"),
                    valid_from=now,
                    created_by=self.user,
                )
            self.recipe.steps.add(step)

    def test_fifteen_ingredients_are_costed_with_seven_joined_queries(self):
        with scopes_disabled(), self.assertNumQueries(7):
            result = cost_recipe(self.recipe, "1", user=self.user)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("15"))
        self.assertEqual(len(result["lines"]), 15)

    def test_preloaded_conversion_preserves_native_order_of_competing_paths(self):
        with scopes_disabled():
            food = self.recipe.steps.get().ingredients.order_by("pk").first().food
            gram = Unit.objects.create(space=self.space, name="g", base_unit="g")
            crate = Unit.objects.create(space=self.space, name="custom-crate")
            case = Unit.objects.create(space=self.space, name="custom-case")
            for base, converted, amount, specific in (
                (gram, crate, "2", food),
                (gram, self.unit, "0.001", None),
                (crate, case, "3", food),
                (self.unit, case, "7", food),
            ):
                UnitConversion.objects.create(
                    space=self.space, food=specific, base_unit=base, converted_unit=converted,
                    base_amount=1, converted_amount=Decimal(amount), created_by=self.user,
                )
            _, recipe_cache, _ = native_recipe_graph([self.recipe.pk], self.space, self.user)
            context = _load_costing_context(recipe_cache, self.space.pk, timezone.now())
            self.assertEqual(convert_native_quantity("1", gram, case, food, self.space), Decimal("6"))
            self.assertEqual(_convert_native_quantity("1", gram, case, food, context), Decimal("6"))
