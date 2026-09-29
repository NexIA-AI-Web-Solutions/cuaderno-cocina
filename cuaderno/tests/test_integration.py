from decimal import Decimal
from threading import Barrier, Lock, Thread

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from cookbook.models import Food, Household, Ingredient, InventoryEntry, InventoryLocation, Recipe, Space, Step, Unit, UserSpace
from cuaderno.models import AllergenDeclaration, PackageFormat, PriceVersion, PurchaseOrder, RecipeExchangeRecord, RecipeYield, SpaceProfile, StockMovement
from cuaderno.services.ledger import IdempotencyConflict, apply_movement, reverse_movement


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CuadernoIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Cocina de pruebas")
            self.admin = self._user("cuaderno-admin", "admin")
            self.user = self._user("cuaderno-user", "user")
            self.guest = self._user("cuaderno-guest", "guest")
            self.space.created_by = self.admin
            self.space.save(update_fields=["created_by"])

            household = Household.objects.create(name="Equipo", space=self.space)
            UserSpace.objects.filter(space=self.space).update(household=household)
            location = InventoryLocation.objects.create(
                name="Almacén",
                household=household,
                created_by=self.admin,
                space=self.space,
            )
            self.location = location
            self.food = Food.objects.create(name="Arroz", space=self.space)
            self.unit = Unit.objects.create(name="kg", space=self.space)
            self.entry = InventoryEntry.objects.create(
                inventory_location=location,
                amount=Decimal("10"),
                food=self.food,
                unit=self.unit,
                created_by=self.admin,
                space=self.space,
            )
            self.other_entry = InventoryEntry.objects.create(
                inventory_location=location,
                amount=Decimal("10"),
                food=self.food,
                unit=self.unit,
                created_by=self.admin,
                space=self.space,
            )
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.INTEGRAL)

    def _user(self, username, group_name):
        user = get_user_model().objects.create_user(username=username, password="local-test-only")
        membership = UserSpace.objects.create(user=user, space=self.space, active=True)
        membership.groups.add(Group.objects.get_or_create(name=group_name)[0])
        return user

    def _client(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_only_admin_can_change_commercial_edition(self):
        response = self._client(self.user).put(
            "/api/cuaderno/edition/",
            {"edition": "profesional", "price_policy": "net"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        response = self._client(self.admin).put(
            "/api/cuaderno/edition/",
            {"edition": "profesional", "price_policy": "net"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_guest_cannot_write_operational_stock(self):
        response = self._client(self.guest).post(
            "/api/cuaderno/movements/",
            {
                "entry": self.entry.id,
                "kind": "receipt",
                "quantity": "1",
                "idempotency_key": "guest-write",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        with scopes_disabled():
            self.assertFalse(StockMovement.objects.filter(idempotency_key="guest-write").exists())

    def test_inventory_isolated_between_households_but_space_admin_can_access(self):
        with scopes_disabled():
            household = Household.objects.create(space=self.space, name="Otro equipo")
            location = InventoryLocation.objects.create(space=self.space, household=household,
                                                        name="Almacén privado del equipo", created_by=self.admin)
            entry = InventoryEntry.objects.create(
                space=self.space, inventory_location=location, food=self.food, unit=self.unit, amount=5, created_by=self.admin,
            )
        client = self._client(self.user)
        self.assertEqual(client.get(f"/api/inventory-entry/{entry.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/inventory-location/{location.pk}/").status_code, 404)
        denied = client.post(
            "/api/cuaderno/movements/", {"entry": entry.pk, "kind": "consume", "quantity": "1", "idempotency_key": "other-team"}, format="json",
        )
        self.assertEqual(denied.status_code, 404)
        denied_location = client.patch(f"/api/inventory-entry/{self.entry.pk}/", {"inventory_location": location.pk},
                                       format="json", HTTP_IDEMPOTENCY_KEY="other-team-location")
        self.assertIn(denied_location.status_code, (400, 404))
        self.assertEqual(self._client(self.admin).get(f"/api/inventory-entry/{entry.pk}/").status_code, 200)
        admin = self._client(self.admin)
        moved = admin.patch(f"/api/inventory-entry/{self.entry.pk}/", {"inventory_location": location.pk},
                            format="json", HTTP_IDEMPOTENCY_KEY="admin-cross-household")
        self.assertEqual(moved.status_code, 400)
        relabelled = admin.patch(f"/api/inventory-location/{self.location.pk}/", {"household": household.pk}, format="json")
        self.assertEqual(relabelled.status_code, 400)

    def test_native_location_creation_accepts_own_household_only(self):
        client = self._client(self.user)
        response = client.post("/api/inventory-location/", {"name": "Nueva ubicación", "household": self.location.household_id}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            household = Household.objects.create(space=self.space, name="Ajeno")
        denied = client.post("/api/inventory-location/", {"name": "No autorizado", "household": household.pk}, format="json")
        self.assertEqual(denied.status_code, 400, denied.data)

    def test_idempotency_fingerprint_includes_the_target_entry(self):
        with scopes_disabled():
            apply_movement(
                entry_id=self.entry.id,
                space=self.space,
                user=self.user,
                kind=StockMovement.RECEIPT,
                quantity="1",
                idempotency_key="same-key",
            )
            with self.assertRaises(IdempotencyConflict):
                apply_movement(
                    entry_id=self.other_entry.id,
                    space=self.space,
                    user=self.user,
                    kind=StockMovement.RECEIPT,
                    quantity="1",
                    idempotency_key="same-key",
                )

    def test_semantically_equal_decimal_replay_is_idempotent(self):
        with scopes_disabled():
            first = apply_movement(
                entry_id=self.entry.id,
                space=self.space,
                user=self.user,
                kind=StockMovement.RECEIPT,
                quantity="1",
                idempotency_key="decimal-replay",
            )
            replay = apply_movement(
                entry_id=self.entry.id,
                space=self.space,
                user=self.user,
                kind=StockMovement.RECEIPT,
                quantity="1.0",
                idempotency_key="decimal-replay",
            )
            self.entry.refresh_from_db()

        self.assertEqual(replay.id, first.id)
        self.assertEqual(self.entry.amount, Decimal("11"))

    def test_a_movement_can_only_be_reversed_once(self):
        with scopes_disabled():
            movement = apply_movement(
                entry_id=self.entry.id,
                space=self.space,
                user=self.user,
                kind=StockMovement.RECEIPT,
                quantity="2",
                idempotency_key="receipt-to-reverse",
            )
            reverse_movement(
                movement_id=movement.id,
                space=self.space,
                user=self.user,
                idempotency_key="first-reversal",
            )
            with self.assertRaises(ValidationError):
                reverse_movement(
                    movement_id=movement.id,
                    space=self.space,
                    user=self.user,
                    idempotency_key="second-reversal",
                )

    def test_a_reversal_cannot_itself_be_reversed(self):
        with scopes_disabled():
            movement = apply_movement(
                entry_id=self.entry.id,
                space=self.space,
                user=self.user,
                kind=StockMovement.RECEIPT,
                quantity="2",
                idempotency_key="receipt",
            )
            reversal = reverse_movement(
                movement_id=movement.id,
                space=self.space,
                user=self.user,
                idempotency_key="reversal",
            )
            with self.assertRaises(ValidationError):
                reverse_movement(
                    movement_id=reversal.id,
                    space=self.space,
                    user=self.user,
                    idempotency_key="reverse-the-reversal",
                )

    def test_purchase_order_rejects_non_positive_quantity(self):
        response = self._client(self.user).post(
            "/api/cuaderno/orders/",
            {"food": self.food.id, "unit": self.unit.id, "quantity": "-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_legacy_order_route_uses_the_persistent_household_contract(self):
        response = self._client(self.user).post("/api/cuaderno/orders/", {
            "food": self.food.pk, "unit": self.unit.pk, "quantity": "2", "supplier_name": "Proveedor anterior",
        }, format="json")
        self.assertEqual(response.status_code, 201, getattr(response, "data", response.content))
        with scopes_disabled():
            order = PurchaseOrder.objects.get(pk=response.data["id"])
            self.assertEqual(order.household_id, self.location.household_id)
            self.assertEqual(order.state, PurchaseOrder.DRAFT)
            self.assertEqual(order.supplier_name, "Proveedor anterior")
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("10"))

    def test_native_inventory_update_uses_the_same_ledger(self):
        client = self._client(self.user)
        response = client.patch(
            f"/api/inventory-entry/{self.entry.id}/",
            {"amount": "7"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="native-adjustment",
        )
        self.assertEqual(response.status_code, 200)

        replay = client.patch(
            f"/api/inventory-entry/{self.entry.id}/",
            {"amount": "7.0"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="native-adjustment",
        )
        self.assertEqual(replay.status_code, 200)
        with scopes_disabled():
            self.entry.refresh_from_db()
            movements = StockMovement.objects.filter(entry=self.entry, idempotency_key="native-adjustment")
            self.assertEqual(self.entry.amount, Decimal("7"))
            self.assertEqual(movements.count(), 1)
            self.assertEqual(movements.get().kind, StockMovement.CONSUME)
            self.assertEqual(movements.get().quantity, Decimal("3"))

    def test_native_delete_preserves_entry_and_stock_history(self):
        with scopes_disabled():
            movement = apply_movement(entry_id=self.entry.pk, space=self.space, user=self.user,
                                      kind="receipt", quantity="1", idempotency_key="history-protected")
        response = self._client(self.user).delete(f"/api/inventory-entry/{self.entry.pk}/")
        self.assertEqual(response.status_code, 400, response.data)
        with scopes_disabled():
            self.assertTrue(InventoryEntry.objects.filter(pk=self.entry.pk).exists())
            self.assertTrue(StockMovement.objects.filter(pk=movement.pk).exists())

    def test_native_delete_cannot_erase_pre_ledger_tandoor_logs(self):
        from cookbook.models import InventoryLog
        with scopes_disabled():
            log = InventoryLog.objects.create(space=self.space, entry=self.entry, booking_type=InventoryLog.B_ADD,
                                              old_amount=0, new_amount=10, old_inventory_location=self.location,
                                              new_inventory_location=self.location)
        response = self._client(self.user).delete(f"/api/inventory-entry/{self.entry.pk}/")
        self.assertEqual(response.status_code, 400, response.data)
        with scopes_disabled():
            self.assertTrue(InventoryLog.objects.filter(pk=log.pk).exists())

    def test_native_consume_replay_does_not_subtract_twice_and_rejects_overdraw(self):
        client = self._client(self.user)
        url = f"/api/inventory-entry/{self.entry.id}/consume/"
        for quantity in ("3", "3.0"):
            response = client.post(url, {"quantity": quantity}, format="json", HTTP_IDEMPOTENCY_KEY="native-consume")
            self.assertEqual(response.status_code, 200)
        denied = client.post(url, {"quantity": "8"}, format="json", HTTP_IDEMPOTENCY_KEY="native-overdraw")
        self.assertEqual(denied.status_code, 400)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("7"))
            self.assertEqual(StockMovement.objects.filter(entry=self.entry).count(), 1)

    def test_native_create_key_cannot_be_reused_by_movement_service(self):
        payload = {"inventory_location": self.location.id, "food": self.food.id, "unit": self.unit.id, "amount": "0"}
        response = self._client(self.user).post("/api/inventory-entry/", payload, format="json", HTTP_IDEMPOTENCY_KEY="zero-create-key")
        self.assertEqual(response.status_code, 201)
        with scopes_disabled(), self.assertRaises(IdempotencyConflict):
            apply_movement(entry_id=response.data["id"], space=self.space, user=self.user,
                           kind=StockMovement.RECEIPT, quantity="1", idempotency_key="zero-create-key")

    def test_native_absolute_stock_edit_preserves_high_precision_delta(self):
        target = "10000000000010.0000000000000001"
        response = self._client(self.user).patch(f"/api/inventory-entry/{self.entry.pk}/", {"amount": target},
                                                 format="json", HTTP_IDEMPOTENCY_KEY="native-high-precision")
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal(target))
            movement = StockMovement.objects.get(space=self.space, idempotency_key="native-high-precision")
            self.assertEqual(movement.quantity, Decimal("10000000000000.0000000000000001"))
        conflict = self._client(self.user).patch(
            f"/api/inventory-entry/{self.entry.pk}/",
            {"amount": "10000000000010.0000000000000002"}, format="json",
            HTTP_IDEMPOTENCY_KEY="native-high-precision",
        )
        self.assertEqual(conflict.status_code, 409, getattr(conflict, "data", conflict.content))

    def test_stock_extreme_exponents_and_unstorable_fraction_are_rejected(self):
        client = self._client(self.user)
        for index, quantity in enumerate(["1e999999999", "1e-999999999", "0.00000000000000001"]):
            response = client.post("/api/cuaderno/movements/", {
                "entry": self.entry.pk, "kind": "receipt", "quantity": quantity, "idempotency_key": f"bounded-{index}",
            }, format="json")
            self.assertEqual(response.status_code, 400)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("10"))
            self.assertFalse(StockMovement.objects.filter(space=self.space).exists())

    def test_high_precision_receipt_preserves_balance_and_distinct_retry_payload(self):
        with scopes_disabled():
            movement = apply_movement(entry_id=self.entry.pk, space=self.space, user=self.user,
                                      kind=StockMovement.RECEIPT, quantity="10000000000000.0000000000000001",
                                      idempotency_key="high-precision")
            with self.assertRaises(IdempotencyConflict):
                apply_movement(entry_id=self.entry.pk, space=self.space, user=self.user,
                               kind=StockMovement.RECEIPT, quantity="10000000000000.0000000000000002",
                               idempotency_key="high-precision")
            self.entry.refresh_from_db()
            movement.refresh_from_db()
            expected = Decimal("10000000000010.0000000000000001")
            self.assertEqual(self.entry.amount, expected)
            self.assertEqual(movement.balance_after, expected)

    def test_unknown_format_conversion_requires_food_specific_content(self):
        from cookbook.models import UnitConversion
        from cuaderno.domain.errors import DomainError
        from cuaderno.services.subrecipes import convert_native_quantity
        with scopes_disabled():
            bag = Unit.objects.create(space=self.space, name="bolsa")
            UnitConversion.objects.create(space=self.space, created_by=self.admin, base_unit=bag, base_amount=1,
                                          converted_unit=self.unit, converted_amount=5)
            with self.assertRaises(DomainError):
                convert_native_quantity(Decimal("2"), bag, self.unit, self.food, self.space)
            UnitConversion.objects.create(space=self.space, created_by=self.admin, food=self.food, base_unit=bag, base_amount=1,
                                          converted_unit=self.unit, converted_amount=5)
            self.assertEqual(convert_native_quantity(Decimal("2"), bag, self.unit, self.food, self.space), Decimal("10"))

    def test_food_specific_density_does_not_authorize_a_generic_bag_conversion(self):
        from cookbook.models import UnitConversion
        from cuaderno.domain.errors import DomainError
        from cuaderno.services.subrecipes import convert_native_quantity
        with scopes_disabled():
            bag = Unit.objects.create(space=self.space, name="bolsa sin contenido declarado")
            litre = Unit.objects.create(space=self.space, name="L")
            UnitConversion.objects.create(space=self.space, created_by=self.admin, base_unit=bag, base_amount=1,
                                          converted_unit=self.unit, converted_amount=5)
            UnitConversion.objects.create(space=self.space, created_by=self.admin, food=self.food, base_unit=self.unit, base_amount=1,
                                          converted_unit=litre, converted_amount=2)
            with self.assertRaises(DomainError):
                convert_native_quantity(Decimal("1"), bag, litre, self.food, self.space)
            self.assertEqual(convert_native_quantity(Decimal("1"), self.unit, litre, self.food, self.space), Decimal("2"))

    def test_global_mass_volume_conversion_is_not_a_food_density(self):
        from cookbook.models import UnitConversion
        from cuaderno.domain.errors import DomainError
        from cuaderno.services.subrecipes import convert_native_quantity
        with scopes_disabled():
            litre = Unit.objects.create(name="L", space=self.space)
            UnitConversion.objects.create(space=self.space, created_by=self.admin, base_unit=litre, base_amount=1,
                                          converted_unit=self.unit, converted_amount=1)
            with self.assertRaises(DomainError):
                convert_native_quantity(1, litre, self.unit, self.food, self.space)

    def test_movement_metadata_is_frozen_when_native_entry_moves(self):
        with scopes_disabled():
            movement = apply_movement(entry_id=self.entry.pk, space=self.space, user=self.user,
                                      kind=StockMovement.RECEIPT, quantity="2", idempotency_key="frozen-receipt")
            other_location = InventoryLocation.objects.create(name="Frigorífico", household=self.location.household,
                                                              created_by=self.admin, space=self.space)
        response = self._client(self.user).patch(f"/api/inventory-entry/{self.entry.pk}/",
                                                 {"inventory_location": other_location.pk}, format="json",
                                                 HTTP_IDEMPOTENCY_KEY="tracked-transfer")
        self.assertEqual(response.status_code, 200)
        with scopes_disabled():
            movement.refresh_from_db()
            self.assertEqual(movement.metadata_snapshot["food_name"], "Arroz")
            self.assertEqual(movement.metadata_snapshot["unit_name"], "kg")
            self.assertEqual(movement.metadata_snapshot["location_id"], self.location.pk)
            from cuaderno.models import InventoryWriteRequest
            audit = InventoryWriteRequest.objects.get(idempotency_key="tracked-transfer")
            self.assertEqual(audit.created_by_id, self.user.pk)
            self.assertEqual(audit.metadata_before["location_id"], self.location.pk)
            self.assertEqual(audit.metadata_after["location_id"], other_location.pk)

    def test_native_inventory_create_is_logged_and_idempotent(self):
        client = self._client(self.user)
        payload = {
            "inventory_location": self.location.id,
            "food": self.food.id,
            "unit": self.unit.id,
            "amount": "5",
        }
        first = client.post(
            "/api/inventory-entry/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="native-create",
        )
        replay = client.post(
            "/api/inventory-entry/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="native-create",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.data["id"], replay.data["id"])
        with scopes_disabled():
            movements = StockMovement.objects.filter(idempotency_key="native-create")
            self.assertEqual(movements.count(), 1)
            self.assertEqual(movements.get().quantity, Decimal("5"))
            self.assertEqual(movements.get().entry.amount, Decimal("5"))

    def test_allergen_declaration_validates_name_and_state(self):
        client = self._client(self.user)
        empty = client.post(
            "/api/cuaderno/allergens/",
            {"food": self.food.id, "name": "", "state": "unknown"},
            format="json",
        )
        invalid = client.post(
            "/api/cuaderno/allergens/",
            {"food": self.food.id, "name": "Gluten", "state": "absent"},
            format="json",
        )
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(invalid.status_code, 400)

    def test_generic_recipe_import_previews_and_replays_without_duplicates(self):
        payload = {
            "format": "cuaderno-recipes-v1",
            "mapping": {"foods": {"Arroz": self.food.id}},
            "recipes": [
                {
                    "external_id": "legacy-42",
                    "name": "Arroz de prueba",
                    "servings": "4",
                    "ingredients": [{"food": "Arroz", "quantity": "400", "unit": "g"}],
                }
            ],
        }
        client = self._client(self.user)
        preview = client.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["writes"], 0)

        first = client.post("/api/cuaderno/exchange/", payload, format="json")
        replay = client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(len(first.data["created"]), 1)
        self.assertEqual(replay.data["created"], [])
        self.assertEqual(replay.data["replayed"], first.data["created"])
        with scopes_disabled():
            self.assertEqual(RecipeExchangeRecord.objects.filter(space=self.space).count(), 1)
            self.assertEqual(Recipe.objects.filter(space=self.space, name="Arroz de prueba").count(), 1)

        changed = {**payload, "recipes": [{**payload["recipes"][0], "name": "Contenido distinto"}]}
        conflict = client.post("/api/cuaderno/exchange/", changed, format="json")
        self.assertEqual(conflict.status_code, 409)

    def test_recipe_exchange_does_not_export_another_users_private_recipe(self):
        with scopes_disabled():
            Recipe.objects.create(name="Privada ajena", servings=1, private=True, created_by=self.admin, space=self.space)
            Recipe.objects.create(name="Privada propia", servings=1, private=True, created_by=self.user, space=self.space)
            Recipe.objects.create(name="Compartida", servings=1, private=False, created_by=self.admin, space=self.space)
        response = self._client(self.user).get("/api/cuaderno/exchange/")
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.json()["recipes"]}
        self.assertNotIn("Privada ajena", names)
        self.assertIn("Privada propia", names)
        self.assertIn("Compartida", names)

    def test_native_food_merge_reassigns_professional_relations(self):
        with scopes_disabled():
            target = Food.objects.create(name="Arroz largo", space=self.space)
            package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                label="Saco",
                quantity=Decimal("5"),
            )
            allergen = AllergenDeclaration.objects.create(
                space=self.space,
                food=self.food,
                name="Trazas",
                state=AllergenDeclaration.UNKNOWN,
            )
            order = PurchaseOrder.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                quantity=Decimal("2"),
                created_by=self.user,
            )
            self.food.merge_into(target)
            package.refresh_from_db()
            allergen.refresh_from_db()
            order.refresh_from_db()
            self.entry.refresh_from_db()

        self.assertEqual(package.food_id, target.id)
        self.assertEqual(allergen.food_id, target.id)
        self.assertEqual(order.food_id, target.id)
        self.assertEqual(self.entry.food_id, target.id)

    def test_native_food_merge_api_preserves_both_packages_and_one_reference(self):
        with scopes_disabled():
            source = Food.add_root(name="Arroz duplicado", space=self.space)
            target = Food.add_root(name="Arroz definitivo", space=self.space)
            source_package = PackageFormat.objects.create(
                space=self.space, food=source, unit=self.unit, label="Saco origen",
                quantity=Decimal("5"), is_reference=True,
            )
            target_package = PackageFormat.objects.create(
                space=self.space, food=target, unit=self.unit, label="Saco destino",
                quantity=Decimal("10"), is_reference=True,
            )
        response = self._client(self.user).put(reverse("api:food-merge", args=[source.id, target.id]))
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            self.assertFalse(Food.objects.filter(pk=source.id).exists())
            source_package.refresh_from_db()
            target_package.refresh_from_db()
            self.assertEqual(source_package.food_id, target.id)
            self.assertFalse(source_package.is_reference)
            self.assertTrue(target_package.is_reference)
            self.assertEqual(PackageFormat.objects.filter(food=target).count(), 2)

    def test_native_food_merge_preserves_shared_properties_and_conversions(self):
        from cookbook.models import Property, PropertyType, UnitConversion
        with scopes_disabled():
            source = Food.add_root(name="Alimento origen", space=self.space)
            target = Food.add_root(name="Alimento destino", space=self.space)
            third = Food.add_root(name="Alimento tercero", space=self.space)
            prop_type = PropertyType.objects.create(name="Proteína", space=self.space)
            prop = Property.objects.create(property_type=prop_type, property_amount=Decimal("4"), space=self.space)
            source.properties.add(prop)
            third.properties.add(prop)
            grams = Unit.objects.create(name="g", space=self.space)
            conversion = UnitConversion.objects.create(
                space=self.space, food=source, base_unit=self.unit, base_amount=1,
                converted_unit=grams, converted_amount=1000, created_by=self.user,
            )
        response = self._client(self.user).put(reverse("api:food-merge", args=[source.pk, target.pk]))
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            self.assertTrue(Property.objects.filter(pk=prop.pk).exists())
            self.assertTrue(target.properties.filter(pk=prop.pk).exists())
            self.assertTrue(third.properties.filter(pk=prop.pk).exists())
            conversion.refresh_from_db()
            self.assertEqual(conversion.food_id, target.pk)

    def test_native_inventory_write_without_key_is_rejected_before_creation(self):
        response = self._client(self.user).post("/api/inventory-entry/", {
            "inventory_location": self.location.pk, "food": self.food.pk, "unit": self.unit.pk, "amount": "1",
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_movement_key_cannot_be_reused_for_native_inventory_adjustment(self):
        with scopes_disabled():
            apply_movement(entry_id=self.entry.pk, space=self.space, user=self.user, kind="consume", quantity="1", idempotency_key="another-operation")
        response = self._client(self.user).patch(f"/api/inventory-entry/{self.entry.pk}/", {"amount": "8"}, format="json", HTTP_IDEMPOTENCY_KEY="another-operation")
        self.assertEqual(response.status_code, 409, response.data)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("9"))

    def test_native_inventory_create_rejects_same_key_for_different_food(self):
        with scopes_disabled():
            other_food = Food.objects.create(name="Lentejas", space=self.space)
            before = InventoryEntry.objects.filter(space=self.space).count()
        client = self._client(self.user)
        payload = {"inventory_location": self.location.id, "food": self.food.id, "unit": self.unit.id, "amount": "5"}
        first = client.post("/api/inventory-entry/", payload, format="json", HTTP_IDEMPOTENCY_KEY="conflicting-create")
        self.assertEqual(first.status_code, 201, first.data)
        conflict = client.post(
            "/api/inventory-entry/", {**payload, "food": other_food.id},
            format="json", HTTP_IDEMPOTENCY_KEY="conflicting-create",
        )
        self.assertEqual(conflict.status_code, 409, conflict.data)
        with scopes_disabled():
            self.assertEqual(InventoryEntry.objects.filter(space=self.space).count(), before + 1)
            self.assertFalse(InventoryEntry.objects.filter(food=other_food).exists())
            self.assertEqual(StockMovement.objects.filter(idempotency_key="conflicting-create").count(), 1)

    def test_native_inventory_zero_create_replay_does_not_duplicate_entry(self):
        client = self._client(self.user)
        payload = {"inventory_location": self.location.id, "food": self.food.id, "unit": self.unit.id, "amount": "0", "note": "Pendiente de recepción"}
        with scopes_disabled():
            before = InventoryEntry.objects.filter(space=self.space).count()
        first = client.post("/api/inventory-entry/", payload, format="json", HTTP_IDEMPOTENCY_KEY="zero-create")
        replay = client.post("/api/inventory-entry/", {**payload, "amount": "0.0"}, format="json", HTTP_IDEMPOTENCY_KEY="zero-create")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(first.data["id"], replay.data["id"])
        with scopes_disabled():
            self.assertEqual(InventoryEntry.objects.filter(space=self.space).count(), before + 1)
            entry = InventoryEntry.objects.get(pk=first.data["id"])
            self.assertEqual(entry.amount, Decimal("0"))
            self.assertEqual(entry.note, "Pendiente de recepción")
            self.assertFalse(StockMovement.objects.filter(entry=entry).exists())

    def test_native_inventory_adjustment_replay_does_not_undo_later_consumption(self):
        client = self._client(self.user)
        url = f"/api/inventory-entry/{self.entry.id}/"
        adjusted = client.patch(url, {"amount": "7"}, format="json", HTTP_IDEMPOTENCY_KEY="adjust-then-consume")
        self.assertEqual(adjusted.status_code, 200, adjusted.data)
        with scopes_disabled():
            apply_movement(entry_id=self.entry.id, space=self.space, user=self.user,
                           kind=StockMovement.CONSUME, quantity="1", idempotency_key="later-consumption")
        replay = client.patch(url, {"amount": "7.0"}, format="json", HTTP_IDEMPOTENCY_KEY="adjust-then-consume")
        self.assertEqual(replay.status_code, 200, replay.data)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("6"))
            self.assertEqual(StockMovement.objects.filter(entry=self.entry).count(), 2)

    def test_native_inventory_update_rejects_same_key_with_changed_metadata(self):
        client = self._client(self.user)
        url = f"/api/inventory-entry/{self.entry.id}/"
        first = client.patch(url, {"amount": "7", "note": "Primer recuento"}, format="json", HTTP_IDEMPOTENCY_KEY="metadata-conflict")
        self.assertEqual(first.status_code, 200, first.data)
        conflict = client.patch(url, {"amount": "7", "note": "Otra operación"}, format="json", HTTP_IDEMPOTENCY_KEY="metadata-conflict")
        self.assertEqual(conflict.status_code, 409, conflict.data)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("7"))
            self.assertEqual(self.entry.note, "Primer recuento")
            self.assertEqual(StockMovement.objects.filter(entry=self.entry).count(), 1)

    def test_movement_history_preserves_balance_at_each_event(self):
        client = self._client(self.user)
        ids = []
        for kind, quantity, key in [("receipt", "3", "history-in"), ("consume", "2", "history-out")]:
            response = client.post(
                "/api/cuaderno/movements/",
                {"entry": self.entry.id, "kind": kind, "quantity": quantity, "idempotency_key": key},
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            ids.append(response.data["movement_id"])
        response = client.get("/api/cuaderno/movements/")
        self.assertEqual(response.status_code, 200)
        balances = {row["id"]: Decimal(row["balance"]) for row in response.data}
        self.assertEqual(balances[ids[0]], Decimal("13"))
        self.assertEqual(balances[ids[1]], Decimal("11"))

    def test_cost_of_unidentified_ingredient_is_incomplete_not_free(self):
        with scopes_disabled():
            recipe = Recipe.objects.create(name="Ingrediente pendiente", servings=2, created_by=self.user, space=self.space)
            step = Step.objects.create(space=self.space, instruction="Identificar antes de cocinar")
            step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=None, unit=self.unit, amount=Decimal("2"), no_amount=False,
            ))
            recipe.steps.add(step)
        response = self._client(self.user).get(f"/api/cuaderno/recipes/{recipe.id}/cost/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "incomplete")
        self.assertIsNone(response.data["per_serving"])
        self.assertEqual(response.data["lines"][0]["status"], "incomplete")

    def test_private_media_requires_visible_recipe_not_only_known_filename(self):
        import tempfile
        from django.core.files.base import ContentFile
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory, GUNICORN_MEDIA=True):
            with scopes_disabled():
                recipe = Recipe.objects.create(name="Foto privada", private=True, created_by=self.admin, space=self.space)
                recipe.image.save("private-demo.png", ContentFile(b"synthetic-image"))
                url = recipe.image.url
            hidden = self._client(self.user).get(url)
            self.assertEqual(hidden.status_code, 404)
            own = self._client(self.admin).get(url)
            self.assertEqual(own.status_code, 200)
            self.assertEqual(b"".join(own.streaming_content), b"synthetic-image")
            anonymous = APIClient().get(url)
            self.assertNotEqual(anonymous.status_code, 200)

    def test_native_shared_recipe_attachment_requires_its_own_share_capability(self):
        import tempfile
        from django.core.files.base import ContentFile
        from cookbook.models import ShareLink, UserFile
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            with scopes_disabled():
                recipe = Recipe.objects.create(name="Adjunto compartido", private=True, created_by=self.admin, space=self.space)
                uploaded = UserFile(name="Documento sintético", created_by=self.admin, space=self.space)
                uploaded.file.save("demo-share.txt", ContentFile(b"synthetic-attachment"))
                step = Step.objects.create(space=self.space, instruction="Ver documento", file=uploaded)
                recipe.steps.add(step)
                link = ShareLink.objects.create(recipe=recipe, created_by=self.admin, space=self.space)
                url = uploaded.file.url
            client = APIClient()
            self.assertEqual(client.get(url).status_code, 404)
            shared = client.get(url, {"share": str(link.uuid)})
            self.assertEqual(shared.status_code, 200)
            self.assertEqual(b"".join(shared.streaming_content), b"synthetic-attachment")
            self.assertEqual(shared["Cache-Control"], "private, no-store")
            self.assertEqual(shared["Content-Disposition"], "attachment")
            self.assertEqual(client.get(url, {"share": "not-a-share"}).status_code, 404)

    def test_service_cannot_link_another_users_private_recipe(self):
        with scopes_disabled():
            recipe = Recipe.objects.create(space=self.space, name="Menú privado ajeno", private=True, created_by=self.admin)
        response = self._client(self.user).post("/api/cuaderno/services/", {"recipe": recipe.pk, "base_covers": "4", "service_date": "2026-10-25"}, format="json")
        self.assertEqual(response.status_code, 404, response.data)

    def test_exchange_round_trip_preserves_private_recipe_and_ordered_steps(self):
        with scopes_disabled():
            recipe = Recipe.objects.create(
                name="Arroz privado", description="Notas propias de elaboración", private=True,
                servings=3, created_by=self.user, space=self.space,
            )
            for order, instruction, amount in [(0, "Lavar el arroz", "0.30"), (1, "Añadir la segunda tanda", "0.15")]:
                step = Step.objects.create(space=self.space, instruction=instruction, order=order)
                step.ingredients.add(Ingredient.objects.create(space=self.space, food=self.food, unit=self.unit, amount=Decimal(amount)))
                recipe.steps.add(step)
        client = self._client(self.user)
        exported = client.get("/api/cuaderno/exchange/")
        self.assertEqual(exported.status_code, 200)
        payload = exported.json()
        self.assertEqual(len(payload["recipes"]), 1)
        imported = client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(imported.status_code, 201, imported.data)
        with scopes_disabled():
            restored = Recipe.objects.get(pk=imported.data["created"][0])
            self.assertNotEqual(restored.pk, recipe.pk)
            self.assertEqual(restored.description, "Notas propias de elaboración")
            self.assertTrue(restored.private)
            self.assertEqual(restored.servings, 3)
            steps = list(restored.steps.order_by("order", "id"))
            self.assertEqual([step.instruction for step in steps], ["Lavar el arroz", "Añadir la segunda tanda"])
            self.assertEqual([step.ingredients.get().amount for step in steps], [Decimal("0.30"), Decimal("0.15")])
            self.assertTrue(all(step.ingredients.get().food_id == self.food.id for step in steps))
            self.assertTrue(all(step.ingredients.get().unit_id == self.unit.id for step in steps))

    def _linked_recipes(self, private_child=False):
        child = Recipe.objects.create(
            name="Salsa madre", servings=4, private=private_child, created_by=self.admin, space=self.space,
        )
        parent = Recipe.objects.create(name="Plato", servings=1, created_by=self.user, space=self.space)
        grams = Unit.objects.create(name="g", space=self.space)
        tomato = Food.objects.create(name="Tomate", space=self.space)
        sauce = Food.objects.create(name="Salsa", recipe=child, space=self.space)
        child_step = Step.objects.create(space=self.space, instruction="Reducir")
        child_step.ingredients.add(Ingredient.objects.create(space=self.space, food=tomato, unit=grams, amount=Decimal("500")))
        child.steps.add(child_step)
        parent_step = Step.objects.create(space=self.space, instruction="Servir")
        parent_step.ingredients.add(Ingredient.objects.create(space=self.space, food=sauce, unit=grams, amount=Decimal("300")))
        parent.steps.add(parent_step)
        return parent, child, child_step, grams

    def test_production_expands_native_subrecipe_by_declared_output_not_servings(self):
        with scopes_disabled():
            parent, child, _, grams = self._linked_recipes()
            RecipeYield.objects.create(
                space=self.space, recipe=child, unit=grams, quantity=Decimal("1000"), updated_by=self.user,
            )
        response = self._client(self.user).post("/api/cuaderno/production/", {"recipe_ids": [parent.id]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({name: Decimal(value) for name, value in response.data["needs"].items()}, {"Tomate": Decimal("150")})
        self.assertFalse(response.data["stock_changed"])
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, Decimal("10"))
            self.assertFalse(StockMovement.objects.filter(space=self.space).exists())

    def test_cost_subrecipe_uses_declared_yield_and_keeps_unrounded_decimal(self):
        with scopes_disabled():
            parent, child, step, _ = self._linked_recipes()
            step.ingredients.clear()
            oil = Food.objects.create(name="Aceite", space=self.space)
            litres = Unit.objects.create(name="L", space=self.space)
            millilitres = Unit.objects.create(name="mL", space=self.space)
            step.ingredients.add(Ingredient.objects.create(space=self.space, food=oil, unit=millilitres, amount=Decimal("400")))
            package = PackageFormat.objects.create(space=self.space, food=oil, unit=litres, quantity=Decimal("5"), label="Garrafa")
            PriceVersion.objects.create(space=self.space, package=package, amount=Decimal("32"), valid_from=timezone.now(), created_by=self.user)
            RecipeYield.objects.create(space=self.space, recipe=child, unit=self.unit, quantity=Decimal("2"), updated_by=self.user)
        client = self._client(self.user)
        batch = client.get(f"/api/cuaderno/recipes/{child.id}/cost/")
        self.assertEqual(batch.status_code, 200, batch.data)
        self.assertEqual(batch.data["status"], "complete")
        self.assertEqual(Decimal(batch.data["unrounded"]), Decimal("2.56"))
        portion = client.get(f"/api/cuaderno/recipes/{parent.id}/cost/")
        self.assertEqual(portion.status_code, 200, portion.data)
        self.assertEqual(portion.data["status"], "complete")
        self.assertEqual(Decimal(portion.data["unrounded"]), Decimal("0.384"))
        self.assertEqual(Decimal(portion.data["display"]), Decimal("0.38"))
        with scopes_disabled():
            child.refresh_from_db()
            self.assertEqual(child.servings, 4)
            self.assertEqual(step.ingredients.get().amount, Decimal("400"))

    def test_cost_cannot_expose_another_users_private_subrecipe(self):
        with scopes_disabled():
            parent, child, _, grams = self._linked_recipes(private_child=True)
            RecipeYield.objects.create(space=self.space, recipe=child, unit=grams, quantity=Decimal("1000"), updated_by=self.admin)
        response = self._client(self.user).get(f"/api/cuaderno/recipes/{parent.id}/cost/")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertNotIn("Tomate", str(response.data))

    def test_cost_detects_native_recipe_cycle_without_declared_yield(self):
        with scopes_disabled():
            parent, _, child_step, grams = self._linked_recipes()
            recursive_food = Food.objects.create(name="Vuelta al plato", recipe=parent, space=self.space)
            child_step.ingredients.add(Ingredient.objects.create(space=self.space, food=recursive_food, unit=grams, amount=1))
        response = self._client(self.user).get(f"/api/cuaderno/recipes/{parent.id}/cost/")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("recipe_cycle", response.data)

    def test_production_detects_real_nested_cycle_before_missing_yield(self):
        with scopes_disabled():
            parent, _, child_step, grams = self._linked_recipes()
            recursive_food = Food.objects.create(name="Vuelta al plato", recipe=parent, space=self.space)
            child_step.ingredients.add(Ingredient.objects.create(space=self.space, food=recursive_food, unit=grams, amount=1))
        response = self._client(self.user).post("/api/cuaderno/production/", {"recipe_ids": [parent.id]}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("recipe_cycle", response.data)

    def test_production_cannot_expose_another_users_private_subrecipe(self):
        with scopes_disabled():
            parent, child, _, grams = self._linked_recipes(private_child=True)
            RecipeYield.objects.create(
                space=self.space, recipe=child, unit=grams, quantity=Decimal("1000"), updated_by=self.admin,
            )
        response = self._client(self.user).post("/api/cuaderno/production/", {"recipe_ids": [parent.id]}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertNotIn("Tomate", str(response.data))

    def test_exchange_rejects_overlong_identity_without_truncating_or_writing(self):
        client = self._client(self.user)
        for field, limit in [("source", 64), ("external_id", 256)]:
            with self.subTest(field=field):
                payload = {"source": "legacy", "recipes": [{"external_id": "valid", "name": "Identidad", "servings": "1"}]}
                if field == "source":
                    payload[field] = "x" * (limit + 1)
                else:
                    payload["recipes"][0][field] = "x" * (limit + 1)
                response = client.post("/api/cuaderno/exchange/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        with scopes_disabled():
            self.assertFalse(RecipeExchangeRecord.objects.filter(space=self.space).exists())
            self.assertFalse(Recipe.objects.filter(space=self.space).exists())

    def test_exchange_rejects_recipe_count_and_byte_limits_before_writing(self):
        client = self._client(self.user)
        payloads = [
            {"recipes": [{"name": f"Receta {index}", "servings": "1"} for index in range(1001)]},
            {"recipes": [{"name": "Texto excesivo", "description": "á" * 1_000_001}]},
        ]
        for payload in payloads:
            with self.subTest(recipe_count=len(payload["recipes"])):
                response = client.post("/api/cuaderno/exchange/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("import_limit", response.data)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.space).exists())
            self.assertFalse(RecipeExchangeRecord.objects.filter(space=self.space).exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StockConcurrencyTests(TransactionTestCase):
    def setUp(self):
        with scopes_disabled():
            self.user = get_user_model().objects.create_user(username="stock-race")
            self.space = Space.objects.create(name="Carrera", created_by=self.user)
            household = Household.objects.create(name="Equipo", space=self.space)
            location = InventoryLocation.objects.create(
                name="Seco",
                household=household,
                created_by=self.user,
                space=self.space,
            )
            food = Food.objects.create(name="Harina", space=self.space)
            self.entry = InventoryEntry.objects.create(
                inventory_location=location,
                amount=Decimal("10"),
                food=food,
                created_by=self.user,
                space=self.space,
            )

    def _race(self, operations):
        barrier = Barrier(len(operations))
        guard = Lock()
        results = []

        def worker(kind, quantity, key):
            close_old_connections()
            try:
                with scopes_disabled():
                    space = Space.objects.get(pk=self.space.pk)
                    user = get_user_model().objects.get(pk=self.user.pk)
                    barrier.wait(timeout=10)
                    movement = apply_movement(
                        entry_id=self.entry.pk,
                        space=space,
                        user=user,
                        kind=kind,
                        quantity=quantity,
                        idempotency_key=key,
                    )
                    result = ("ok", movement.id)
            except Exception as exc:  # Captured and asserted by type below.
                result = ("error", type(exc).__name__)
            finally:
                # Persistent healthy connections are not closed by close_old_connections.
                # Each worker owns its connection and must release it before DB teardown.
                connections.close_all()
            with guard:
                results.append(result)

        threads = [Thread(target=worker, args=operation) for operation in operations]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "La carrera no terminó; posible deadlock")
        return results

    def test_two_consumptions_cannot_overdraw_the_last_stock(self):
        results = self._race(
            [
                (StockMovement.CONSUME, "7", "consume-seven"),
                (StockMovement.CONSUME, "6", "consume-six"),
            ]
        )
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(StockMovement.objects.filter(space=self.space).count(), 1)
        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertIn(self.entry.amount, (Decimal("3"), Decimal("4")))

    def test_concurrent_replay_applies_a_receipt_once(self):
        results = self._race(
            [
                (StockMovement.RECEIPT, "5", "same-receipt"),
                (StockMovement.RECEIPT, "5.0", "same-receipt"),
            ]
        )
        with scopes_disabled():
            self.entry.refresh_from_db()
            movements = StockMovement.objects.filter(space=self.space, idempotency_key="same-receipt")
            self.assertEqual(movements.count(), 1)
        self.assertEqual({result[0] for result in results}, {"ok"})
        self.assertEqual(len({result[1] for result in results}), 1)
        self.assertEqual(self.entry.amount, Decimal("15"))
