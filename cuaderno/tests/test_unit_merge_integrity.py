"""Integrity contracts for native Unit merges with professional references."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Ingredient, InventoryEntry, Recipe, SearchFields, Step, Unit, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.models import PurchaseOrder, ServicePlan
from cuaderno.tests.test_purchasing import PurchasingFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UnitMergeIntegrityTests(PurchasingFixtureMixin, TestCase):
    def setUp(self):
        # TransactionTestCase suites can flush migration seed rows before this
        # class runs; native user signals require this canonical row.
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
        super().setUp()

    def _alias(self, name, base_unit="g"):
        return Unit.objects.create(space=self.space, name=name, base_unit=base_unit)

    def _conversion(self, base, converted, base_amount, converted_amount):
        return UnitConversion.objects.create(
            space=self.space,
            base_unit=base,
            converted_unit=converted,
            base_amount=Decimal(base_amount),
            converted_amount=Decimal(converted_amount),
            food=self.food,
            created_by=self.admin,
        )

    def test_endpoint_merge_preserves_inventory_entry_id_amount_and_equivalent_alias(self):
        entry_id = self.entry.pk
        other_entry_id = self.other_entry.pk
        with scopes_disabled():
            alias = self._alias("gramos alias inventario")

        response = self.client_for(self.user).put(
            f"/api/unit/{self.g.pk}/merge/{alias.pk}/", {}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        with scopes_disabled():
            entry = InventoryEntry.objects.get(pk=entry_id)
            other_entry = InventoryEntry.objects.get(pk=other_entry_id)
            self.assertEqual(entry.amount, Decimal("1000"))
            self.assertEqual(entry.unit_id, alias.pk)
            self.assertEqual(other_entry.amount, Decimal("0"))
            self.assertEqual(other_entry.unit_id, alias.pk)
            self.assertFalse(Unit.objects.filter(pk=self.g.pk).exists())

    def test_model_merge_preserves_a_food_specific_conversion_as_an_equivalent_alias(self):
        with scopes_disabled():
            source = self._alias("gramos alias conversión")
            conversion = self._conversion(source, self.kg, "1000", "1")

            source.merge_into(self.g)

            conversion.refresh_from_db()
            self.assertEqual(conversion.base_unit_id, self.g.pk)
            self.assertEqual(conversion.converted_unit_id, self.kg.pk)
            self.assertEqual(conversion.base_amount, Decimal("1000"))
            self.assertEqual(conversion.converted_amount, Decimal("1"))
            self.assertEqual(conversion.food_id, self.food.pk)
            self.assertFalse(Unit.objects.filter(pk=source.pk).exists())

    def test_service_snapshot_is_immutable_even_when_it_is_the_only_source_reference(self):
        with scopes_disabled():
            source = self._alias("gramos congelados servicio")
            plan = ServicePlan.objects.create(
                space=self.space,
                household=self.household,
                title="Servicio con unidad congelada",
                covers=Decimal("4"),
                created_by=self.user,
                service_date=timezone.localdate(),
                state=ServicePlan.CONFIRMED,
                snapshot={"schema_version": 1, "needs": [{"unit_id": source.pk}]},
            )

            with self.assertRaises(DomainError):
                source.merge_into(self.g)

            self.assertTrue(Unit.objects.filter(pk=source.pk).exists())
            plan.refresh_from_db()
            self.assertEqual(plan.snapshot["needs"][0]["unit_id"], source.pk)

    def test_equivalent_duplicate_food_conversion_is_coalesced_without_losing_factor(self):
        with scopes_disabled():
            source = self._alias("gramos conversión duplicada")
            source_edge = self._conversion(source, self.kg, "1000", "1")
            target_edge = self._conversion(self.g, self.kg, "1000", "1")

            source.merge_into(self.g)

            edges = list(UnitConversion.objects.filter(
                space=self.space,
                base_unit=self.g,
                converted_unit=self.kg,
                food=self.food,
            ))
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].pk, target_edge.pk)
            self.assertEqual(edges[0].base_amount, Decimal("1000"))
            self.assertEqual(edges[0].converted_amount, Decimal("1"))
            self.assertFalse(UnitConversion.objects.filter(pk=source_edge.pk).exists())
            self.assertFalse(Unit.objects.filter(pk=source.pk).exists())

    def test_conflicting_duplicate_conversion_rolls_back_units_and_inventory(self):
        with scopes_disabled():
            source = self._alias("gramos conversión incompatible")
            source_edge = self._conversion(source, self.kg, "500", "1")
            target_edge = self._conversion(self.g, self.kg, "1000", "1")
            entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=source,
                amount=Decimal("17.5"),
                created_by=self.admin,
            )

            with self.assertRaises(DomainError):
                source.merge_into(self.g)

            self.assertTrue(Unit.objects.filter(pk=source.pk).exists())
            self.assertTrue(Unit.objects.filter(pk=self.g.pk).exists())
            entry.refresh_from_db()
            source_edge.refresh_from_db()
            target_edge.refresh_from_db()
            self.assertEqual(entry.unit_id, source.pk)
            self.assertEqual(entry.amount, Decimal("17.5"))
            self.assertEqual(source_edge.base_unit_id, source.pk)
            self.assertEqual(source_edge.base_amount, Decimal("500"))
            self.assertEqual(target_edge.base_unit_id, self.g.pk)
            self.assertEqual(target_edge.base_amount, Decimal("1000"))

    def test_inventory_only_merge_rejects_changing_grams_into_kilograms(self):
        entry_id = self.entry.pk
        with scopes_disabled():
            with self.assertRaises(DomainError):
                self.g.merge_into(self.kg)

            self.assertTrue(Unit.objects.filter(pk=self.g.pk).exists())
            entry = InventoryEntry.objects.get(pk=entry_id)
            self.assertEqual(entry.unit_id, self.g.pk)
            self.assertEqual(entry.amount, Decimal("1000"))

    def test_ingredient_only_merge_rejects_relabelling_grams_as_kilograms(self):
        with scopes_disabled():
            source = self._alias("gramos usados solo por ingrediente")
            recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.user,
                name="Receta para integridad de unidad",
                servings=1,
            )
            step = Step.objects.create(space=self.space, instruction="Usar el ingrediente sintético")
            ingredient = Ingredient.objects.create(
                space=self.space,
                food=self.food,
                unit=source,
                amount=Decimal("1000"),
            )
            step.ingredients.add(ingredient)
            recipe.steps.add(step)

            with self.assertRaises(DomainError):
                source.merge_into(self.kg)

            self.assertTrue(Unit.objects.filter(pk=source.pk).exists())
            ingredient.refresh_from_db()
            self.assertEqual(ingredient.unit_id, source.pk)
            self.assertEqual(ingredient.amount, Decimal("1000"))
            self.assertTrue(step.ingredients.filter(pk=ingredient.pk).exists())

    def test_inverse_equivalent_conversions_are_deduplicated_preserving_target_edge(self):
        with scopes_disabled():
            source = self._alias("gramos origen conversión inversa")
            target = self._alias("gramos destino conversión inversa")
            source_edge = self._conversion(source, self.kg, "1000", "1")
            target_edge = self._conversion(self.kg, target, "1", "1000")

            source.merge_into(target)

            edges = list(UnitConversion.objects.filter(
                space=self.space,
                food=self.food,
            ).filter(base_unit__in=[target, self.kg], converted_unit__in=[target, self.kg]))
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].pk, target_edge.pk)
            self.assertEqual(edges[0].base_unit_id, self.kg.pk)
            self.assertEqual(edges[0].converted_unit_id, target.pk)
            self.assertEqual(edges[0].base_amount, Decimal("1"))
            self.assertEqual(edges[0].converted_amount, Decimal("1000"))
            self.assertFalse(UnitConversion.objects.filter(pk=source_edge.pk).exists())
            self.assertFalse(Unit.objects.filter(pk=source.pk).exists())

    def test_inverse_contradictory_conversions_abort_and_roll_back_both_edges(self):
        with scopes_disabled():
            source = self._alias("gramos origen conversión inversa conflictiva")
            target = self._alias("gramos destino conversión inversa conflictiva")
            source_edge = self._conversion(source, self.kg, "1000", "1")
            target_edge = self._conversion(self.kg, target, "1", "2000")

            with self.assertRaises(DomainError):
                source.merge_into(target)

            self.assertTrue(Unit.objects.filter(pk=source.pk).exists())
            self.assertTrue(Unit.objects.filter(pk=target.pk).exists())
            source_edge.refresh_from_db()
            target_edge.refresh_from_db()
            self.assertEqual(source_edge.base_unit_id, source.pk)
            self.assertEqual(source_edge.converted_unit_id, self.kg.pk)
            self.assertEqual(source_edge.base_amount, Decimal("1000"))
            self.assertEqual(source_edge.converted_amount, Decimal("1"))
            self.assertEqual(target_edge.base_unit_id, self.kg.pk)
            self.assertEqual(target_edge.converted_unit_id, target.pk)
            self.assertEqual(target_edge.base_amount, Decimal("1"))
            self.assertEqual(target_edge.converted_amount, Decimal("2000"))

    def test_purchase_order_unit_snapshots_block_alias_merge_and_preserve_identity(self):
        with scopes_disabled():
            source = self._alias("gramos congelados pedido")
            order = PurchaseOrder.objects.create(
                space=self.space,
                household=self.household,
                food=self.food,
                unit=source,
                quantity=Decimal("5"),
                supplier=self.supplier,
                package=self.package,
                package_count=Decimal("1"),
                package_quantity_snapshot=Decimal("5"),
                package_unit_snapshot=source,
                price_snapshot=Decimal("12.50"),
                created_by=self.user,
            )

            with self.assertRaises(DomainError):
                source.merge_into(self.g)

            self.assertTrue(Unit.objects.filter(pk=source.pk).exists())
            order.refresh_from_db()
            self.assertEqual(order.unit_id, source.pk)
            self.assertEqual(order.package_unit_snapshot_id, source.pk)
            self.assertEqual(order.package_quantity_snapshot, Decimal("5"))
