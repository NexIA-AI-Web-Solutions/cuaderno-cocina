"""Ordinary ingredients reuse native food-specific UnitConversion rows for density."""

from decimal import Decimal, localcontext

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, Ingredient, Recipe, Space, Step, Unit, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.models import PackageFormat, PriceVersion
from cuaderno.services.costing import cost_recipe
from cuaderno.services.subrecipes import convert_native_quantity


class NativeFoodDensityCostTests(TestCase):
    def setUp(self):
        with scopes_disabled():
            self.user = get_user_model().objects.create_user(username="density-cost-owner")
            self.space = Space.objects.create(name="Densidades sintéticas", created_by=self.user)
            self.grams = Unit.objects.create(space=self.space, name="g", base_unit="g")
            self.millilitres = Unit.objects.create(space=self.space, name="mL", base_unit="ml")
            self.food = Food.add_root(space=self.space, name="Aceite con densidad")
            self.recipe, self.ingredient = self._recipe_with_ingredient(
                self.food, self.millilitres, "400", "Uso en volumen"
            )
            self.package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.grams,
                label="Formato 5 kg",
                quantity=Decimal("5000"),
                is_reference=True,
            )
            self.price = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("32"),
                valid_from=timezone.now(),
                created_by=self.user,
            )
            self.density = UnitConversion.objects.create(
                space=self.space,
                food=self.food,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.user,
            )

    def _recipe_with_ingredient(self, food, unit, amount, name):
        recipe = Recipe.objects.create(
            space=self.space,
            name=name,
            servings=1,
            created_by=self.user,
        )
        step = Step.objects.create(space=self.space, instruction="Preparar")
        ingredient = Ingredient.objects.create(
            space=self.space,
            food=food,
            unit=unit,
            amount=Decimal(amount),
        )
        step.ingredients.add(ingredient)
        recipe.steps.add(step)
        return recipe, ingredient

    def _cost(self, recipe=None):
        with scopes_disabled():
            return cost_recipe(recipe or self.recipe, "1", user=self.user)

    def test_food_density_costs_plain_ingredient_exactly_and_changes_no_persisted_snapshot(self):
        before = {
            "ingredient": (self.ingredient.amount, self.ingredient.unit_id, self.ingredient.food_id),
            "package": (self.package.quantity, self.package.unit_id, self.package.food_id),
            "price": (self.price.amount, self.price.valid_from),
            "density": (
                self.density.base_amount,
                self.density.base_unit_id,
                self.density.converted_amount,
                self.density.converted_unit_id,
                self.density.food_id,
            ),
        }
        with scopes_disabled(), CaptureQueriesContext(connection) as captured:
            result = cost_recipe(self.recipe, "1", user=self.user)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("2.3552"))
        self.assertEqual(Decimal(result["display"]), Decimal("2.36"))
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in captured.captured_queries))
        self.ingredient.refresh_from_db()
        self.package.refresh_from_db()
        self.price.refresh_from_db()
        self.density.refresh_from_db()
        self.assertEqual(
            {
                "ingredient": (self.ingredient.amount, self.ingredient.unit_id, self.ingredient.food_id),
                "package": (self.package.quantity, self.package.unit_id, self.package.food_id),
                "price": (self.price.amount, self.price.valid_from),
                "density": (
                    self.density.base_amount,
                    self.density.base_unit_id,
                    self.density.converted_amount,
                    self.density.converted_unit_id,
                    self.density.food_id,
                ),
            },
            before,
        )

    def test_food_density_is_reversible_for_mass_ingredient_and_volume_package(self):
        with scopes_disabled():
            reverse_food = Food.add_root(space=self.space, name="Aceite inverso")
            recipe, _ingredient = self._recipe_with_ingredient(reverse_food, self.grams, "368", "Uso en masa")
            package = PackageFormat.objects.create(
                space=self.space,
                food=reverse_food,
                unit=self.millilitres,
                label="Formato 5 L",
                quantity=Decimal("5000"),
                is_reference=True,
            )
            PriceVersion.objects.create(
                space=self.space,
                package=package,
                amount=Decimal("32"),
                valid_from=timezone.now(),
                created_by=self.user,
            )
            UnitConversion.objects.create(
                space=self.space,
                food=reverse_food,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.user,
            )

        result = self._cost(recipe)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("2.56"))
        self.assertEqual(Decimal(result["display"]), Decimal("2.56"))

    def test_other_food_and_global_cross_dimension_conversions_are_not_density(self):
        with scopes_disabled():
            self.density.delete()
            other = Food.add_root(space=self.space, name="Otro alimento")
            UnitConversion.objects.create(
                space=self.space,
                food=other,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.user,
            )
            UnitConversion.objects.create(
                space=self.space,
                food=None,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.user,
            )

        result = self._cost()
        self.assertEqual(result["status"], "needs_conversion")
        self.assertIsNone(result["total"])
        self.assertIsNone(result["lines"][0]["unrounded"])
        self.price.refresh_from_db()
        self.assertEqual(self.price.amount, Decimal("32"))

    def test_zero_or_negative_conversion_ratio_is_unknown_and_never_zero_cost(self):
        for base_amount, converted_amount in (("0", "1000"), ("920", "0"), ("-920", "1000")):
            with self.subTest(base_amount=base_amount, converted_amount=converted_amount), scopes_disabled():
                self.density.base_amount = Decimal(base_amount)
                self.density.converted_amount = Decimal(converted_amount)
                self.density.save(update_fields=["base_amount", "converted_amount"])
                result = cost_recipe(self.recipe, "1", user=self.user)
                self.assertEqual(result["status"], "needs_conversion")
                self.assertIsNone(result["total"])
                self.assertIsNone(result["lines"][0]["unrounded"])
                self.assertEqual(PriceVersion.objects.get(pk=self.price.pk).amount, Decimal("32"))

    def test_foreign_space_and_corrupt_cross_space_units_cannot_supply_density(self):
        with scopes_disabled():
            self.density.delete()
            foreign_space = Space.objects.create(name="Densidad ajena", created_by=self.user)
            foreign_grams = Unit.objects.create(space=foreign_space, name="g ajeno", base_unit="g")
            foreign_millilitres = Unit.objects.create(space=foreign_space, name="mL ajeno", base_unit="ml")
            UnitConversion.objects.create(
                space=foreign_space,
                food=self.food,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.user,
            )
            UnitConversion.objects.create(
                space=self.space,
                food=self.food,
                base_amount=Decimal("920"),
                base_unit=foreign_grams,
                converted_amount=Decimal("1000"),
                converted_unit=foreign_millilitres,
                created_by=self.user,
            )

        result = self._cost()
        self.assertEqual(result["status"], "needs_conversion")
        self.assertIsNone(result["total"])

    def test_density_queries_are_constant_from_ten_to_fifty_plain_ingredients(self):
        with scopes_disabled():
            recipe = Recipe.objects.create(
                space=self.space,
                name="Cincuenta ingredientes densos",
                servings=1,
                created_by=self.user,
            )
            step = Step.objects.create(space=self.space, instruction="Mezclar todos")
            recipe.steps.add(step)

            def add_lines(start, stop):
                for index in range(start, stop):
                    food = Food.add_root(space=self.space, name=f"Denso {index:02d}")
                    ingredient = Ingredient.objects.create(
                        space=self.space,
                        food=food,
                        unit=self.millilitres,
                        amount=Decimal("400"),
                        order=index,
                    )
                    step.ingredients.add(ingredient)
                    package = PackageFormat.objects.create(
                        space=self.space,
                        food=food,
                        unit=self.grams,
                        label=f"Formato {index:02d}",
                        quantity=Decimal("5000"),
                        is_reference=True,
                    )
                    PriceVersion.objects.create(
                        space=self.space,
                        package=package,
                        amount=Decimal("32"),
                        valid_from=timezone.now(),
                        created_by=self.user,
                    )
                    UnitConversion.objects.create(
                        space=self.space,
                        food=food,
                        base_amount=Decimal("920"),
                        base_unit=self.grams,
                        converted_amount=Decimal("1000"),
                        converted_unit=self.millilitres,
                        created_by=self.user,
                    )

            add_lines(0, 10)
            with CaptureQueriesContext(connection) as ten_queries:
                ten = cost_recipe(recipe, "1", user=self.user)
            add_lines(10, 50)
            with CaptureQueriesContext(connection) as fifty_queries:
                fifty = cost_recipe(recipe, "1", user=self.user)

        self.assertEqual(ten["status"], "complete")
        self.assertEqual(Decimal(ten["unrounded"]), Decimal("23.552"))
        self.assertEqual(fifty["status"], "complete")
        self.assertEqual(Decimal(fifty["unrounded"]), Decimal("117.760"))
        self.assertEqual(len(ten_queries), len(fifty_queries))
        self.assertLessEqual(len(fifty_queries), 10)
        self.assertTrue(
            all(query["sql"].lstrip().upper().startswith("SELECT") for query in fifty_queries.captured_queries)
        )

    def test_canonical_mass_conversion_beats_a_conflicting_food_specific_edge(self):
        with scopes_disabled():
            kilograms = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.ingredient.unit = kilograms
            self.ingredient.amount = Decimal("0.4")
            self.ingredient.save(update_fields=["unit", "amount"])
            UnitConversion.objects.create(
                space=self.space, food=self.food, created_by=self.user,
                base_unit=kilograms, base_amount=Decimal("1"),
                converted_unit=self.grams, converted_amount=Decimal("123"),
            )
        result = self._cost()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("2.56"))

    def test_density_uses_gross_after_net_yield_exactly_once(self):
        with scopes_disabled():
            self.ingredient.quantity_basis = "net_usable"
            self.ingredient.yield_ratio = Decimal("0.8")
            self.ingredient.save(update_fields=["quantity_basis", "yield_ratio"])
        result = self._cost()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("2.944"))
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.amount, Decimal("400"))

    def test_unknown_price_is_not_a_free_density_cost(self):
        with scopes_disabled():
            self.price.delete()
        result = self._cost()
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["total"])

    def test_free_price_requires_density_and_invalid_zero_remains_invalid(self):
        with scopes_disabled():
            PriceVersion.objects.filter(pk=self.price.pk).update(amount=Decimal("0"), explicit_free=True)
            result = cost_recipe(self.recipe, "1", user=self.user)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(Decimal(result["total"]), Decimal("0"))
            self.density.delete()
            result = cost_recipe(self.recipe, "1", user=self.user)
            self.assertEqual(result["status"], "needs_conversion")
            self.assertIsNone(result["total"])
            # The persistent price contract rejects non-explicit zero outright.
            with self.assertRaises(IntegrityError), transaction.atomic():
                PriceVersion.objects.filter(pk=self.price.pk).update(explicit_free=False)

    def test_custom_food_format_uses_its_declared_content_not_a_universal_bag(self):
        with scopes_disabled():
            bag = Unit.objects.create(space=self.space, name="bolsa sintética")
            self.ingredient.unit = bag
            self.ingredient.amount = Decimal("2")
            self.ingredient.save(update_fields=["unit", "amount"])
            UnitConversion.objects.create(
                space=self.space, food=self.food, created_by=self.user,
                base_unit=bag, base_amount=Decimal("1"),
                converted_unit=self.grams, converted_amount=Decimal("250"),
            )
        result = self._cost()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("3.2"))

    def test_corrupt_foreign_unit_bridge_does_not_complete_a_local_density(self):
        with scopes_disabled():
            self.density.delete()
            foreign_space = Space.objects.create(name="Puente ajeno", created_by=self.user)
            bridge = Unit.objects.create(space=foreign_space, name="puente de densidad")
            UnitConversion.objects.create(
                space=self.space, food=self.food, created_by=self.user,
                base_unit=self.millilitres, base_amount=Decimal("1000"),
                converted_unit=bridge, converted_amount=Decimal("920"),
            )
            UnitConversion.objects.create(
                space=self.space, food=self.food, created_by=self.user,
                base_unit=bridge, base_amount=Decimal("1"),
                converted_unit=self.grams, converted_amount=Decimal("1"),
            )
        result = self._cost()
        self.assertEqual(result["status"], "needs_conversion")
        self.assertIsNone(result["total"])

    def test_nonfinite_native_density_does_not_crash_or_produce_zero(self):
        # Django rejects NaN inputs. Simulate a corrupt legacy database row,
        # not an accepted API input, in this isolated PostgreSQL test only.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cookbook_unitconversion SET base_amount = 'NaN'::numeric WHERE id = %s",
                [self.density.pk],
            )
        result = self._cost()
        self.assertEqual(result["status"], "needs_conversion")
        self.assertIsNone(result["total"])

    def test_foreign_ingredient_unit_cannot_take_the_canonical_shortcut(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Unidad ingrediente ajena", created_by=self.user)
            foreign_unit = Unit.objects.create(space=foreign, name="g", base_unit="g")
            Ingredient.objects.filter(pk=self.ingredient.pk).update(unit=foreign_unit)
        result = self._cost()
        self.assertEqual(result["status"], "needs_conversion")
        self.assertIsNone(result["total"])

    def test_foreign_package_unit_cannot_supply_a_price_ratio(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Unidad formato ajena", created_by=self.user)
            foreign_unit = Unit.objects.create(space=foreign, name="mL", base_unit="ml")
            PackageFormat.objects.filter(pk=self.package.pk).update(unit=foreign_unit)
        result = self._cost()
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["total"])

    def test_foreign_food_cannot_be_priced_through_a_corrupt_local_package(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Alimento ajeno", created_by=self.user)
            foreign_food = Food.add_root(space=foreign, name="Alimento de otro Space")
            Ingredient.objects.filter(pk=self.ingredient.pk).update(food=foreign_food)
            PackageFormat.objects.filter(pk=self.package.pk).update(food=foreign_food, unit=self.millilitres)
        result = self._cost()
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["total"])

    def test_preloaded_foreign_bridge_is_rejected_by_the_shared_converter(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Puente precargado ajeno", created_by=self.user)
            bridge = Unit.objects.create(space=foreign, name="Puente precargado")
            edges = [
                UnitConversion.objects.create(
                    space=self.space, food=self.food, created_by=self.user,
                    base_unit=self.millilitres, base_amount=Decimal("1000"),
                    converted_unit=bridge, converted_amount=Decimal("920"),
                ),
                UnitConversion.objects.create(
                    space=self.space, food=self.food, created_by=self.user,
                    base_unit=bridge, base_amount=Decimal("1"),
                    converted_unit=self.grams, converted_amount=Decimal("1"),
                ),
            ]
            with self.assertRaises(DomainError):
                convert_native_quantity("400", self.millilitres, self.grams, self.food, self.space, conversions=edges)

    def test_shared_converter_rejects_foreign_endpoints_even_for_the_same_unit(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Extremos ajenos", created_by=self.user)
            foreign_unit = Unit.objects.create(space=foreign, name="g", base_unit="g")
            foreign_food = Food.add_root(space=foreign, name="Food ajeno")
            for source, target, food in (
                (foreign_unit, foreign_unit, self.food),
                (self.grams, self.grams, foreign_food),
            ):
                with self.subTest(source=source.pk, target=target.pk, food=food.pk), self.assertRaises(DomainError):
                    convert_native_quantity("1", source, target, food, self.space)

    def test_conversion_multiplies_valid_32_digit_values_at_64_digit_working_precision(self):
        # (10^16 - 10^-16)^2 / 10^15 = 10^17 - 2*10^-15 + 10^-47.
        # The exact finite result needs 64 digits; do not round its product at28.
        amount = Decimal("9999999999999999.9999999999999999")
        with scopes_disabled():
            UnitConversion.objects.filter(pk=self.density.pk).update(
                base_unit=self.millilitres, base_amount=Decimal("1000000000000000"),
                converted_unit=self.grams, converted_amount=amount,
            )
            self.density.refresh_from_db()
        with localcontext() as outer:
            outer.prec = 28
            result = convert_native_quantity(
                amount, self.millilitres, self.grams, self.food, self.space,
                conversions=[self.density],
            )
            self.assertEqual(outer.prec, 28)
        self.assertEqual(
            result,
            Decimal("99999999999999999.99999999999999800000000000000000000000000000001"),
        )

    def test_recipe_total_and_per_serving_keep_the_exact_finite_line_precision(self):
        amount = Decimal("9999999999999999.9999999999999999")
        expected = Decimal("99999999999999999.99999999999999800000000000000000000000000000001")
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(amount=amount)
            PackageFormat.objects.filter(pk=self.package.pk).update(quantity=Decimal("1000000000000000"))
            PriceVersion.objects.filter(pk=self.price.pk).update(amount=amount)
            UnitConversion.objects.filter(pk=self.density.pk).update(base_amount=Decimal("1"), converted_amount=Decimal("1"))
        result = self._cost()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["lines"][0]["unrounded"]), expected)
        self.assertEqual(Decimal(result["unrounded"]), expected)
        self.assertEqual(Decimal(result["known_subtotal"]), expected)
        self.assertEqual(Decimal(result["per_serving"]), expected)

    def test_shared_canonical_conversion_preserves_all_32_input_digits(self):
        amount = Decimal("9999999999999999.9999999999999999")
        with scopes_disabled():
            kilograms = Unit.objects.create(space=self.space, name="kg precisión", base_unit="kg")
        result = convert_native_quantity(amount, self.grams, kilograms, self.food, self.space)
        self.assertEqual(result, Decimal("9999999999999.9999999999999999999"))
