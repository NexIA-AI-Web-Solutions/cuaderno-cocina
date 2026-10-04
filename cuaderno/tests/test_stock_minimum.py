"""Integral stock-minimum metadata and replenishment contracts."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, InventoryEntry, InventoryLocation, Space, Unit
from cuaderno.models import PurchaseOrder, ServicePlan, SpaceProfile, StockMinimum
from cuaderno.domain.errors import DomainError
from cuaderno.tests.test_purchasing import PurchasingFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StockMinimumApiTests(PurchasingFixtureMixin, TestCase):
    url = "/api/cuaderno/stock-minimums/"

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(
            response.get("Content-Type", "").startswith("application/json"),
            "Stock-minimum API is missing; the HTML SPA fallback is not an API.",
        )

    def put_minimum(self, quantity="2", *, client=None, food=None, unit=None, location=None):
        return (client or self.client_for(self.user)).put(
            self.url,
            {
                "food": (food or self.food).pk,
                "unit": (unit or self.kg).pk,
                "quantity": quantity,
                "location": location,
            },
            format="json",
        )

    def items(self, response):
        self.assert_json(response)
        self.assertEqual(response.data["edition"], SpaceProfile.INTEGRAL)
        return response.data["items"]

    def test_get_is_household_scoped_admin_can_select_and_repeated_put_is_upsert(self):
        first = self.put_minimum("2")
        self.assert_json(first)
        second = self.put_minimum("3")
        rows = self.items(second)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["food"], self.food.pk)
        self.assertEqual(rows[0]["household"], self.household.pk)
        self.assertEqual(rows[0]["unit"], self.kg.pk)
        self.assertEqual(Decimal(rows[0]["quantity"]), Decimal("3"))
        self.assertIsNone(rows[0]["location"])

        self.assertEqual(self.items(self.client_for(self.outsider).get(self.url)), [])
        selected = self.client_for(self.admin).get(f"{self.url}?household={self.other_household.pk}")
        self.assertEqual(self.items(selected), [])
        denied = self.client_for(self.user).get(f"{self.url}?household={self.other_household.pk}")
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(first.data["household"], {"id": self.household.pk, "name": self.household.name})
        self.assertEqual(first.data["locations"], [{"id": self.location.pk, "name": self.location.name}])

    def test_quantity_is_strict_positive_decimal_string_and_null_removes(self):
        for invalid in (True, 1, 1.5, [], {}, "", "0", "-1", "NaN", "Infinity", "0.12345678901234567"):
            with self.subTest(invalid=invalid):
                self.assert_json(self.put_minimum(invalid), 400)
        self.assert_json(self.put_minimum("0.1234567890123456"))
        removed = self.put_minimum(None)
        self.assertEqual(self.items(removed), [])

        for field, invalid in (("food", True), ("unit", [self.kg.pk]), ("location", {})):
            payload = {"food": self.food.pk, "unit": self.kg.pk, "quantity": "1", "location": None}
            payload[field] = invalid
            response = self.client_for(self.user).put(self.url, payload, format="json")
            self.assert_json(response, 400)

    def test_guest_reads_own_household_and_non_integral_profiles_cannot_read_or_write(self):
        guest = self.client_for(self.guest)
        self.assert_json(guest.get(self.url), 200)
        self.assert_json(self.put_minimum(client=guest), 403)
        with scopes_disabled():
            profile = SpaceProfile.objects.get(space=self.space)
            profile.edition = SpaceProfile.PROFESIONAL
            profile.save(update_fields=["edition"])
        user = self.client_for(self.user)
        self.assert_json(user.get(self.url), 403)
        self.assert_json(self.put_minimum(client=user), 403)

    def test_foreign_food_unit_and_other_household_location_are_not_found(self):
        other_location_id = self.other_entry.inventory_location_id
        self.assert_json(self.put_minimum(location=other_location_id), 404)
        with scopes_disabled():
            other_space = Space.objects.create(name="Foreign minimum space")
            other_food = Food.objects.create(space=other_space, name="Foreign food")
            other_unit = Unit.objects.create(space=other_space, name="foreign kg", base_unit="kg")
        self.assert_json(self.put_minimum(food=other_food), 404)
        self.assert_json(self.put_minimum(unit=other_unit), 404)

    def test_global_and_location_minimums_for_same_food_cannot_coexist(self):
        self.assert_json(self.put_minimum("2"))
        self.assert_json(self.put_minimum("2", location=self.location.pk), 409)
        self.assert_json(self.put_minimum(None))
        self.assert_json(self.put_minimum("2", location=self.location.pk))
        self.assert_json(self.put_minimum("2"), 409)

    def test_food_without_services_replenishes_minimum_with_conversion_expiry_and_package_ceiling(self):
        with scopes_disabled():
            InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("100"),
                expires=date.today() - timedelta(days=1),
                created_by=self.admin,
            )
        self.assert_json(self.put_minimum("1250", unit=self.g))
        before = self.entry.amount
        result = self.client_for(self.user).post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_json(result)
        self.assertEqual(len(result.data["items"]), 1)
        item = result.data["items"][0]
        self.assertEqual(Decimal(item["required"]), Decimal("0"))
        self.assertEqual(Decimal(item["minimum_stock"]), Decimal("1.25"))
        self.assertEqual(Decimal(item["target_stock"]), Decimal("1.25"))
        self.assertEqual(Decimal(item["usable_stock"]), Decimal("1"))
        self.assertEqual(Decimal(item["missing"]), Decimal("0.25"))
        self.assertEqual(Decimal(item["packages"]), Decimal("1"))
        self.assertEqual(Decimal(item["purchase_quantity"]), Decimal("5"))
        self.assertIsNone(item["reference_price"])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, before)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_confirmed_requirement_adds_to_global_minimum_without_writing_stock_or_order(self):
        with scopes_disabled():
            ServicePlan.objects.create(
                space=self.space,
                household=self.household,
                title="Synthetic minimum service",
                covers=1,
                created_by=self.user,
                service_date=timezone.localdate(),
                state=ServicePlan.CONFIRMED,
                snapshot={
                    "schema_version": 2,
                    "needs": [{
                        "food_id": self.food.pk,
                        "food_name": self.food.name,
                        "unit_id": self.kg.pk,
                        "unit_name": "kg",
                        "quantity": "3",
                    }],
                },
            )
        self.assert_json(self.put_minimum("2"))
        before = self.entry.amount
        response = self.client_for(self.user).post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_json(response)
        item = response.data["items"][0]
        self.assertEqual(Decimal(item["required"]), Decimal("3"))
        self.assertEqual(Decimal(item["minimum_stock"]), Decimal("2"))
        self.assertEqual(Decimal(item["target_stock"]), Decimal("5"))
        self.assertEqual(Decimal(item["usable_stock"]), Decimal("1"))
        self.assertEqual(Decimal(item["missing"]), Decimal("4"))
        self.assertEqual(Decimal(item["packages"]), Decimal("1"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, before)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_location_shortfall_forces_replenishment_despite_excess_elsewhere(self):
        with scopes_disabled():
            overflow = InventoryLocation.objects.create(
                space=self.space, household=self.household, name="Overflow", created_by=self.admin,
            )
            InventoryEntry.objects.create(
                space=self.space,
                inventory_location=overflow,
                food=self.food,
                unit=self.kg,
                amount=Decimal("10"),
                created_by=self.admin,
            )
        self.assert_json(self.put_minimum("3", location=self.location.pk))
        response = self.client_for(self.user).post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_json(response)
        item = response.data["items"][0]
        self.assertEqual(Decimal(item["usable_stock"]), Decimal("11"))
        self.assertEqual(Decimal(item["minimum_stock"]), Decimal("3"))
        self.assertEqual(Decimal(item["missing"]), Decimal("2"))
        self.assertEqual(Decimal(item["packages"]), Decimal("1"))
        self.assertEqual(len(item["location_shortfalls"]), 1)
        shortage = item["location_shortfalls"][0]
        self.assertEqual(shortage["location"], self.location.pk)
        self.assertEqual(Decimal(shortage["minimum_stock"]), Decimal("3"))
        self.assertEqual(Decimal(shortage["usable_stock"]), Decimal("1"))
        self.assertEqual(Decimal(shortage["missing"]), Decimal("2"))

    def test_multiple_location_deficits_are_summed_and_required_target_can_dominate(self):
        with scopes_disabled():
            second = InventoryLocation.objects.create(space=self.space, household=self.household, name="Second", created_by=self.admin)
            overflow = InventoryLocation.objects.create(space=self.space, household=self.household, name="Overflow", created_by=self.admin)
            for location, amount in ((second, "0.5"), (overflow, "20")):
                InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food, unit=self.kg, amount=Decimal(amount), created_by=self.admin)
            plan = ServicePlan.objects.create(
                space=self.space, household=self.household, title="Two reserves", covers=1, created_by=self.user,
                state=ServicePlan.CONFIRMED, snapshot={"needs": [{"food_id": self.food.pk, "unit_id": self.kg.pk, "quantity": "10"}]},
            )
        self.assert_json(self.put_minimum("3", location=self.location.pk))
        self.assert_json(self.put_minimum("2", location=second.pk))
        client = self.client_for(self.user)
        first = client.post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_json(first)
        row = first.data["items"][0]
        self.assertEqual(Decimal(row["minimum_stock"]), Decimal("5"))
        self.assertEqual(Decimal(row["usable_stock"]), Decimal("21.5"))
        self.assertEqual(Decimal(row["missing"]), Decimal("3.5"))
        self.assertEqual(len(row["location_shortfalls"]), 2)
        with scopes_disabled():
            plan.snapshot["needs"][0]["quantity"] = "30"
            plan.save(update_fields=["snapshot"])
        second_response = client.post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_json(second_response)
        row = second_response.data["items"][0]
        self.assertEqual(Decimal(row["target_stock"]), Decimal("35"))
        self.assertEqual(Decimal(row["missing"]), Decimal("13.5"))
        self.assertEqual(Decimal(row["packages"]), Decimal("3"))

    def test_database_rejects_zero_and_duplicate_global_metadata(self):
        self.assert_json(self.put_minimum("2"))
        kwargs = dict(space=self.space, household=self.household, food=self.food, unit=self.kg, updated_by=self.user)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            StockMinimum.objects.create(**kwargs, quantity=0)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            StockMinimum.objects.create(**kwargs, quantity=3)

    def test_model_food_merge_preserves_minimum_and_rejects_scope_collision(self):
        self.assert_json(self.put_minimum("2"))
        with scopes_disabled():
            target = Food.add_root(space=self.space, name="Merge target minimum")
            self.food.merge_into(target)
        rows = self.items(self.client_for(self.user).get(self.url))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["food"], target.pk)
        self.assertEqual(Decimal(rows[0]["quantity"]), Decimal("2"))
        with scopes_disabled():
            source = Food.add_root(space=self.space, name="Merge conflict minimum")
            StockMinimum.objects.create(space=self.space, household=self.household, food=source, unit=self.kg, quantity=3, updated_by=self.user)
            with self.assertRaises(DomainError):
                source.merge_into(target)
            self.assertTrue(Food.objects.filter(pk=source.pk).exists())
            self.assertEqual(StockMinimum.objects.filter(food__in=[source, target]).count(), 2)

    def test_endpoint_merge_cannot_mix_global_and_location_reserves(self):
        self.assert_json(self.put_minimum("2"))
        with scopes_disabled():
            target = Food.add_root(space=self.space, name="Merge location target")
            StockMinimum.objects.create(space=self.space, household=self.household, food=target, unit=self.kg, location=self.location, quantity=3, updated_by=self.user)
        response = self.client_for(self.user).put(f"/api/food/{self.food.pk}/merge/{target.pk}/", {}, format="json")
        self.assertIn(response.status_code, (400, 409), response.content)
        with scopes_disabled():
            self.assertTrue(Food.objects.filter(pk=self.food.pk).exists())
            self.assertEqual(StockMinimum.objects.filter(food__in=[self.food, target]).count(), 2)

    def test_unit_model_merge_preserves_alias_quantity_and_rejects_scale_change(self):
        self.assert_json(self.put_minimum("2"))
        with scopes_disabled():
            alias = Unit.objects.create(space=self.space, name="kilogramos", base_unit="kg")
            self.kg.merge_into(alias)
            minimum = StockMinimum.objects.get(food=self.food)
            self.assertEqual(minimum.unit_id, alias.pk)
            self.assertEqual(minimum.quantity, Decimal("2"))
            with self.assertRaises(DomainError):
                alias.merge_into(self.g)
            minimum.refresh_from_db()
            self.assertEqual(minimum.unit_id, alias.pk)
            self.assertTrue(Unit.objects.filter(pk=alias.pk).exists())

    def test_unit_endpoint_cannot_relabel_minimum_kilograms_as_grams(self):
        self.assert_json(self.put_minimum("2"))
        response = self.client_for(self.user).put(f"/api/unit/{self.kg.pk}/merge/{self.g.pk}/", {}, format="json")
        self.assertIn(response.status_code, (400, 409), response.content)
        with scopes_disabled():
            self.assertEqual(StockMinimum.objects.get(food=self.food).unit_id, self.kg.pk)
            self.assertTrue(Unit.objects.filter(pk=self.kg.pk).exists())
