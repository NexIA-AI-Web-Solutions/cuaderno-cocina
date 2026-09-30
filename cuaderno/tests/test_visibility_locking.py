"""Visibility decisions made before a Space lock must be revalidated after it."""

from decimal import Decimal
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    Household,
    InventoryEntry,
    InventoryLocation,
    Ingredient,
    Recipe,
    SearchFields,
    Space,
    Step,
    Storage,
    Supermarket,
    Unit,
    UserSpace,
)
from cuaderno.models import (
    AllergenDeclaration,
    InventoryWriteRequest,
    PackageFormat,
    PriceVersion,
    PurchaseOffer,
    PurchaseOrder,
    PurchaseReceipt,
    SpaceProfile,
    StockMovement,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VisibilityLockingTests(TransactionTestCase):
    reset_sequences = True

    def test_native_recipe_create_revalidates_child_after_space_lock(self):
        with scopes_disabled():
            before = (Recipe.objects.count(), Step.objects.count(), Ingredient.objects.count())
        response = self._request_during_committed_revocation("post", "/api/recipe/", {
            "name": "Raced root recipe", "steps": [{
                "name": "Raced child step", "ingredients": [], "step_recipe": self.recipe.pk,
            }],
        })
        self._assert_status(response, 404)
        with scopes_disabled():
            self.assertEqual((Recipe.objects.count(), Step.objects.count(), Ingredient.objects.count()), before)

    def test_native_external_delete_revalidates_before_provider_and_metadata(self):
        with scopes_disabled():
            storage = Storage.objects.create(
                space=self.space, name="Synthetic boundary only", method=Storage.LOCAL, created_by=self.owner,
            )
            root = Recipe.objects.create(
                space=self.space, name="Raced external root", created_by=self.owner,
                storage=storage, file_path="synthetic/never-opened.txt", file_uid="synthetic-only",
            )
            step = Step.objects.create(space=self.space, name="Raced external step", step_recipe=self.recipe)
            root.steps.add(step)
            before = (root.storage_id, root.file_path, root.file_uid)
        # Only the external provider is a boundary mock. ACL, PostgreSQL locks,
        # graph, request and metadata persistence are all real.
        with patch("cookbook.views.api.get_recipe_provider") as provider:
            response = self._request_during_committed_revocation(
                "patch", f"/api/recipe/{root.pk}/delete_external/", {},
            )
            self._assert_status(response, 404)
            provider.assert_not_called()
        with scopes_disabled():
            root.refresh_from_db()
            self.assertEqual((root.storage_id, root.file_path, root.file_uid), before)

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql", "Este contrato necesita locks PostgreSQL reales.")
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = get_user_model().objects.create_user(
                username="visibility-lock-owner", password="synthetic-only",
            )
            self.observer = get_user_model().objects.create_user(
                username="visibility-lock-observer", password="synthetic-only",
            )
            self.space = Space.objects.create(name="Visibility lock", created_by=self.owner)
            self.household = Household.objects.create(space=self.space, name="Visibility lock home")
            user_group = Group.objects.get_or_create(name="user")[0]
            for user in (self.owner, self.observer):
                membership = UserSpace.objects.create(
                    user=user, space=self.space, household=self.household, active=True,
                )
                membership.groups.add(user_group)
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.INTEGRAL)
            self.unit = Unit.objects.create(space=self.space, name="visibility-lock-kg", base_unit="kg")
            self.recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Visibility lock private recipe",
                servings=Decimal("4"),
                private=True,
            )
            self.recipe.shared.add(self.observer)
            self.food = Food.add_root(
                space=self.space, name="Visibility lock private food", recipe=self.recipe,
            )
            self.public_food = Food.add_root(space=self.space, name="Visibility lock public food")
            self.package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                label="Visibility lock format",
                quantity=Decimal("5"),
                is_reference=True,
            )
            self.price = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("10"),
                valid_from=timezone.now(),
                created_by=self.owner,
            )
            self.supplier = Supermarket.objects.create(space=self.space, name="Visibility lock supplier")
            self.offer = PurchaseOffer.objects.create(
                space=self.space,
                package=self.package,
                supplier=self.supplier,
                amount=Decimal("10"),
                created_by=self.owner,
            )
            self.location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Visibility lock stockroom",
                created_by=self.owner,
            )
            self.private_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.unit,
                amount=Decimal("10"),
                created_by=self.owner,
            )
            self.public_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.public_food,
                unit=self.unit,
                amount=Decimal("0"),
                created_by=self.owner,
            )
            self.order = PurchaseOrder.objects.create(
                space=self.space,
                household=self.household,
                food=self.food,
                unit=self.unit,
                quantity=Decimal("5"),
                supplier=self.supplier,
                supplier_name=self.supplier.name,
                package=self.package,
                package_count=Decimal("1"),
                package_quantity_snapshot=self.package.quantity,
                package_unit_snapshot=self.unit,
                price_snapshot=self.offer.amount,
                state=PurchaseOrder.DRAFT,
                created_by=self.owner,
            )

        self.client = APIClient()
        self.client.force_login(self.observer)
        self.owner_client = APIClient()
        self.owner_client.force_login(self.owner)

    @staticmethod
    def _backend_pid():
        connection.ensure_connection()
        raw_connection = connection.connection
        info = getattr(raw_connection, "info", None)
        pid = getattr(info, "backend_pid", None)
        return pid if pid is not None else raw_connection.get_backend_pid()

    def _wait_for_space_lock(self, worker_pid, holder_pid, done):
        deadline = monotonic() + 3
        samples = []
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    """
                    SELECT wait_event_type, query, pg_blocking_pids(activity.pid),
                           EXISTS (
                               SELECT 1 FROM pg_locks locks
                                WHERE locks.pid = activity.pid
                                  AND locks.relation = 'cookbook_space'::regclass
                                  AND locks.locktype = 'relation'
                                  AND locks.mode = 'RowShareLock' AND locks.granted
                           )
                      FROM pg_stat_activity activity
                     WHERE activity.pid = %s
                       AND datname = current_database()
                       AND backend_type = 'client backend'
                    """,
                    [worker_pid],
                )
                row = cursor.fetchone()
            samples.append(row)
            if (
                row
                and row[0] == "Lock"
                and holder_pid in row[2]
                # track_activity_query_size can truncate the SELECT before
                # FOR UPDATE; pg_locks still proves the acquired table lock.
                and row[3]
                and "cookbook_space" in row[1]
            ):
                return True, samples
            # This Event wait is a bounded poll that also exits as soon as the
            # request finishes; correctness never depends on a chosen sleep.
            if done.wait(0.02):
                break
        return False, samples

    def _request_during_committed_revocation(self, method, path, payload, **headers):
        started = Event()
        done = Event()
        outcome = {}

        def worker():
            close_old_connections()
            try:
                outcome["pid"] = self._backend_pid()
                started.set()
                request = getattr(self.client, method)
                outcome["response"] = request(path, payload, format="json", **headers)
            except Exception as exc:  # Surface thread failures as test failures.
                outcome["error"] = exc
            finally:
                connections.close_all()
                done.set()

        thread = Thread(target=worker, name=f"visibility-lock-{method}", daemon=True)
        observed_lock = False
        samples = []
        with transaction.atomic(), scopes_disabled():
            Space.objects.select_for_update().get(pk=self.space.pk)
            holder_pid = self._backend_pid()
            thread.start()
            self.assertTrue(started.wait(3), "El worker no publicó su conexión PostgreSQL.")
            observed_lock, samples = self._wait_for_space_lock(outcome["pid"], holder_pid, done)
            self.recipe.shared.remove(self.observer)

        thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "La petición siguió viva después de liberar el Space lock.")
        self.assertNotIn("error", outcome, repr(outcome.get("error")))
        self.assertTrue(
            observed_lock,
            f"La escritura no esperó el Space lock observado por PostgreSQL: {samples[-5:]}",
        )
        return outcome["response"]

    @staticmethod
    def _assert_status(response, expected):
        if response.status_code != expected:
            raise AssertionError(getattr(response, "data", response.content))

    def test_package_creation_revalidates_food_visibility_after_space_lock(self):
        with scopes_disabled():
            before = PackageFormat.objects.count()
        response = self._request_during_committed_revocation(
            "post",
            "/api/cuaderno/packages/",
            {"food": self.food.pk, "unit": self.unit.pk, "label": "Raced format", "quantity": "2"},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.assertEqual(PackageFormat.objects.count(), before)

    def test_price_creation_revalidates_package_visibility_after_space_lock(self):
        with scopes_disabled():
            before = PriceVersion.objects.count()
        response = self._request_during_committed_revocation(
            "post",
            f"/api/cuaderno/packages/{self.package.pk}/prices/",
            {"amount": "11", "explicit_free": False},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.assertEqual(PriceVersion.objects.count(), before)

    def test_offer_creation_revalidates_package_visibility_after_space_lock(self):
        with scopes_disabled():
            before = PurchaseOffer.objects.count()
        response = self._request_during_committed_revocation(
            "post",
            "/api/cuaderno/purchase-offers/",
            {"package": self.package.pk, "supplier": self.supplier.pk, "amount": "11"},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.assertEqual(PurchaseOffer.objects.count(), before)

    def test_allergen_creation_revalidates_food_visibility_after_space_lock(self):
        with scopes_disabled():
            before = AllergenDeclaration.objects.count()
        response = self._request_during_committed_revocation(
            "post",
            "/api/cuaderno/allergens/",
            {"food": self.food.pk, "name": "Race allergen", "state": AllergenDeclaration.UNKNOWN},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.assertEqual(AllergenDeclaration.objects.count(), before)

    def test_order_transition_revalidates_visibility_after_space_lock(self):
        response = self._request_during_committed_revocation(
            "post",
            f"/api/cuaderno/purchase-orders/{self.order.pk}/",
            {"action": "order"},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.order.refresh_from_db()
            self.assertEqual(self.order.state, PurchaseOrder.DRAFT)
            self.assertIsNone(self.order.ordered_at)

    def test_receipt_revalidates_order_and_entry_visibility_after_space_lock(self):
        with scopes_disabled():
            self.order.state = PurchaseOrder.ORDERED
            self.order.save(update_fields=["state"])
            before = (PurchaseReceipt.objects.count(), StockMovement.objects.count(), self.private_entry.amount)
        response = self._request_during_committed_revocation(
            "post",
            f"/api/cuaderno/purchase-orders/{self.order.pk}/receipts/",
            {"entry": self.private_entry.pk, "quantity": "1", "idempotency_key": "raced-receipt"},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.private_entry.refresh_from_db()
            self.order.refresh_from_db()
            self.assertEqual(
                (PurchaseReceipt.objects.count(), StockMovement.objects.count(), self.private_entry.amount),
                before,
            )
            self.assertEqual(self.order.received_quantity, Decimal("0"))

    def test_receipt_replay_does_not_bypass_committed_revocation(self):
        with scopes_disabled():
            self.order.state = PurchaseOrder.ORDERED
            self.order.save(update_fields=["state"])
        payload = {
            "entry": self.private_entry.pk,
            "quantity": "1",
            "idempotency_key": "raced-receipt-replay",
        }
        created = self.client.post(
            f"/api/cuaderno/purchase-orders/{self.order.pk}/receipts/",
            payload,
            format="json",
        )
        self._assert_status(created, 201)
        with scopes_disabled():
            self.private_entry.refresh_from_db()
            self.order.refresh_from_db()
            before = (
                PurchaseReceipt.objects.count(), StockMovement.objects.count(),
                self.private_entry.amount, self.order.received_quantity,
            )
        response = self._request_during_committed_revocation(
            "post",
            f"/api/cuaderno/purchase-orders/{self.order.pk}/receipts/",
            payload,
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            self.private_entry.refresh_from_db()
            self.order.refresh_from_db()
            self.assertEqual(
                (
                    PurchaseReceipt.objects.count(), StockMovement.objects.count(),
                    self.private_entry.amount, self.order.received_quantity,
                ),
                before,
            )

    def test_receipt_reversal_revalidates_visibility_after_space_lock(self):
        with scopes_disabled():
            self.order.state = PurchaseOrder.ORDERED
            self.order.save(update_fields=["state"])
        created = self.owner_client.post(
            f"/api/cuaderno/purchase-orders/{self.order.pk}/receipts/",
            {"entry": self.private_entry.pk, "quantity": "1", "idempotency_key": "reversal-seed"},
            format="json",
        )
        self._assert_status(created, 201)
        with scopes_disabled():
            receipt = PurchaseReceipt.objects.get(pk=created.data["id"])
            self.private_entry.refresh_from_db()
            self.order.refresh_from_db()
            before = (StockMovement.objects.count(), self.private_entry.amount, self.order.received_quantity)
        response = self._request_during_committed_revocation(
            "post",
            f"/api/cuaderno/purchase-receipts/{receipt.pk}/reverse/",
            {"idempotency_key": "raced-reversal"},
        )
        self._assert_status(response, 404)
        with scopes_disabled():
            receipt.refresh_from_db()
            self.private_entry.refresh_from_db()
            self.order.refresh_from_db()
            self.assertIsNone(receipt.reversed_by_id)
            self.assertEqual(
                (StockMovement.objects.count(), self.private_entry.amount, self.order.received_quantity),
                before,
            )

    def test_native_inventory_create_revalidates_nested_food_after_space_lock(self):
        with scopes_disabled():
            before = (
                InventoryEntry.objects.count(), InventoryWriteRequest.objects.count(),
                StockMovement.objects.count(),
            )
        response = self._request_during_committed_revocation(
            "post",
            "/api/inventory-entry/",
            {
                "inventory_location": self.location.pk,
                "food": {"id": self.food.pk, "name": self.food.name},
                "unit": self.unit.pk,
                "amount": "1",
            },
            HTTP_IDEMPOTENCY_KEY="raced-native-create",
        )
        self._assert_status(response, 400)
        self.assertNotIn(self.food.name, str(response.data))
        with scopes_disabled():
            self.assertEqual(
                (
                    InventoryEntry.objects.count(), InventoryWriteRequest.objects.count(),
                    StockMovement.objects.count(),
                ),
                before,
            )

    def test_native_inventory_update_revalidates_nested_food_after_space_lock(self):
        with scopes_disabled():
            before = (
                self.public_entry.food_id, self.public_entry.amount,
                InventoryWriteRequest.objects.count(), StockMovement.objects.count(),
            )
        response = self._request_during_committed_revocation(
            "patch",
            f"/api/inventory-entry/{self.public_entry.pk}/",
            {"food": {"id": self.food.pk, "name": self.food.name}},
            HTTP_IDEMPOTENCY_KEY="raced-native-update",
        )
        self._assert_status(response, 400)
        self.assertNotIn(self.food.name, str(response.data))
        with scopes_disabled():
            self.public_entry.refresh_from_db()
            self.assertEqual(
                (
                    self.public_entry.food_id, self.public_entry.amount,
                    InventoryWriteRequest.objects.count(), StockMovement.objects.count(),
                ),
                before,
            )

    def test_native_food_patch_revalidates_object_visibility_after_space_lock(self):
        with scopes_disabled():
            original = self.food.description
            before = Food.objects.count()
        response = self._request_during_committed_revocation(
            "patch",
            f"/api/food/{self.food.pk}/",
            {"description": "Raced private description"},
        )
        self._assert_status(response, 404)
        self.assertNotIn(self.food.name, str(response.data))
        with scopes_disabled():
            self.food.refresh_from_db()
            self.assertEqual(self.food.description, original)
            self.assertEqual(Food.objects.count(), before)

    def test_native_food_patch_revalidates_private_recipe_link_after_space_lock(self):
        with scopes_disabled():
            before = Food.objects.count()
            self.public_food.refresh_from_db()
            self.assertIsNone(self.public_food.recipe_id)
        response = self._request_during_committed_revocation(
            "patch",
            f"/api/food/{self.public_food.pk}/",
            {"recipe": {"id": self.recipe.pk, "name": self.recipe.name}},
        )
        self._assert_status(response, 400)
        self.assertNotIn(self.recipe.name, str(response.data))
        with scopes_disabled():
            self.public_food.refresh_from_db()
            self.assertIsNone(self.public_food.recipe_id)
            self.assertEqual(Food.objects.count(), before)

    def test_native_food_create_revalidates_private_recipe_link_after_space_lock(self):
        with scopes_disabled():
            before = Food.objects.count()
        response = self._request_during_committed_revocation(
            "post",
            "/api/food/",
            {
                "name": "Raced recipe-linked food",
                "recipe": {"id": self.recipe.pk, "name": self.recipe.name},
            },
        )
        self._assert_status(response, 400)
        self.assertNotIn(self.recipe.name, str(response.data))
        with scopes_disabled():
            self.assertEqual(Food.objects.count(), before)
            self.assertFalse(Food.objects.filter(name="Raced recipe-linked food").exists())

    def test_inventory_nested_food_create_revalidates_recipe_link_after_space_lock(self):
        with scopes_disabled():
            before = (
                Food.objects.count(), InventoryEntry.objects.count(),
                InventoryWriteRequest.objects.count(), StockMovement.objects.count(),
            )
        response = self._request_during_committed_revocation(
            "post",
            "/api/inventory-entry/",
            {
                "inventory_location": self.location.pk,
                "food": {
                    "name": "Raced nested recipe food",
                    "recipe": {"id": self.recipe.pk, "name": self.recipe.name},
                },
                "unit": self.unit.pk,
                "amount": "1",
            },
            HTTP_IDEMPOTENCY_KEY="raced-nested-recipe-food",
        )
        self._assert_status(response, 400)
        self.assertNotIn(self.recipe.name, str(response.data))
        with scopes_disabled():
            self.assertEqual(
                (
                    Food.objects.count(), InventoryEntry.objects.count(),
                    InventoryWriteRequest.objects.count(), StockMovement.objects.count(),
                ),
                before,
            )
            self.assertFalse(Food.objects.filter(name="Raced nested recipe food").exists())

    def _assert_denied_stock_race(self, path, payload, **headers):
        with scopes_disabled():
            before = (StockMovement.objects.count(), InventoryWriteRequest.objects.count(), self.private_entry.amount)
        response = self._request_during_committed_revocation("post", path, payload, **headers)
        self._assert_status(response, 404)
        with scopes_disabled():
            self.private_entry.refresh_from_db()
            self.assertEqual(
                (StockMovement.objects.count(), InventoryWriteRequest.objects.count(), self.private_entry.amount),
                before,
            )

    def test_native_consume_revalidates_entry_after_space_lock(self):
        self._assert_denied_stock_race(
            f"/api/inventory-entry/{self.private_entry.pk}/consume/",
            {"quantity": "1"}, HTTP_IDEMPOTENCY_KEY="raced-native-consume",
        )

    def test_movement_creation_revalidates_entry_after_space_lock(self):
        self._assert_denied_stock_race(
            "/api/cuaderno/movements/",
            {"entry": self.private_entry.pk, "kind": StockMovement.CONSUME,
             "quantity": "1", "idempotency_key": "raced-movement"},
        )

    def test_movement_reversal_revalidates_entry_after_space_lock(self):
        created = self.owner_client.post(
            "/api/cuaderno/movements/",
            {"entry": self.private_entry.pk, "kind": StockMovement.RECEIPT,
             "quantity": "1", "idempotency_key": "raced-movement-seed"}, format="json",
        )
        self._assert_status(created, 201)
        with scopes_disabled():
            self.private_entry.refresh_from_db()
        self._assert_denied_stock_race(
            "/api/cuaderno/movements/",
            {"reverse_of": created.data["movement_id"], "idempotency_key": "raced-movement-reverse"},
        )
