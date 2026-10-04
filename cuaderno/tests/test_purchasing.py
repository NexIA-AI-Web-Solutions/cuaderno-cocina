from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier, Lock, Thread

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db import close_old_connections, connections
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient
from cuaderno.services.ledger import apply_movement

from cookbook.models import Food, Household, InventoryEntry, InventoryLocation, Space, Supermarket, Unit, UserSpace
from cuaderno.models import (
    PackageFormat,
    PriceVersion,
    PurchaseOffer,
    PurchaseOrder,
    PurchaseReceipt,
    ServicePlan,
    SpaceProfile,
    StockMovement,
)


class PurchasingFixtureMixin:
    def make_user(self, username, group, household):
        user = get_user_model().objects.create_user(username=username, password="local-test-only")
        membership = UserSpace.objects.create(user=user, space=self.space, household=household, active=True)
        membership.groups.add(Group.objects.get_or_create(name=group)[0])
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Compras")
            self.household = Household.objects.create(space=self.space, name="Cocina")
            self.other_household = Household.objects.create(space=self.space, name="Otra cocina")
            self.admin = self.make_user("purchasing-admin", "admin", self.household)
            self.user = self.make_user("purchasing-user", "user", self.household)
            self.guest = self.make_user("purchasing-guest", "guest", self.household)
            self.outsider = self.make_user("purchasing-outsider", "user", self.other_household)
            self.space.created_by = self.admin
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.INTEGRAL)
            self.kg = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.g = Unit.objects.create(space=self.space, name="g", base_unit="g")
            self.food = Food.objects.create(space=self.space, name="Harina")
            self.package = PackageFormat.objects.create(
                space=self.space, food=self.food, unit=self.kg, label="Saco 5 kg", quantity=Decimal("5")
            )
            self.supplier = Supermarket.objects.create(space=self.space, name="Mercado local")
            self.location = InventoryLocation.objects.create(
                space=self.space, household=self.household, name="Seco", created_by=self.admin
            )
            self.entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.g,
                amount=Decimal("1000"),
                created_by=self.admin,
            )
            other_location = InventoryLocation.objects.create(
                space=self.space, household=self.other_household, name="Ajeno", created_by=self.admin
            )
            self.other_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=other_location,
                food=self.food,
                unit=self.g,
                amount=Decimal("0"),
                created_by=self.admin,
            )

    def create_offer(self, amount="12.50"):
        response = self.client_for(self.user).post(
            "/api/cuaderno/purchase-offers/",
            {
                "package": self.package.pk,
                "supplier": self.supplier.pk,
                "amount": amount,
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, getattr(response, "data", response.content))
        return PurchaseOffer.objects.get(pk=response.data["id"])

    def create_order(self, *, quantity="10", package_count="2"):
        offer = self.create_offer()
        before = self.entry.amount
        response = self.client_for(self.user).post(
            "/api/cuaderno/purchase-orders/",
            {
                "quantity": quantity,
                "package": self.package.pk,
                "supplier": self.supplier.pk,
                "offer": offer.pk,
                "package_count": package_count,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, getattr(response, "data", response.content))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, before)
        return PurchaseOrder.objects.get(pk=response.data["id"])

    def order_order(self, order):
        response = self.client_for(self.user).post(
            f"/api/cuaderno/purchase-orders/{order.pk}/", {"action": "order"}, format="json"
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        order.refresh_from_db()
        return order


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PurchasingWorkflowTests(PurchasingFixtureMixin, TestCase):
    def test_database_offer_free_flag_is_exactly_equivalent_to_zero(self):
        with scopes_disabled(), transaction.atomic(), self.assertRaises(IntegrityError):
            PurchaseOffer.objects.create(space=self.space, package=self.package, supplier=self.supplier,
                                         amount=Decimal("1"), explicit_free=True, created_by=self.user)

    def test_native_supermarket_offer_history_and_order_snapshots_never_move_stock(self):
        order = self.create_order()
        self.assertEqual(order.food_id, self.food.pk)
        self.assertEqual(order.unit_id, self.kg.pk)
        self.assertEqual(order.household_id, self.household.pk)
        self.assertEqual(order.supplier_id, self.supplier.pk)
        self.assertEqual(order.supplier_name, "Mercado local")
        self.assertEqual(order.package_quantity_snapshot, Decimal("5"))
        self.assertEqual(order.package_unit_snapshot_id, self.kg.pk)
        self.assertEqual(order.price_snapshot, Decimal("12.50"))
        self.assertEqual(order.currency_snapshot, "EUR")
        self.assertEqual(order.state, PurchaseOrder.DRAFT)
        self.assertFalse(StockMovement.objects.exists())

        changed = self.client_for(self.user).post(
            "/api/cuaderno/purchase-offers/",
            {"package": self.package.pk, "supplier": self.supplier.pk, "amount": "13.25"},
            format="json",
        )
        self.assertEqual(changed.status_code, 201, getattr(changed, "data", changed.content))
        order.refresh_from_db()
        self.assertEqual(order.price_snapshot, Decimal("12.50"))
        self.assertEqual(PurchaseOffer.objects.count(), 2)

    def test_offer_and_order_inputs_are_strict_decimal_strings_and_ids_reject_bool_or_list(self):
        client = self.client_for(self.user)
        for invalid_package in (True, [self.package.pk]):
            response = client.post(
                "/api/cuaderno/purchase-offers/",
                {"package": invalid_package, "supplier": self.supplier.pk, "amount": "2"},
                format="json",
            )
            self.assertEqual(response.status_code, 400, getattr(response, "data", response.content))
        numeric_money = client.post(
            "/api/cuaderno/purchase-offers/",
            {"package": self.package.pk, "supplier": self.supplier.pk, "amount": 2.1},
            format="json",
        )
        self.assertEqual(numeric_money.status_code, 400, getattr(numeric_money, "data", numeric_money.content))
        for invalid_amount in (
            "10000000000000000.0000000000000001",
            "1e999999999",
            "1e-999999999",
        ):
            overflow = client.post(
                "/api/cuaderno/purchase-offers/",
                {"package": self.package.pk, "supplier": self.supplier.pk, "amount": invalid_amount},
                format="json",
            )
            self.assertEqual(overflow.status_code, 400, getattr(overflow, "data", overflow.content))
        undeclared_zero = client.post(
            "/api/cuaderno/purchase-offers/",
            {"package": self.package.pk, "supplier": self.supplier.pk, "amount": "0"},
            format="json",
        )
        self.assertEqual(undeclared_zero.status_code, 400, getattr(undeclared_zero, "data", undeclared_zero.content))

    def test_partial_receipt_converts_to_entry_unit_and_replay_is_exactly_once(self):
        order = self.order_order(self.create_order())
        payload = {"entry": self.entry.pk, "quantity": "2.5", "idempotency_key": "delivery-1"}
        first = self.client_for(self.user).post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/", payload, format="json"
        )
        self.assertEqual(first.status_code, 201, getattr(first, "data", first.content))
        replay = self.client_for(self.user).post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/", payload, format="json"
        )
        self.assertEqual(replay.status_code, 200, getattr(replay, "data", replay.content))
        self.assertEqual(replay.data["id"], first.data["id"])
        different = self.client_for(self.user).post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/",
            {**payload, "quantity": "3"},
            format="json",
        )
        self.assertEqual(different.status_code, 409, getattr(different, "data", different.content))

        order.refresh_from_db()
        self.entry.refresh_from_db()
        receipt = PurchaseReceipt.objects.get(pk=first.data["id"])
        self.assertEqual(order.received_quantity, Decimal("2.5"))
        self.assertEqual(order.state, PurchaseOrder.PART_RECEIVED)
        self.assertEqual(self.entry.amount, Decimal("3500"))
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(
            receipt.movement.metadata_snapshot["origin"],
            {"type": "purchase_order", "id": order.pk, "receipt_key": "delivery-1"},
        )

    def test_receipt_boundaries_cancel_and_reversal_preserve_documents(self):
        order = self.order_order(self.create_order(quantity="4", package_count="0.8"))
        client = self.client_for(self.user)
        foreign = client.post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/",
            {"entry": self.other_entry.pk, "quantity": "1", "idempotency_key": "foreign-entry"},
            format="json",
        )
        self.assertEqual(foreign.status_code, 404, getattr(foreign, "data", foreign.content))
        received = client.post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/",
            {"entry": self.entry.pk, "quantity": "3", "idempotency_key": "partial"},
            format="json",
        )
        self.assertEqual(received.status_code, 201, getattr(received, "data", received.content))
        over = client.post(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/",
            {"entry": self.entry.pk, "quantity": "2", "idempotency_key": "over"},
            format="json",
        )
        self.assertEqual(over.status_code, 400, getattr(over, "data", over.content))
        cancelled = client.post(
            f"/api/cuaderno/purchase-orders/{order.pk}/", {"action": "cancel"}, format="json"
        )
        self.assertEqual(cancelled.status_code, 200, getattr(cancelled, "data", cancelled.content))
        order.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertEqual(order.state, PurchaseOrder.CANCELLED)
        self.assertEqual(order.received_quantity, Decimal("3"))
        self.assertEqual(self.entry.amount, Decimal("4000"))

        receipt = PurchaseReceipt.objects.get(pk=received.data["id"])
        listed = client.get(f"/api/cuaderno/purchase-orders/{order.pk}/receipts/")
        self.assertEqual(listed.status_code, 200, getattr(listed, "data", listed.content))
        self.assertEqual([row["id"] for row in listed.data], [receipt.pk])
        self.assertEqual(self.client_for(self.outsider).get(
            f"/api/cuaderno/purchase-orders/{order.pk}/receipts/"
        ).status_code, 404)
        bypass = client.post("/api/cuaderno/movements/", {
            "reverse_of": receipt.movement_id, "idempotency_key": "bypass-purchase-document",
        }, format="json")
        self.assertEqual(bypass.status_code, 400, getattr(bypass, "data", bypass.content))
        reversed_response = client.post(
            f"/api/cuaderno/purchase-receipts/{receipt.pk}/reverse/",
            {"idempotency_key": "undo-partial"},
            format="json",
        )
        self.assertEqual(reversed_response.status_code, 201, getattr(reversed_response, "data", reversed_response.content))
        replay = client.post(
            f"/api/cuaderno/purchase-receipts/{receipt.pk}/reverse/",
            {"idempotency_key": "undo-partial"},
            format="json",
        )
        self.assertEqual(replay.status_code, 200, getattr(replay, "data", replay.content))
        order.refresh_from_db()
        self.entry.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(order.received_quantity, Decimal("0"))
        self.assertEqual(order.state, PurchaseOrder.CANCELLED)
        self.assertEqual(self.entry.amount, Decimal("1000"))
        self.assertIsNotNone(receipt.reversed_by_id)
        self.assertEqual(receipt.reversed_by.metadata_snapshot["origin"]["id"], order.pk)
        with self.assertRaises(ProtectedError):
            order.delete()
        with self.assertRaises(ProtectedError):
            receipt.movement.delete()

    def test_replenishment_uses_confirmed_needs_usable_household_stock_and_reference_price(self):
        with scopes_disabled():
            PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("12.50"),
                valid_from=timezone.now(),
                created_by=self.admin,
            )
            ServicePlan.objects.create(
                space=self.space,
                household=self.household,
                title="Servicio confirmado",
                covers=10,
                created_by=self.user,
                service_date=timezone.localdate(),
                state=ServicePlan.CONFIRMED,
                snapshot={
                    "schema_version": 1,
                    "recipe_id": None,
                    "recipe_graph": {},
                    "needs": [{
                        "food_id": self.food.pk,
                        "food_name": self.food.name,
                        "unit_id": self.kg.pk,
                        "unit_name": "kg",
                        "quantity": "12",
                    }, {
                        "food_id": self.food.pk,
                        "food_name": self.food.name,
                        "unit_id": self.g.pk,
                        "unit_name": "g",
                        "quantity": "1000",
                    }],
                },
            )
            expired = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("100"),
                expires=date.today() - timedelta(days=1),
                created_by=self.admin,
            )
        response = self.client_for(self.user).post(
            "/api/cuaderno/replenishment/", {"required": "999", "usable_stock": "999"}, format="json"
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        self.assertEqual(response.data["items"], [{
            "food": self.food.pk,
            "unit": self.kg.pk,
            "required": "13",
            "minimum_stock": "0",
            "target_stock": "13",
            "location_shortfalls": [],
            "usable_stock": "1",
            "missing": "12",
            "package": self.package.pk,
            "packages": "3",
            "purchase_quantity": "15",
            "reference_price": "12.5",
            "currency": "EUR",
        }])
        with scopes_disabled():
            self.assertTrue(InventoryEntry.objects.filter(pk=expired.pk).exists())
        self.assertEqual(self.client_for(self.outsider).post("/api/cuaderno/replenishment/", {}, format="json").data["items"], [])
        self.assertEqual(self.client_for(self.guest).post("/api/cuaderno/replenishment/", {}, format="json").status_code, 403)


    def test_guest_purchase_reads_are_household_scoped_and_foreign_ids_are_opaque(self):
        own = self.create_order()
        other_response = self.client_for(self.outsider).post(
            "/api/cuaderno/purchase-orders/",
            {"quantity": "5", "package": self.package.pk,
             "supplier": self.supplier.pk, "package_count": "1"},
            format="json",
        )
        self.assertEqual(other_response.status_code, 201, other_response.data)
        other = PurchaseOrder.objects.get(pk=other_response.data["id"])
        with scopes_disabled():
            own_movement = apply_movement(
                entry_id=self.entry.pk, space=self.space, user=self.user,
                kind=StockMovement.RECEIPT, quantity="1",
                idempotency_key="guest-household-own",
            )
            other_movement = apply_movement(
                entry_id=self.other_entry.pk, space=self.space, user=self.outsider,
                kind=StockMovement.RECEIPT, quantity="1",
                idempotency_key="guest-household-other",
            )
        guest = self.client_for(self.guest)

        listed = guest.get("/api/cuaderno/purchase-orders/")
        movements = guest.get("/api/cuaderno/movements/")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual({row["id"] for row in listed.data}, {own.pk})
        self.assertEqual(movements.status_code, 200, movements.data)
        self.assertIn(own_movement.pk, {row["id"] for row in movements.data})
        self.assertNotIn(other_movement.pk, {row["id"] for row in movements.data})
        self.assertEqual(
            guest.get(f"/api/cuaderno/purchase-orders/{other.pk}/").status_code, 404,
        )
        self.assertEqual(
            guest.get(f"/api/cuaderno/purchase-orders/{other.pk}/receipts/").status_code, 404,
        )
        self.assertEqual(
            guest.get(f"/api/cuaderno/stock-minimums/?household={self.other_household.pk}").status_code,
            404,
        )
        self.assertNotIn(self.other_household.name, str(listed.data) + str(movements.data))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PurchasingConcurrencyTests(PurchasingFixtureMixin, TransactionTestCase):
    def test_two_same_key_receipts_create_one_document_and_one_balance_change(self):
        order = self.order_order(self.create_order())
        barrier = Barrier(2)
        lock = Lock()
        results = []

        def worker():
            close_old_connections()
            try:
                client = self.client_for(self.user)
                barrier.wait()
                response = client.post(
                    f"/api/cuaderno/purchase-orders/{order.pk}/receipts/",
                    {"entry": self.entry.pk, "quantity": "2.5", "idempotency_key": "concurrent-delivery"},
                    format="json",
                )
                with lock:
                    results.append(response.status_code)
            finally:
                connections.close_all()

        threads = [Thread(target=worker), Thread(target=worker)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results), [200, 201])
        self.entry.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("3500"))
        self.assertEqual(order.received_quantity, Decimal("2.5"))
        self.assertEqual(PurchaseReceipt.objects.filter(order=order).count(), 1)
        self.assertEqual(StockMovement.objects.filter(entry=self.entry).count(), 1)
