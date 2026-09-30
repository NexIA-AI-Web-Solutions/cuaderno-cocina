"""Declared-yield loss is a frozen classification, not a second stock debit."""

from copy import deepcopy
from decimal import Decimal

from django.test import TestCase, override_settings
from django_scopes import scopes_disabled

from cookbook.models import Food, Ingredient, InventoryEntry, InventoryLocation, Recipe, Space, Step, Unit
from cuaderno.models import RecipeYield, ServicePlan, SpaceProfile, StockMovement
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductionWasteClassificationTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save(update_fields=["edition"])
            self.ingredient = self.recipe.steps.get().ingredients.get()
            self.ingredient.amount = Decimal("0.5")
            self.ingredient.quantity_basis = "net_usable"
            self.ingredient.yield_ratio = Decimal("0.8")
            self.ingredient.save(update_fields=["amount", "quantity_basis", "yield_ratio"])
            location = InventoryLocation.objects.create(
                space=self.space, household=self.household, name="Classification stock", created_by=self.user,
            )
            self.entry = InventoryEntry.objects.create(
                space=self.space, inventory_location=location, food=self.food, unit=self.kg,
                amount=Decimal("5"), created_by=self.user,
            )

    def confirmed(self):
        _, plan = self.create_plan(covers=10)
        response = self.transition(plan, "confirm")
        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        return plan

    def produce(self, plan, key="classification-production"):
        response = self.transition(plan, "produce", key=key)
        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertIn("waste_classification", plan.snapshot["production"])
        return plan.snapshot["production"]["waste_classification"]

    def assert_quantities(self, row, purchased, useful, waste):
        self.assertEqual(Decimal(row["purchased_quantity"]), Decimal(purchased))
        self.assertEqual(Decimal(row["useful_quantity"]), Decimal(useful))
        self.assertEqual(Decimal(row["waste_quantity"]), Decimal(waste))

    def test_net_yield_freezes_identity_and_classifies_without_second_debit(self):
        with scopes_disabled():
            plan = self.confirmed()
            self.ingredient.amount = Decimal("4")
            self.ingredient.yield_ratio = Decimal("0.5")
            self.ingredient.save(update_fields=["amount", "yield_ratio"])
            self.food.name = "Nombre posterior"
            self.food.save(update_fields=["name"])
            document = self.produce(plan)
            self.assertEqual(document["policy"], "declared_yield_estimate")
            self.assertTrue(document["classification_only"])
            self.assertTrue(document["included_in_gross_needs"])
            self.assertFalse(document["additional_stock_movement"])
            self.assertEqual(document["coverage"], "declared_yields_only")
            self.assertEqual(document["recorded_by"], self.user.pk)
            self.assertEqual(document["recorded_at"], plan.produced_at.isoformat())
            self.assertEqual(len(document["lines"]), 1)
            row = document["lines"][0]
            self.assertEqual((row["food_id"], row["food_name"]), (self.food.pk, "Arroz"))
            self.assertEqual((row["unit_id"], row["unit_name"]), (self.kg.pk, "kg"))
            self.assertEqual(row["cause"], "declared_yield")
            self.assert_quantities(row, "0.625", "0.5", "0.125")
            self.assertEqual(self.entry.amount, Decimal("4.375"))
            self.assertEqual(StockMovement.objects.filter(kind=StockMovement.CONSUME).count(), 1)
            self.assertFalse(StockMovement.objects.filter(kind=StockMovement.WASTE).exists())

    def test_gross_yield_does_not_inflate_purchase_or_debit(self):
        with scopes_disabled():
            self.ingredient.quantity_basis = "gross"
            self.ingredient.save(update_fields=["quantity_basis"])
            document = self.produce(self.confirmed())
            self.assert_quantities(document["lines"][0], "0.5", "0.4", "0.1")
            self.assertEqual(self.entry.amount, Decimal("4.5"))

    def test_replay_and_complete_reversal_preserve_classification(self):
        with scopes_disabled():
            plan = self.confirmed()
            frozen = deepcopy(self.produce(plan))
            self.assertEqual(self.produce(plan), frozen)
            self.assertEqual(StockMovement.objects.count(), 1)
            self.assertEqual(self.transition(plan, "produce", key="different-key").status_code, 409)
            response = self.transition(plan, "reverse", key="classification-reversal")
            self.assertEqual(response.status_code, 200, response.data)
            plan.refresh_from_db()
            self.entry.refresh_from_db()
            self.assertEqual(plan.snapshot["production"]["waste_classification"], frozen)
            self.assertEqual(plan.state, ServicePlan.CANCELLED)
            self.assertEqual(self.entry.amount, Decimal("5"))
            self.assertEqual(StockMovement.objects.count(), 2)

    def test_unknown_yield_is_not_reported_as_zero_loss(self):
        with scopes_disabled():
            self.ingredient.quantity_basis = "gross"
            self.ingredient.yield_ratio = None
            self.ingredient.save(update_fields=["quantity_basis", "yield_ratio"])
            document = self.produce(self.confirmed())
            self.assertEqual(document["lines"], [])
            self.assertEqual(document["status"], "unknown")
            self.assertNotIn("total_waste", document)
            self.assertEqual(self.entry.amount, Decimal("4.5"))

    def test_legacy_trace_does_not_invent_historical_food_or_unit_labels(self):
        with scopes_disabled():
            plan = self.confirmed()
            for field in ("food_id", "food_name", "unit_id", "unit_name"):
                plan.snapshot["ingredient_yields"][0].pop(field, None)
            plan.save(update_fields=["snapshot"])
            document = self.produce(plan)
            self.assertEqual(document["status"], "incomplete")
            row = document["lines"][0]
            self.assertTrue(all(row[field] is None for field in ("food_id", "food_name", "unit_id", "unit_name")))
            self.assert_quantities(row, "0.625", "0.5", "0.125")

    def test_corrupt_frozen_loss_rolls_back_entire_production(self):
        with scopes_disabled():
            plan = self.confirmed()
            plan.snapshot["ingredient_yields"][0]["waste_quantity"] = "99"
            plan.save(update_fields=["snapshot"])
            response = self.transition(plan, "produce", key="corrupt-classification")
            self.assertEqual(response.status_code, 400, response.data)
            plan.refresh_from_db()
            self.entry.refresh_from_db()
            self.assertEqual(plan.state, ServicePlan.CONFIRMED)
            self.assertEqual(self.entry.amount, Decimal("5"))
            self.assertFalse(StockMovement.objects.exists())

    def test_quantities_matching_difference_but_not_ratio_are_rejected_before_stock(self):
        with scopes_disabled():
            for basis, purchased, useful, waste in (
                ("gross", "0.5", "0.45", "0.05"),
                ("net_usable", "0.75", "0.5", "0.25"),
            ):
                with self.subTest(basis=basis):
                    self.ingredient.quantity_basis = basis
                    self.ingredient.save(update_fields=["quantity_basis"])
                    plan = self.confirmed()
                    trace = plan.snapshot["ingredient_yields"][0]
                    trace.update(purchased_quantity=purchased, useful_quantity=useful, waste_quantity=waste)
                    plan.save(update_fields=["snapshot"])
                    response = self.transition(plan, "produce", key=f"corrupt-ratio-{basis}")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.entry.refresh_from_db()
                    plan.refresh_from_db()
                    self.assertEqual(self.entry.amount, Decimal("5"))
                    self.assertEqual(plan.state, ServicePlan.CONFIRMED)
                    self.assertFalse(StockMovement.objects.exists())

    def test_foreign_header_and_no_amount_units_are_rejected_before_confirmation(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="Foreign classification graph")
            foreign_unit = Unit.objects.create(space=foreign_space, name="Secret foreign unit")
            for field in ("is_header", "no_amount"):
                with self.subTest(field=field):
                    setattr(self.ingredient, field, True)
                    self.ingredient.unit = foreign_unit
                    self.ingredient.save(update_fields=[field, "unit"])
                    _, plan = self.create_plan(covers=10)
                    response = self.transition(plan, "confirm")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertNotIn(foreign_unit.name, str(response.data))
                    plan.refresh_from_db()
                    self.assertEqual(plan.state, ServicePlan.DRAFT)
                    self.assertFalse(StockMovement.objects.exists())
                    setattr(self.ingredient, field, False)
                    self.ingredient.unit = self.kg
                    self.ingredient.save(update_fields=[field, "unit"])

    def test_subrecipe_leaf_loss_is_classified_once(self):
        with scopes_disabled():
            child = Recipe.objects.create(space=self.space, name="Child loss", servings=1, created_by=self.user)
            child_step = Step.objects.create(space=self.space, name="Child preparation")
            child_step.ingredients.add(self.ingredient)
            child.steps.add(child_step)
            RecipeYield.objects.create(space=self.space, recipe=child, quantity=1, unit=self.kg, updated_by=self.user)
            child_food = Food.objects.create(space=self.space, name="Child preparation food", recipe=child)
            root_step = self.recipe.steps.get()
            root_step.ingredients.clear()
            root_step.ingredients.add(Ingredient.objects.create(space=self.space, food=child_food, unit=self.kg, amount=1))
            document = self.produce(self.confirmed())
            self.assertEqual(len(document["lines"]), 1)
            self.assert_quantities(document["lines"][0], "0.625", "0.5", "0.125")
            self.assertEqual(self.entry.amount, Decimal("4.375"))
            self.assertEqual(StockMovement.objects.count(), 1)

    def test_explicit_full_yield_is_known_zero_not_unknown(self):
        with scopes_disabled():
            self.ingredient.yield_ratio = Decimal("1")
            self.ingredient.save(update_fields=["yield_ratio"])
            document = self.produce(self.confirmed())
            self.assertEqual(document["status"], "declared")
            self.assert_quantities(document["lines"][0], "0.5", "0.5", "0")

    def test_reused_subrecipe_keeps_each_declared_yield_trace_and_consumes_gross_once(self):
        with scopes_disabled():
            child = Recipe.objects.create(space=self.space, name="Repeated child", servings=1, created_by=self.user)
            child_step = Step.objects.create(space=self.space, name="Repeated leaf")
            child_step.ingredients.add(self.ingredient)
            child.steps.add(child_step)
            RecipeYield.objects.create(space=self.space, recipe=child, quantity=1, unit=self.kg, updated_by=self.user)
            child_food = Food.objects.create(space=self.space, name="Repeated child food", recipe=child)
            root_step = self.recipe.steps.get()
            root_step.ingredients.clear()
            for amount in ("1", "2"):
                root_step.ingredients.add(Ingredient.objects.create(
                    space=self.space, food=child_food, unit=self.kg, amount=Decimal(amount),
                ))
            document = self.produce(self.confirmed())
            rows = document["lines"]
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["ingredient_id"] for row in rows], [self.ingredient.pk, self.ingredient.pk])
            self.assert_quantities(rows[0], "0.625", "0.5", "0.125")
            self.assert_quantities(rows[1], "1.25", "1", "0.25")
            self.assertEqual(self.entry.amount, Decimal("3.125"))
            self.assertEqual(StockMovement.objects.count(), 1)
            self.assertFalse(StockMovement.objects.filter(kind=StockMovement.WASTE).exists())

    def test_professional_classification_does_not_claim_any_stock_debit(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.PROFESIONAL
            self.profile.save(update_fields=["edition"])
            document = self.produce(self.confirmed())
            self.assertTrue(document["included_in_gross_needs"])
            self.assertFalse(document["additional_stock_movement"])
            self.assert_quantities(document["lines"][0], "0.625", "0.5", "0.125")
            self.assertEqual(self.entry.amount, Decimal("5"))
            self.assertFalse(StockMovement.objects.exists())

    def test_replay_rejects_a_corrupt_persisted_classification(self):
        with scopes_disabled():
            plan = self.confirmed()
            self.produce(plan)
            plan.snapshot["production"]["waste_classification"]["additional_stock_movement"] = True
            plan.save(update_fields=["snapshot"])
            response = self.transition(plan, "produce", key="classification-production")
            self.assertEqual(response.status_code, 400, response.data)
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("4.375"))
            self.assertEqual(StockMovement.objects.count(), 1)

    def test_corrupt_classification_cannot_reverse_or_replay_a_reversal(self):
        with scopes_disabled():
            for already_reversed in (False, True):
                with self.subTest(already_reversed=already_reversed):
                    plan = self.confirmed()
                    self.produce(plan, key=f"corrupt-reverse-produce-{already_reversed}")
                    key = f"corrupt-reverse-{already_reversed}"
                    if already_reversed:
                        response = self.transition(plan, "reverse", key=key)
                        self.assertEqual(response.status_code, 200, response.data)
                        plan.refresh_from_db()
                    plan.snapshot["production"]["waste_classification"]["additional_stock_movement"] = True
                    plan.save(update_fields=["snapshot"])
                    before = deepcopy(plan.snapshot)
                    before_state = plan.state
                    self.entry.refresh_from_db()
                    before_balance = self.entry.amount
                    before_movements = list(StockMovement.objects.order_by("pk").values())
                    response = self.transition(plan, "reverse", key=key)
                    self.assertEqual(response.status_code, 400, response.data)
                    plan.refresh_from_db()
                    self.entry.refresh_from_db()
                    self.assertEqual(plan.state, before_state)
                    self.assertEqual(plan.snapshot, before)
                    self.assertEqual(self.entry.amount, before_balance)
                    self.assertEqual(list(StockMovement.objects.order_by("pk").values()), before_movements)

    def test_classification_without_new_schema_marker_is_not_legacy(self):
        with scopes_disabled():
            plan = self.confirmed()
            self.produce(plan)
            plan.snapshot["production"].pop("schema_version")
            plan.save(update_fields=["snapshot"])
            before = deepcopy(plan.snapshot)
            response = self.transition(plan, "produce", key="classification-production")
            self.assertEqual(response.status_code, 400, response.data)
            plan.refresh_from_db()
            self.entry.refresh_from_db()
            self.assertEqual(plan.snapshot, before)
            self.assertEqual(self.entry.amount, Decimal("4.375"))
            self.assertEqual(StockMovement.objects.count(), 1)
