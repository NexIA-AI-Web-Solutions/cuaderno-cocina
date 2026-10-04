"""Recipe privacy must follow Food IDs into every operational workflow."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    FoodInheritField,
    Household,
    InventoryEntry,
    InventoryLocation,
    InventoryLog,
    Recipe,
    SearchFields,
    ShoppingList,
    Space,
    Supermarket,
    SupermarketCategory,
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
    StockMinimum,
    StockMovement,
)
from cuaderno.services.ledger import apply_movement


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OperationalFoodVisibilityTests(TestCase):
    def _read_after_dispatch_change(self, client, url, change):
        changed = False
        def intercept(execute, sql, parameters, many, context):
            nonlocal changed
            projection = ('JSON_AGG(' in sql.upper() and
                          ('"cuaderno_packageformat"' in sql or '"cuaderno_stockmovement"' in sql))
            if projection and not changed:
                changed = True
                with scopes_disabled():
                    change()
            return execute(sql, parameters, many, context)
        with connection.execute_wrapper(intercept):
            response = client.get(url)
        self.assertTrue(changed, "The change must occur immediately before the protected projection.")
        self.assert_status(response, 200)
        return response

    def test_list_projection_rechecks_groups_revoked_after_permission_dispatch(self):
        client = self._client(self.observer)
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.observer, space=self.space)
            group = Group.objects.get(name="user")
            apply_movement(entry_id=self.public_entry.pk, space=self.space, user=self.owner,
                           kind=StockMovement.RECEIPT, quantity="1", idempotency_key="race-group-own")
        for url in ("/api/cuaderno/packages/", "/api/cuaderno/movements/"):
            with self.subTest(url=url):
                response = self._read_after_dispatch_change(client, url, membership.groups.clear)
                self.assertEqual(response.data, [])
                with scopes_disabled():
                    membership.groups.add(group)

    def test_movement_projection_uses_household_reassigned_after_permission_dispatch(self):
        client = self._client(self.owner)
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.owner, space=self.space)
            other = Household.objects.create(space=self.space, name="Reassigned at dispatch")
            apply_movement(entry_id=self.public_entry.pk, space=self.space, user=self.owner,
                           kind=StockMovement.RECEIPT, quantity="1", idempotency_key="race-household")
        response = self._read_after_dispatch_change(
            client, "/api/cuaderno/movements/",
            lambda: UserSpace.objects.filter(pk=membership.pk).update(household=other),
        )
        self.assertEqual(response.data, [])

    def test_list_projection_fails_closed_on_second_active_space_after_dispatch(self):
        client = self._client(self.observer)
        response = self._read_after_dispatch_change(
            client, "/api/cuaderno/packages/",
            lambda: UserSpace.objects.create(user=self.observer, space=self.foreign_space, active=True),
        )
        self.assertEqual(response.data, [])

    def test_movement_projection_drops_admin_oversight_revoked_after_dispatch(self):
        client = self._client(self.owner)
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.owner, space=self.space)
            admin = Group.objects.get_or_create(name="admin")[0]
            membership.groups.add(admin)
            other = Household.objects.create(space=self.space, name="Other household during revocation")
            location = InventoryLocation.objects.create(space=self.space, household=other,
                name="Other location during revocation", created_by=self.owner)
            entry = InventoryEntry.objects.create(space=self.space, inventory_location=location,
                food=self.public_food, unit=self.unit, amount=Decimal("1"), created_by=self.owner)
            denied = apply_movement(entry_id=entry.pk, space=self.space, user=self.owner,
                kind=StockMovement.RECEIPT, quantity="1", idempotency_key="race-admin-other")
            allowed = apply_movement(entry_id=self.public_entry.pk, space=self.space, user=self.owner,
                kind=StockMovement.RECEIPT, quantity="1", idempotency_key="race-admin-own")
        response = self._read_after_dispatch_change(client, "/api/cuaderno/movements/",
            lambda: membership.groups.remove(admin))
        identifiers = {row["id"] for row in response.data}
        self.assertIn(allowed.pk, identifiers)
        self.assertNotIn(denied.pk, identifiers)

    def test_guest_native_inventory_reads_keep_household_and_space_boundaries(self):
        client = self._client(self.guest)
        with scopes_disabled():
            other_household = Household.objects.create(space=self.space, name="Other kitchen")
            other_location = InventoryLocation.objects.create(
                space=self.space, household=other_household, name="Other stockroom", created_by=self.owner,
            )
            other_entry = InventoryEntry.objects.create(
                space=self.space, inventory_location=other_location, food=self.public_food,
                unit=self.unit, amount=Decimal("3"), created_by=self.owner,
            )
        for endpoint, allowed, denied in (
            ("inventory-entry", self.public_entry, other_entry),
            ("inventory-location", self.location, other_location),
            ("unit", self.unit, self.foreign_unit),
        ):
            with self.subTest(endpoint=endpoint):
                response = client.get(f"/api/{endpoint}/")
                self.assert_status(response, 200)
                ids = {row["id"] for row in self._rows(response)}
                self.assertIn(allowed.pk, ids)
                self.assertNotIn(denied.pk, ids)
                self.assert_status(client.get(f"/api/{endpoint}/{allowed.pk}/"), 200)
                self.assert_status(client.head(f"/api/{endpoint}/{allowed.pk}/"), 200)
                self.assert_status(client.get(f"/api/{endpoint}/{denied.pk}/"), 404)
        entry_ids = {row["id"] for row in self._rows(client.get("/api/inventory-entry/"))}
        self.assertNotIn(self.private_entry.pk, entry_ids)
        self.assertNotIn(self.corrupt_entry.pk, entry_ids)

    def test_guest_native_inventory_private_sharing_revokes_without_relogin(self):
        client = self._client(self.guest)
        path = f"/api/inventory-entry/{self.private_entry.pk}/"
        self.assert_status(client.get(path), 404)
        with scopes_disabled():
            self.private_recipe.shared.add(self.guest)
        self.assert_status(client.get(path), 200)
        with scopes_disabled():
            self.private_recipe.shared.remove(self.guest)
        self.assert_status(client.get(path), 404)
        response = client.get("/api/inventory-entry/")
        self.assert_status(response, 200)
        self.assertNotIn(self.private_entry.pk, {row["id"] for row in self._rows(response)})

    def test_guest_native_reads_fail_closed_when_household_or_membership_is_revoked(self):
        client = self._client(self.guest)
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.guest, space=self.space)
            membership.household = None
            membership.save(update_fields=["household"])
        for endpoint in ("inventory-entry", "inventory-location"):
            response = client.get(f"/api/{endpoint}/")
            self.assert_status(response, 200)
            self.assertEqual(self._rows(response), [])
        with scopes_disabled():
            membership.groups.clear()
        for endpoint in ("inventory-entry", "inventory-location", "unit"):
            self.assert_status(client.get(f"/api/{endpoint}/"), 403)

    def test_guest_native_mutations_and_relation_inspection_stay_forbidden(self):
        client = self._client(self.guest)
        for endpoint, obj in (
            ("inventory-entry", self.public_entry), ("inventory-location", self.location), ("unit", self.unit),
        ):
            for method, path in (
                ("post", f"/api/{endpoint}/"),
                ("patch", f"/api/{endpoint}/{obj.pk}/"),
                ("delete", f"/api/{endpoint}/{obj.pk}/"),
                ("get", f"/api/{endpoint}/{obj.pk}/protecting/"),
                ("get", f"/api/{endpoint}/{obj.pk}/cascading/"),
            ):
                with self.subTest(endpoint=endpoint, method=method, path=path):
                    self.assert_status(self._request(client, method, path), 403)
        self.assert_status(client.post(f"/api/inventory-entry/{self.public_entry.pk}/consume/", {"quantity": "1"}, format="json"), 403)
        self.assert_status(client.put(f"/api/unit/{self.unit.pk}/merge/{self.foreign_unit.pk}/", {}, format="json"), 403)
        with scopes_disabled():
            self.public_entry.refresh_from_db()
            self.assertEqual(self.public_entry.amount, Decimal("4"))

    def test_space_inheritance_reset_cannot_mutate_unshared_private_foods(self):
        admin = self._admin_client("inheritance-reset")
        with scopes_disabled():
            inherited = FoodInheritField.objects.get_or_create(field="ignore_shopping")[0]
            self.private_food.inherit_fields.add(inherited)
            self.foreign_food.inherit_fields.add(inherited)
            before = list(Food.inherit_fields.through.objects.order_by("pk").values_list(
                "pk", "food_id", "foodinheritfield_id",
            ))
        response = admin.post("/api/reset-food-inheritance/", {}, format="json")
        self.assert_status(response, 400)
        with scopes_disabled():
            self.assertEqual(list(Food.inherit_fields.through.objects.order_by("pk").values_list(
                "pk", "food_id", "foodinheritfield_id",
            )), before)

    def test_native_inventory_nested_food_preserves_the_authorized_recipe_identity(self):
        self._share()
        response = self.client.post("/api/inventory-entry/", {
            "food": {"name": "Nested authorized food", "recipe": {
                "id": self.private_recipe.pk, "name": self.private_recipe.name,
            }},
            "unit": self.unit.pk, "inventory_location": self.location.pk, "amount": "1",
        }, format="json", HTTP_IDEMPOTENCY_KEY="nested-authorized-food")
        self.assert_status(response, 201)
        with scopes_disabled():
            food = Food.objects.get(space=self.space, name="Nested authorized food")
            self.assertEqual(food.recipe_id, self.private_recipe.pk)

    def test_parent_update_cannot_cascade_into_private_descendant(self):
        with scopes_disabled():
            inherited = FoodInheritField.objects.get_or_create(field="ignore_shopping")[0]
            child = self.public_food.add_child(
                space=self.space, name="Private inherited child", recipe=self.private_recipe,
                ignore_shopping=False,
            )
            child.inherit_fields.add(inherited)
        response = self.client.patch(
            f"/api/food/{self.public_food.pk}/", {"ignore_shopping": True, "reset_inherit": True}, format="json",
        )
        self.assert_status(response, 400)
        with scopes_disabled():
            child.refresh_from_db()
            self.public_food.refresh_from_db()
            self.assertFalse(child.ignore_shopping)
            self.assertFalse(self.public_food.ignore_shopping)
            self.assertEqual(list(child.inherit_fields.values_list("pk", flat=True)), [inherited.pk])

    def test_reset_inherit_preserves_unrelated_local_and_foreign_food_fields(self):
        with scopes_disabled():
            inherited = FoodInheritField.objects.get_or_create(field="ignore_shopping")[0]
            self.foreign_food.inherit_fields.add(inherited)
            self.private_food.inherit_fields.add(inherited)
            self.public_food.child_inherit_fields.add(inherited)
            child = self.public_food.add_child(space=self.space, name="Public reset child")
        response = self.client.patch(
            f"/api/food/{self.public_food.pk}/", {"ignore_shopping": True, "reset_inherit": True}, format="json",
        )
        self.assert_status(response, 200)
        with scopes_disabled():
            for food in (self.foreign_food, self.private_food):
                self.assertEqual(list(food.inherit_fields.values_list("pk", flat=True)), [inherited.pk])
            child.refresh_from_db()
            self.assertTrue(child.ignore_shopping)
            self.assertEqual(list(child.inherit_fields.values_list("pk", flat=True)), [inherited.pk])

    def test_merge_rejects_hidden_or_foreign_substitute_counterparts_without_writes(self):
        with scopes_disabled():
            target = Food.add_root(space=self.space, name="Public merge target")
        for other in (self.private_food, self.foreign_food):
            with self.subTest(other=other.pk), scopes_disabled():
                self.public_food.substitute.clear()
                self.public_food.substitute.add(other)
                before = list(Food.substitute.through.objects.order_by("pk").values_list(
                    "pk", "from_food_id", "to_food_id",
                ))
                food_count = Food.objects.count()
                response = self.client.put(f"/api/food/{self.public_food.pk}/merge/{target.pk}/", {}, format="json")
                self.assert_status(response, 400)
                self.assertEqual(Food.objects.count(), food_count)
                self.assertEqual(list(Food.substitute.through.objects.order_by("pk").values_list(
                    "pk", "from_food_id", "to_food_id",
                )), before)

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = self._new_user("food-visibility-owner")
            self.observer = self._new_user("food-visibility-observer")
            self.guest = self._new_user("food-visibility-guest")
            self.foreign_owner = self._new_user("food-visibility-foreign")
            self.space = Space.objects.create(name="Food visibility", created_by=self.owner)
            self.foreign_space = Space.objects.create(
                name="Foreign food visibility", created_by=self.foreign_owner,
            )
            self.household = Household.objects.create(space=self.space, name="Shared kitchen")
            user_group = Group.objects.get_or_create(name="user")[0]
            guest_group = Group.objects.get_or_create(name="guest")[0]
            for user, group in (
                (self.owner, user_group),
                (self.observer, user_group),
                (self.guest, guest_group),
            ):
                membership = UserSpace.objects.create(
                    user=user, space=self.space, household=self.household, active=True,
                )
                membership.groups.add(group)
            SpaceProfile.objects.create(
                space=self.space, edition=SpaceProfile.INTEGRAL,
                currency="EUR", price_policy=SpaceProfile.NET,
            )

            self.unit = Unit.objects.create(
                space=self.space, name="visibility kg", base_unit="kg",
            )
            self.foreign_unit = Unit.objects.create(
                space=self.foreign_space, name="foreign visibility kg", base_unit="kg",
            )
            self.public_food = Food.add_root(space=self.space, name="Public visibility food")
            self.private_recipe = Recipe.objects.create(
                space=self.space, created_by=self.owner,
                name="Private visibility recipe", servings=4, private=True,
            )
            self.private_food = Food.add_root(
                space=self.space, name="Private visibility food", recipe=self.private_recipe,
            )
            self.foreign_food = Food.add_root(space=self.foreign_space, name="Foreign visibility food")
            self.visible_recipe = Recipe.objects.create(
                space=self.space, created_by=self.observer,
                name="Visible impact recipe", servings=4,
            )
            self.public_package = self._package(
                self.public_food, self.unit, "Public visibility package",
            )
            self.private_package = self._package(
                self.private_food, self.unit, "Private visibility package",
            )
            self.corrupt_package = self._package(
                self.foreign_food, self.foreign_unit, "Foreign relations package",
            )
            now = timezone.now()
            self.private_price = PriceVersion.objects.create(
                space=self.space, package=self.private_package, amount=Decimal("12"),
                valid_from=now, note="Private price marker", created_by=self.owner,
            )
            self.public_price = PriceVersion.objects.create(
                space=self.space, package=self.public_package, amount=Decimal("8"),
                valid_from=now, created_by=self.owner,
            )
            self.supplier = Supermarket.objects.create(space=self.space, name="Visible supplier")
            self.foreign_supplier = Supermarket.objects.create(
                space=self.foreign_space, name="Foreign supplier marker",
            )
            self.private_offer = PurchaseOffer.objects.create(
                space=self.space, package=self.private_package, supplier=self.supplier,
                amount=Decimal("11"), valid_from=now, created_by=self.owner,
            )
            self.location = InventoryLocation.objects.create(
                space=self.space, household=self.household,
                name="Shared stockroom", created_by=self.owner,
            )
            self.private_entry = self._entry(self.private_food, self.unit, "10")
            self.public_entry = self._entry(self.public_food, self.unit, "4")
            self.corrupt_entry = self._entry(self.foreign_food, self.foreign_unit, "2")
            self.private_order = PurchaseOrder.objects.create(
                space=self.space, household=self.household, food=self.private_food,
                unit=self.unit, quantity=Decimal("5"), supplier=self.supplier,
                supplier_name=self.supplier.name, package=self.private_package,
                package_count=Decimal("1"), package_quantity_snapshot=Decimal("5"),
                package_unit_snapshot=self.unit, price_snapshot=Decimal("11"),
                currency_snapshot="EUR", state=PurchaseOrder.ORDERED, created_by=self.owner,
            )
            self.public_minimum = self._minimum(self.public_food, self.unit, "1")
            self.private_minimum = self._minimum(self.private_food, self.unit, "3")
            self.corrupt_minimum = self._minimum(self.foreign_food, self.foreign_unit, "2")
            self.private_movement = apply_movement(
                entry_id=self.private_entry.pk,
                space=self.space,
                user=self.owner,
                kind=StockMovement.RECEIPT,
                quantity="1",
                idempotency_key="private-visibility-seed",
            )
            self.private_entry.refresh_from_db()

        self.client = self._client(self.observer)

    @staticmethod
    def _new_user(username):
        return get_user_model().objects.create_user(
            username=username, password="synthetic-only",
        )

    @staticmethod
    def _client(user):
        client = APIClient()
        client.force_login(user)
        return client

    def _package(self, food, unit, label):
        return PackageFormat.objects.create(
            space=self.space,
            food=food,
            unit=unit,
            label=label,
            quantity=Decimal("5"),
            is_reference=True,
        )

    def _entry(self, food, unit, amount):
        return InventoryEntry.objects.create(
            space=self.space, inventory_location=self.location, food=food,
            unit=unit, amount=Decimal(amount), created_by=self.owner,
        )

    def _minimum(self, food, unit, quantity):
        return StockMinimum.objects.create(
            space=self.space, household=self.household, food=food,
            unit=unit, quantity=Decimal(quantity), updated_by=self.owner,
        )

    def _share(self):
        with scopes_disabled():
            self.private_recipe.shared.add(self.observer)

    def _revoke(self):
        with scopes_disabled():
            self.private_recipe.shared.remove(self.observer)

    @staticmethod
    def _rows(response):
        if isinstance(response.data, list):
            return response.data
        return response.data.get("results", response.data.get("items", []))

    def assert_status(self, response, status):
        self.assertEqual(
            response.status_code,
            status,
            getattr(response, "data", response.content),
        )

    @staticmethod
    def _request(client, method, path, data=None):
        return getattr(client, method)(path, data or {}, format="json")

    @staticmethod
    def _write_counts():
        with scopes_disabled():
            return tuple(model.objects.count() for model in (
                PackageFormat, PriceVersion, PurchaseOffer, PurchaseOrder,
                PurchaseReceipt, StockMinimum, StockMovement, InventoryLog,
                AllergenDeclaration,
            ))

    @staticmethod
    def _food_count():
        with scopes_disabled():
            return Food.objects.count()

    def _admin_client(self, suffix):
        with scopes_disabled():
            admin = self._new_user(f"food-visibility-admin-{suffix}")
            membership = UserSpace.objects.create(
                user=admin, space=self.space, household=self.household, active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="admin")[0])
        return self._client(admin)

    def _branch_with_hidden_descendant(self, suffix):
        with scopes_disabled():
            author = self._new_user(f"food-branch-author-{suffix}")
            membership = UserSpace.objects.create(
                user=author, space=self.space, household=self.household, active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            hidden_recipe = Recipe.objects.create(
                space=self.space,
                created_by=author,
                name=f"Hidden branch recipe {suffix}",
                servings=Decimal("1"),
                private=True,
            )
            root = Food.add_root(space=self.space, name=f"Public branch root {suffix}")
            branch = root.add_child(space=self.space, name=f"Public branch node {suffix}")
            hidden = branch.add_child(
                space=self.space,
                name=f"Hidden branch leaf {suffix}",
                recipe=hidden_recipe,
            )
            other = Food.add_root(space=self.space, name=f"Public structural peer {suffix}")
        return root, branch, hidden, other

    def _order_payload(self, *, package=None, offer=None, supplier=None):
        package = package or self.private_package
        return {
            "quantity": "5",
            "package": package.pk,
            "package_count": "1",
            "supplier": (supplier or self.supplier).pk,
            "offer": (offer or self.private_offer).pk,
        }

    def test_package_create_and_price_history_follow_share_and_revocation(self):
        before = (PackageFormat.objects.count(), PriceVersion.objects.count())
        denied_package = self.client.post(
            "/api/cuaderno/packages/",
            {
                "food": self.private_food.pk,
                "unit": self.unit.pk,
                "label": "Denied private package",
                "quantity": "2",
            },
            format="json",
        )
        self.assert_status(denied_package, 404)
        history_url = f"/api/cuaderno/packages/{self.private_package.pk}/prices/"
        self.assert_status(self.client.get(history_url), 404)
        self.assert_status(
            self.client.post(
                history_url, {"amount": "13", "explicit_free": False}, format="json",
            ),
            404,
        )
        self.assertEqual((PackageFormat.objects.count(), PriceVersion.objects.count()), before)

        self._share()
        self.assert_status(self.client.get(history_url), 200)
        self.assert_status(
            self.client.post(
                history_url, {"amount": "13", "explicit_free": False}, format="json",
            ),
            201,
        )
        self.assert_status(
            self.client.post(
                "/api/cuaderno/packages/",
                {
                    "food": self.private_food.pk,
                    "unit": self.unit.pk,
                    "label": "Shared private package",
                    "quantity": "2",
                },
                format="json",
            ),
            201,
        )
        self._revoke()
        after_share = (PackageFormat.objects.count(), PriceVersion.objects.count())
        self.assert_status(self.client.get(history_url), 404)
        self.assert_status(
            self.client.post(
                history_url, {"amount": "14", "explicit_free": False}, format="json",
            ),
            404,
        )
        self.assertEqual((PackageFormat.objects.count(), PriceVersion.objects.count()), after_share)

    def test_offers_orders_and_receipts_follow_private_food_visibility(self):
        offers_url = "/api/cuaderno/purchase-offers/"
        orders_url = "/api/cuaderno/purchase-orders/"
        receipt_url = f"{orders_url}{self.private_order.pk}/receipts/"
        before = (
            PurchaseOffer.objects.count(),
            PurchaseOrder.objects.count(),
            PurchaseReceipt.objects.count(),
            StockMovement.objects.count(),
            self.private_entry.amount,
        )
        offers = self.client.get(offers_url)
        orders = self.client.get(orders_url)
        self.assert_status(offers, 200)
        self.assert_status(orders, 200)
        self.assertNotIn(self.private_offer.pk, {row["id"] for row in offers.data})
        self.assertNotIn(self.private_order.pk, {row["id"] for row in orders.data})
        self.assert_status(
            self.client.post(
                offers_url,
                {
                    "package": self.private_package.pk,
                    "supplier": self.supplier.pk,
                    "amount": "12",
                },
                format="json",
            ),
            404,
        )
        self.assert_status(self.client.post(orders_url, self._order_payload(), format="json"), 404)
        self.assert_status(
            self.client.post(
                receipt_url,
                {
                    "entry": self.private_entry.pk,
                    "quantity": "1",
                    "idempotency_key": "private-receipt-denied",
                },
                format="json",
            ),
            404,
        )
        self.private_entry.refresh_from_db()
        self.assertEqual(
            (
                PurchaseOffer.objects.count(),
                PurchaseOrder.objects.count(),
                PurchaseReceipt.objects.count(),
                StockMovement.objects.count(),
                self.private_entry.amount,
            ),
            before,
        )

        self._share()
        self.assertIn(self.private_offer.pk, {row["id"] for row in self.client.get(offers_url).data})
        self.assertIn(self.private_order.pk, {row["id"] for row in self.client.get(orders_url).data})
        self.assert_status(self.client.post(offers_url, {
            "package": self.private_package.pk,
            "supplier": self.supplier.pk,
            "amount": "12",
        }, format="json"), 201)
        self.assert_status(
            self.client.post(orders_url, self._order_payload(), format="json"), 201,
        )
        received = self.client.post(
            receipt_url,
            {
                "entry": self.private_entry.pk,
                "quantity": "1",
                "idempotency_key": "private-receipt-shared",
            },
            format="json",
        )
        self.assert_status(received, 201)
        self._revoke()
        denied_counts = (PurchaseReceipt.objects.count(), StockMovement.objects.count())
        self.assert_status(self.client.get(f"{orders_url}{self.private_order.pk}/"), 404)
        self.assert_status(
            self.client.post(
                receipt_url,
                {
                    "entry": self.private_entry.pk,
                    "quantity": "1",
                    "idempotency_key": "private-receipt-revoked",
                },
                format="json",
            ),
            404,
        )
        self.assertEqual((PurchaseReceipt.objects.count(), StockMovement.objects.count()), denied_counts)

    def test_minimums_and_replenishment_filter_hidden_and_corrupt_foods(self):
        minimum_url = "/api/cuaderno/stock-minimums/"
        replenishment_url = "/api/cuaderno/replenishment/"
        before = StockMinimum.objects.count()
        minimums = self.client.get(minimum_url)
        replenishment = self.client.post(replenishment_url, {}, format="json")
        self.assert_status(minimums, 200)
        self.assert_status(replenishment, 200)
        self.assertEqual(
            {row["id"] for row in minimums.data["items"]},
            {self.public_minimum.pk},
        )
        self.assertEqual(
            {row["food"] for row in replenishment.data["items"]},
            {self.public_food.pk},
        )
        self.assertNotIn(self.private_food.name, str(minimums.data))
        self.assertNotIn(self.foreign_food.name, str(minimums.data))
        self.assert_status(
            self.client.put(
                minimum_url,
                {
                    "food": self.private_food.pk,
                    "unit": self.unit.pk,
                    "quantity": "4",
                    "location": None,
                },
                format="json",
            ),
            404,
        )
        self.assertEqual(StockMinimum.objects.count(), before)

        self._share()
        shared = self.client.get(minimum_url)
        self.assert_status(shared, 200)
        self.assertIn(self.private_minimum.pk, {row["id"] for row in shared.data["items"]})
        self.assert_status(self.client.put(minimum_url, {
            "food": self.private_food.pk,
            "unit": self.unit.pk,
            "quantity": "4",
            "location": None,
        }, format="json"), 200)
        shared_replenishment = self.client.post(replenishment_url, {}, format="json")
        self.assert_status(shared_replenishment, 200)
        self.assertIn(
            self.private_food.pk,
            {row["food"] for row in shared_replenishment.data["items"]},
        )
        self._revoke()
        revoked = self.client.get(minimum_url)
        self.assert_status(revoked, 200)
        self.assertEqual({row["id"] for row in revoked.data["items"]}, {self.public_minimum.pk})

    def test_movements_and_native_inventory_follow_private_food_visibility(self):
        movement_url = "/api/cuaderno/movements/"
        entries_url = "/api/inventory-entry/?empty=true"
        logs_url = f"/api/inventory-log/?entry_id={self.private_entry.pk}"
        movement_rows = self.client.get(movement_url)
        entries = self.client.get(entries_url)
        logs = self.client.get(logs_url)
        self.assert_status(movement_rows, 200)
        self.assert_status(entries, 200)
        self.assert_status(logs, 200)
        self.assertNotIn(self.private_movement.pk, {row["id"] for row in movement_rows.data})
        self.assertNotIn(
            self.private_entry.pk,
            {row["id"] for row in self._rows(entries)},
        )
        self.assertNotIn(
            self.corrupt_entry.pk,
            {row["id"] for row in self._rows(entries)},
        )
        self.assertEqual(self._rows(logs), [])
        self.assertNotIn(self.private_food.name, str(movement_rows.data))

        def private_entry_state():
            with scopes_disabled():
                self.private_entry.refresh_from_db()
                return (
                    self.private_entry.amount,
                    StockMovement.objects.count(),
                    InventoryLog.objects.count(),
                )

        before = private_entry_state()
        self.assert_status(
            self.client.post(
                movement_url,
                {
                    "entry": self.private_entry.pk,
                    "kind": StockMovement.RECEIPT,
                    "quantity": "1",
                    "idempotency_key": "private-movement-denied",
                },
                format="json",
            ),
            404,
        )
        self.assert_status(
            self.client.post(
                f"/api/inventory-entry/{self.private_entry.pk}/consume/",
                {"quantity": "1"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="private-native-denied",
            ),
            404,
        )
        self.assertEqual(private_entry_state(), before)

        self._share()
        shared_entries = self.client.get(entries_url)
        self.assert_status(shared_entries, 200)
        self.assertIn(
            self.private_entry.pk,
            {row["id"] for row in self._rows(shared_entries)},
        )
        shared_payload = {
            "entry": self.private_entry.pk, "kind": StockMovement.RECEIPT,
            "quantity": "1", "idempotency_key": "private-movement-shared",
        }
        self.assert_status(self.client.post(movement_url, shared_payload, format="json"), 201)
        self._revoke()
        revoked_entries = self.client.get(entries_url)
        self.assertNotIn(
            self.private_entry.pk,
            {row["id"] for row in self._rows(revoked_entries)},
        )
        after_revoke = self._write_counts()
        shared_payload["idempotency_key"] = "private-movement-revoked"
        self.assert_status(self.client.post(movement_url, shared_payload, format="json"), 404)
        self.assertEqual(self._write_counts(), after_revoke)

    def test_price_impact_and_allergen_writes_require_visible_food(self):
        impact_url = (
            f"/api/cuaderno/recipes/{self.visible_recipe.pk}/price-impact/"
            f"?package={self.private_package.pk}&servings=4"
        )
        allergen_url = "/api/cuaderno/allergens/"
        allergen_payload = {
            "food": self.private_food.pk,
            "name": "Private allergen marker",
            "state": AllergenDeclaration.UNKNOWN,
        }
        before = AllergenDeclaration.objects.count()
        self.assert_status(self.client.get(impact_url), 404)
        self.assert_status(self.client.post(allergen_url, allergen_payload, format="json"), 404)
        self.assertEqual(AllergenDeclaration.objects.count(), before)

        self._share()
        impact = self.client.get(impact_url)
        self.assert_status(impact, 200)
        self.assertFalse(impact.data["affected"])
        self.assert_status(self.client.post(allergen_url, allergen_payload, format="json"), 201)
        self._revoke()
        after_share = AllergenDeclaration.objects.count()
        self.assert_status(self.client.get(impact_url), 404)
        self.assert_status(self.client.post(allergen_url, allergen_payload, format="json"), 404)
        self.assertEqual(AllergenDeclaration.objects.count(), after_share)

    def test_native_food_reads_and_writes_follow_private_recipe_visibility(self):
        list_url = "/api/food/"
        simple_url = "/api/food/?simple=true"
        detail_url = f"/api/food/{self.private_food.pk}/"
        simple_detail_url = f"{detail_url}?simple=true"

        def listed_ids(response):
            self.assert_status(response, 200)
            return {row["id"] for row in self._rows(response)}

        owner = self._client(self.owner)
        self.assertIn(self.private_food.pk, listed_ids(owner.get(list_url)))
        owner_detail = owner.get(detail_url)
        self.assert_status(owner_detail, 200)
        self.assertEqual(owner_detail.data["recipe"]["id"], self.private_recipe.pk)

        guest = self._client(self.guest)
        for role, client in (("observer", self.client), ("guest", guest)):
            with self.subTest(role=role, representation="full"):
                response = client.get(list_url)
                self.assertNotIn(self.private_food.pk, listed_ids(response))
                self.assertNotIn(self.private_recipe.name, str(response.data))
            with self.subTest(role=role, representation="simple"):
                self.assertNotIn(self.private_food.pk, listed_ids(client.get(simple_url)))
            self.assert_status(client.get(detail_url), 404)
            self.assert_status(client.get(simple_detail_url), 404)
        self.assert_status(guest.get(f"/api/food/{self.public_food.pk}/"), 200)

        original = (
            self.private_food.name, self.private_food.description,
            self.private_food.recipe_id, self._food_count(),
        )
        denied_writes = (
            ("put", {"name": "Denied replacement"}),
            ("patch", {"description": "Denied private mutation"}),
        )
        for method, payload in denied_writes:
            with self.subTest(method=method, phase="hidden"):
                self.assert_status(
                    getattr(self.client, method)(detail_url, payload, format="json"), 404,
                )
        self.private_food.refresh_from_db()
        self.assertEqual(
            (self.private_food.name, self.private_food.description,
             self.private_food.recipe_id, self._food_count()),
            original,
        )

        self._share()
        self.assertIn(self.private_food.pk, listed_ids(self.client.get(list_url)))
        shared_detail = self.client.get(detail_url)
        self.assert_status(shared_detail, 200)
        self.assertEqual(shared_detail.data["recipe"]["id"], self.private_recipe.pk)
        self._revoke()
        self.assertNotIn(self.private_food.pk, listed_ids(self.client.get(simple_url)))
        self.assert_status(
            self.client.patch(
                detail_url, {"description": "Denied after revocation"}, format="json",
            ),
            404,
        )
        self.private_food.refresh_from_db()
        self.assertEqual(self.private_food.description, original[1])

    def test_native_inventory_nested_food_writes_follow_sharing_and_scope(self):
        entries_url = "/api/inventory-entry/"
        public_detail = f"{entries_url}{self.public_entry.pk}/"

        def payload(food, *, unit=None):
            return {
                "inventory_location": self.location.pk,
                "food": {"id": food.pk, "name": food.name},
                "unit": (unit or self.unit).pk,
                "amount": "1",
            }

        def inventory_state():
            with scopes_disabled():
                self.public_entry.refresh_from_db()
                return (
                    InventoryEntry.objects.count(), InventoryWriteRequest.objects.count(),
                    StockMovement.objects.count(), InventoryLog.objects.count(),
                    self.public_entry.food_id, self.public_entry.amount,
                )

        hidden_payload = payload(self.private_food)
        before = inventory_state()
        denied_create = self.client.post(
            entries_url, hidden_payload, format="json",
            HTTP_IDEMPOTENCY_KEY="hidden-nested-create",
        )
        self.assert_status(denied_create, 400)
        self.assertNotIn(self.private_food.name, str(denied_create.data))
        self.assertEqual(inventory_state(), before)

        denied_patch = self.client.patch(
            public_detail, {"food": hidden_payload["food"]}, format="json",
            HTTP_IDEMPOTENCY_KEY="hidden-nested-patch",
        )
        self.assert_status(denied_patch, 400)
        self.assertNotIn(self.private_food.name, str(denied_patch.data))
        self.assertEqual(inventory_state(), before)

        self._share()
        first = self.client.post(
            entries_url, hidden_payload, format="json",
            HTTP_IDEMPOTENCY_KEY="shared-nested-create",
        )
        self.assert_status(first, 201)
        after_first = inventory_state()
        replay = self.client.post(
            entries_url, hidden_payload, format="json",
            HTTP_IDEMPOTENCY_KEY="shared-nested-create",
        )
        self.assert_status(replay, 201)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(inventory_state(), after_first)

        self._revoke()
        revoked_replay = self.client.post(
            entries_url, hidden_payload, format="json",
            HTTP_IDEMPOTENCY_KEY="shared-nested-create",
        )
        self.assert_status(revoked_replay, 400)
        self.assertNotIn(self.private_food.name, str(revoked_replay.data))
        self.assertEqual(inventory_state(), after_first)

        foreign_unit = self.client.post(
            entries_url, payload(self.public_food, unit=self.foreign_unit), format="json",
            HTTP_IDEMPOTENCY_KEY="foreign-unit-nested-create",
        )
        self.assert_status(foreign_unit, 400)
        self.assertNotIn(self.foreign_unit.name, str(foreign_unit.data))
        self.assertEqual(inventory_state(), after_first)

    def test_nullable_legacy_inventory_serializes_without_unsafe_food_label(self):
        with scopes_disabled():
            entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=None,
                unit=None,
                amount=Decimal("1.25"),
                code="LEGACY-NULL",
                created_by=self.owner,
            )
            log = InventoryLog.objects.create(
                space=self.space,
                entry=entry,
                booking_type=InventoryLog.B_ADD,
                old_amount=Decimal("0"),
                new_amount=entry.amount,
                old_inventory_location=self.location,
                new_inventory_location=self.location,
                note="Legacy nullable row",
            )
            movement = StockMovement.objects.create(
                space=self.space,
                entry=entry,
                kind=StockMovement.RECEIPT,
                quantity=entry.amount,
                idempotency_key="legacy-nullable-row",
                fingerprint="legacy-nullable-row-fingerprint",
                balance_after=entry.amount,
                metadata_snapshot={},
                created_by=self.owner,
            )

        entries = self.client.get("/api/inventory-entry/?empty=true")
        logs = self.client.get(f"/api/inventory-log/?entry_id={entry.pk}")
        movements = self.client.get("/api/cuaderno/movements/")
        self.assert_status(entries, 200)
        self.assert_status(logs, 200)
        self.assert_status(movements, 200)
        entry_row = next(row for row in self._rows(entries) if row["id"] == entry.pk)
        log_row = next(row for row in self._rows(logs) if row["id"] == log.pk)
        self.assertIn("LEGACY-NULL", entry_row["label"])
        self.assertIn("sin alimento", entry_row["label"].casefold())
        self.assertEqual(log_row["entry"]["label"], entry_row["label"])
        self.assertIsNone(entry_row["food"])
        self.assertIsNone(entry_row["unit"])
        self.assertIn(movement.pk, {row["id"] for row in movements.data})

    def test_replenishment_ignores_nullable_and_foreign_unit_stock_rows(self):
        with scopes_disabled():
            null_unit = self._entry(self.public_food, None, "100")
            foreign_unit = self._entry(self.public_food, self.foreign_unit, "200")
            orders_before = PurchaseOrder.objects.count()

        response = self.client.post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_status(response, 200)
        row = next(item for item in response.data["items"] if item["food"] == self.public_food.pk)
        self.assertEqual(Decimal(row["usable_stock"]), Decimal("4"))
        self.assertEqual(Decimal(row["target_stock"]), Decimal("1"))
        self.assertEqual(Decimal(row["missing"]), Decimal("0"))
        with scopes_disabled():
            self.assertTrue(InventoryEntry.objects.filter(pk=null_unit.pk).exists())
            self.assertTrue(InventoryEntry.objects.filter(pk=foreign_unit.pk).exists())
            self.assertEqual(PurchaseOrder.objects.count(), orders_before)

    def test_corrupt_orders_and_cross_space_recipe_food_remain_hidden_from_admins(self):
        with scopes_disabled():
            admin = self._new_user("food-visibility-admin")
            membership = UserSpace.objects.create(
                user=admin, space=self.space, household=self.household, active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="admin")[0])
            other_unit = Unit.objects.create(
                space=self.space, name="visibility alternate kg", base_unit="kg",
            )
            corrupt_order = PurchaseOrder.objects.create(
                space=self.space,
                household=self.household,
                food=self.private_food,
                unit=other_unit,
                quantity=Decimal("5"),
                package=self.public_package,
                package_count=Decimal("1"),
                package_quantity_snapshot=self.public_package.quantity,
                package_unit_snapshot=self.public_package.unit,
                state=PurchaseOrder.DRAFT,
                created_by=self.owner,
            )
            foreign_recipe = Recipe.objects.create(
                space=self.foreign_space,
                created_by=self.foreign_owner,
                name="Foreign recipe link marker",
                servings=Decimal("1"),
                private=False,
            )
            cross_recipe_food = Food.add_root(
                space=self.space,
                name="Cross-space recipe food marker",
                recipe=foreign_recipe,
            )

        admin_client = self._client(admin)
        for role, client in (("observer", self.client), ("admin", admin_client)):
            with self.subTest(role=role, resource="food"):
                foods = client.get("/api/food/?simple=true")
                self.assert_status(foods, 200)
                self.assertNotIn(cross_recipe_food.pk, {row["id"] for row in self._rows(foods)})
                self.assert_status(client.get(f"/api/food/{cross_recipe_food.pk}/"), 404)
                self.assertNotIn(cross_recipe_food.name, str(foods.data))
            with self.subTest(role=role, resource="orders"):
                orders = client.get("/api/cuaderno/purchase-orders/")
                self.assert_status(orders, 200)
                ids = {row["id"] for row in orders.data}
                self.assertNotIn(corrupt_order.pk, ids)
                self.assertNotIn(self.private_order.pk, ids)

        owner_orders = self._client(self.owner).get("/api/cuaderno/purchase-orders/")
        self.assert_status(owner_orders, 200)
        self.assertIn(self.private_order.pk, {row["id"] for row in owner_orders.data})
        self.assertNotIn(corrupt_order.pk, {row["id"] for row in owner_orders.data})
        self._share()
        shared_orders = self.client.get("/api/cuaderno/purchase-orders/")
        self.assert_status(shared_orders, 200)
        self.assertIn(self.private_order.pk, {row["id"] for row in shared_orders.data})
        self.assertNotIn(corrupt_order.pk, {row["id"] for row in shared_orders.data})

    def test_food_merge_move_and_batch_reject_hidden_sources_and_targets(self):
        with scopes_disabled():
            merge_source = Food.add_root(
                space=self.space, name="Private merge source", recipe=self.private_recipe,
            )
            merge_target = Food.add_root(space=self.space, name="Public merge target")
            public_source = Food.add_root(space=self.space, name="Public merge source")
            move_source = Food.add_root(
                space=self.space, name="Private move source", recipe=self.private_recipe,
            )
            move_target = Food.add_root(space=self.space, name="Public move target")
            original_paths = (move_source.path, move_target.path)
            before_count = Food.objects.count()

        denied_actions = (
            (f"/api/food/{merge_source.pk}/merge/{merge_target.pk}/", "private-source"),
            (f"/api/food/{public_source.pk}/merge/{merge_source.pk}/", "private-target"),
            (f"/api/food/{move_source.pk}/move/{move_target.pk}/", "private-move-source"),
            (f"/api/food/{move_target.pk}/move/{move_source.pk}/", "private-move-target"),
        )
        for url, vector in denied_actions:
            with self.subTest(vector=vector):
                response = self.client.put(url, {}, format="json")
                self.assert_status(response, 404)
                self.assertNotIn(self.private_food.name, str(response.data))

        batch_url = "/api/food/batch_update/"
        denied_batches = (
            {"foods": [merge_source.pk], "ignore_shopping": True},
            {"foods": [self.public_food.pk], "substitute_add": [merge_source.pk]},
            {"foods": [self.public_food.pk], "substitute_set": [merge_source.pk]},
            {"foods": [self.public_food.pk], "substitute_remove": [merge_source.pk]},
        )
        for payload in denied_batches:
            with self.subTest(payload=payload):
                response = self.client.put(batch_url, payload, format="json")
                self.assert_status(response, 400)
                self.assertNotIn(merge_source.name, str(response.data))

        with scopes_disabled():
            move_source.refresh_from_db()
            move_target.refresh_from_db()
            merge_source.refresh_from_db()
            self.public_food.refresh_from_db()
            self.assertEqual(Food.objects.count(), before_count)
            self.assertEqual((move_source.path, move_target.path), original_paths)
            self.assertFalse(self.public_food.substitute.filter(pk=merge_source.pk).exists())
            self.assertFalse(merge_source.ignore_shopping)

        self._share()
        shared_batch = self.client.put(
            batch_url,
            {"foods": [self.public_food.pk], "substitute_add": [merge_source.pk]},
            format="json",
        )
        self.assert_status(shared_batch, 200)
        self.assert_status(
            self.client.put(
                f"/api/food/{move_source.pk}/move/{move_target.pk}/", {}, format="json",
            ),
            200,
        )
        self.assert_status(
            self.client.put(
                f"/api/food/{merge_source.pk}/merge/{merge_target.pk}/", {}, format="json",
            ),
            200,
        )
        with scopes_disabled():
            move_source.refresh_from_db()
            self.assertEqual(move_source.get_parent().pk, move_target.pk)
            self.assertTrue(self.public_food.substitute.filter(pk=merge_target.pk).exists())
            self.assertFalse(Food.objects.filter(pk=merge_source.pk).exists())

    def test_food_name_collision_never_returns_an_invisible_private_food(self):
        admin = self._admin_client("collision")
        before = self._food_count()
        for role, client in (("observer", self.client), ("admin", admin)):
            with self.subTest(role=role):
                response = client.post(
                    "/api/food/", {"name": self.private_food.name}, format="json",
                )
                self.assert_status(response, 400)
                self.assertNotIn(self.private_food.name, str(response.data))
                self.assertNotIn(str(self.private_food.pk), str(response.data))
                self.assertEqual(self._food_count(), before)

        owner_collision = self._client(self.owner).post(
            "/api/food/", {"name": self.private_food.name}, format="json",
        )
        self.assert_status(owner_collision, 201)
        self.assertEqual(owner_collision.data["id"], self.private_food.pk)
        public_collision = self.client.post(
            "/api/food/", {"name": self.public_food.name}, format="json",
        )
        self.assert_status(public_collision, 201)
        self.assertEqual(public_collision.data["id"], self.public_food.pk)
        self._share()
        shared_collision = self.client.post(
            "/api/food/", {"name": self.private_food.name}, format="json",
        )
        self.assert_status(shared_collision, 201)
        self.assertEqual(shared_collision.data["id"], self.private_food.pk)
        self.assertEqual(self._food_count(), before)

    def test_food_plural_collision_never_returns_an_invisible_private_food(self):
        with scopes_disabled():
            self.private_food.plural_name = "Private plural collision marker"
            self.private_food.save(update_fields=["plural_name"])
        admin = self._admin_client("plural-collision")
        before = self._food_count()
        payload = {"name": self.private_food.plural_name}
        for role, client in (("observer", self.client), ("admin", admin)):
            with self.subTest(role=role):
                response = client.post("/api/food/", payload, format="json")
                self.assert_status(response, 400)
                self.assertNotIn(self.private_food.name, str(response.data))
                self.assertNotIn(str(self.private_food.pk), str(response.data))
                self.assertEqual(self._food_count(), before)

        owner_collision = self._client(self.owner).post("/api/food/", payload, format="json")
        self.assert_status(owner_collision, 201)
        self.assertEqual(owner_collision.data["id"], self.private_food.pk)
        self._share()
        shared_collision = self.client.post("/api/food/", payload, format="json")
        self.assert_status(shared_collision, 201)
        self.assertEqual(shared_collision.data["id"], self.private_food.pk)
        self.assertEqual(self._food_count(), before)

    def test_food_serialization_filters_hidden_substitutes_and_private_ancestor_subtrees(self):
        admin = self._admin_client("serialization")
        with scopes_disabled():
            self.public_food.substitute.add(self.private_food)
            private_parent = Food.add_root(
                space=self.space,
                name="Private ancestor marker",
                recipe=self.private_recipe,
            )
            private_child = private_parent.add_child(
                space=self.space,
                name="Private descendant marker",
            )

        public_url = f"/api/food/{self.public_food.pk}/"
        child_url = f"/api/food/{private_child.pk}/"
        for role, client in (("observer", self.client), ("admin", admin)):
            with self.subTest(role=role):
                public = client.get(public_url)
                foods = client.get("/api/food/")
                self.assert_status(public, 200)
                self.assert_status(foods, 200)
                self.assertEqual(public.data["substitute"], [])
                rendered = f"{public.data} {foods.data}"
                self.assertNotIn(self.private_food.name, rendered)
                self.assertNotIn(private_parent.name, rendered)
                self.assertNotIn(private_child.name, rendered)
                self.assert_status(client.get(child_url), 404)

        owner = self._client(self.owner)
        owner_public = owner.get(public_url)
        owner_child = owner.get(child_url)
        self.assert_status(owner_public, 200)
        self.assert_status(owner_child, 200)
        self.assertIn(self.private_food.pk, {row["id"] for row in owner_public.data["substitute"]})
        self.assertEqual(
            owner_child.data["full_name"],
            f"{private_parent.name} > {private_child.name}",
        )

        self._share()
        shared_public = self.client.get(public_url)
        shared_child = self.client.get(child_url)
        self.assert_status(shared_public, 200)
        self.assert_status(shared_child, 200)
        self.assertIn(self.private_food.pk, {row["id"] for row in shared_public.data["substitute"]})
        self.assertIn(private_parent.name, shared_child.data["full_name"])

    def test_food_tree_queries_cannot_enumerate_a_private_ancestor_branch(self):
        with scopes_disabled():
            private_parent = Food.add_root(
                space=self.space,
                name="Private queried ancestor marker",
                recipe=self.private_recipe,
            )
            private_child = private_parent.add_child(
                space=self.space,
                name="Private queried descendant marker",
            )

        vectors = (
            f"/api/food/?root={private_parent.pk}",
            f"/api/food/?tree={private_parent.pk}",
            f"/api/food/?root_tree={private_child.pk}",
            f"/api/food/?root={private_parent.pk}&simple=true",
            f"/api/food/?tree={private_parent.pk}&simple=true",
            f"/api/food/?root_tree={private_child.pk}&simple=true",
        )
        for url in vectors:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_status(response, 200)
                self.assertEqual(self._rows(response), [])
                rendered = str(response.data)
                self.assertNotIn(private_parent.name, rendered)
                self.assertNotIn(private_child.name, rendered)

        self._share()
        shared_tree = self.client.get(f"/api/food/?tree={private_parent.pk}&simple=true")
        self.assert_status(shared_tree, 200)
        self.assertEqual(
            {row["id"] for row in self._rows(shared_tree)},
            {private_parent.pk, private_child.pk},
        )

    def test_food_patch_cannot_resolve_or_mutate_a_hidden_substitute(self):
        url = f"/api/food/{self.public_food.pk}/"
        payload = {
            "substitute": [{"id": self.private_food.pk, "name": "Nested mutation marker"}],
        }
        before = self._food_count()
        original_name = self.private_food.name
        denied = self.client.patch(url, payload, format="json")
        self.assert_status(denied, 400)
        self.assertNotIn(original_name, str(denied.data))
        with scopes_disabled():
            self.private_food.refresh_from_db()
            self.public_food.refresh_from_db()
            self.assertEqual(self.private_food.name, original_name)
            self.assertFalse(self.public_food.substitute.filter(pk=self.private_food.pk).exists())
            self.assertEqual(Food.objects.count(), before)

        self._share()
        allowed = self.client.patch(url, payload, format="json")
        self.assert_status(allowed, 200)
        self.assertIn(self.private_food.pk, {row["id"] for row in allowed.data["substitute"]})
        with scopes_disabled():
            self.private_food.refresh_from_db()
            self.public_food.refresh_from_db()
            self.assertEqual(self.private_food.name, original_name)
            self.assertTrue(self.public_food.substitute.filter(pk=self.private_food.pk).exists())
            self.assertEqual(Food.objects.count(), before)

    def test_food_batch_rejects_foreign_category_and_shopping_list_relations(self):
        batch_url = "/api/food/batch_update/"
        with scopes_disabled():
            foreign_category = SupermarketCategory.objects.create(
                space=self.foreign_space, name="Foreign batch category marker",
            )
            local_list = ShoppingList.objects.create(space=self.space, name="Local batch list")
            foreign_list = ShoppingList.objects.create(
                space=self.foreign_space, name="Foreign batch list marker",
            )
            self.public_food.shopping_lists.add(local_list, foreign_list)
            baseline = {
                "category": self.public_food.supermarket_category_id,
                "lists": set(self.public_food.shopping_lists.values_list("pk", flat=True)),
            }

        vectors = (
            {"foods": [self.public_food.pk], "category": foreign_category.pk},
            {"foods": [self.public_food.pk], "shopping_lists_add": [foreign_list.pk]},
            {"foods": [self.public_food.pk], "shopping_lists_remove": [foreign_list.pk]},
            {"foods": [self.public_food.pk], "shopping_lists_set": [foreign_list.pk]},
        )
        for payload in vectors:
            with self.subTest(payload=payload):
                response = self.client.put(batch_url, payload, format="json")
                self.assert_status(response, 400)
                self.assertNotIn(foreign_category.name, str(response.data))
                self.assertNotIn(foreign_list.name, str(response.data))
                with scopes_disabled():
                    self.public_food.refresh_from_db()
                    self.assertEqual(self.public_food.supermarket_category_id, baseline["category"])
                    self.assertEqual(
                        set(self.public_food.shopping_lists.values_list("pk", flat=True)),
                        baseline["lists"],
                    )

    def test_food_merge_rejects_public_target_with_hidden_descendant_even_for_space_owner(self):
        _, target, hidden, source = self._branch_with_hidden_descendant("merge")
        with scopes_disabled():
            baseline = dict(Food.objects.filter(space=self.space).values_list("pk", "path"))
            before = Food.objects.count()
        response = self._client(self.owner).put(
            f"/api/food/{source.pk}/merge/{target.pk}/", {}, format="json",
        )
        self.assert_status(response, 400)
        self.assertNotIn(hidden.name, str(response.data))
        with scopes_disabled():
            self.assertEqual(Food.objects.count(), before)
            self.assertEqual(
                dict(Food.objects.filter(space=self.space).values_list("pk", "path")),
                baseline,
            )

    def test_food_move_rejects_public_parent_with_hidden_descendant_even_for_space_owner(self):
        _, parent, hidden, source = self._branch_with_hidden_descendant("move")
        with scopes_disabled():
            baseline = dict(Food.objects.filter(space=self.space).values_list("pk", "path"))
        response = self._client(self.owner).put(
            f"/api/food/{source.pk}/move/{parent.pk}/", {}, format="json",
        )
        self.assert_status(response, 400)
        self.assertNotIn(hidden.name, str(response.data))
        with scopes_disabled():
            self.assertEqual(
                dict(Food.objects.filter(space=self.space).values_list("pk", "path")),
                baseline,
            )

    def test_food_batch_parent_changes_reject_source_branch_with_hidden_descendant(self):
        _, branch, hidden, target = self._branch_with_hidden_descendant("batch-parent")
        batch_url = "/api/food/batch_update/"
        with scopes_disabled():
            baseline = dict(Food.objects.filter(space=self.space).values_list("pk", "path"))
        vectors = (
            {"foods": [branch.pk], "parent_remove": True},
            {"foods": [branch.pk], "parent_set": target.pk},
        )
        for payload in vectors:
            with self.subTest(payload=payload):
                response = self._client(self.owner).put(batch_url, payload, format="json")
                self.assert_status(response, 400)
                self.assertNotIn(hidden.name, str(response.data))
                with scopes_disabled():
                    self.assertEqual(
                        dict(Food.objects.filter(space=self.space).values_list("pk", "path")),
                        baseline,
                    )

    def test_substitute_onhand_ignores_hidden_food_until_recipe_is_shared(self):
        with scopes_disabled():
            self.public_food.substitute.add(self.private_food)
            self.private_food.onhand_users.add(self.observer)
        url = f"/api/food/{self.public_food.pk}/"
        hidden = self.client.get(url)
        self.assert_status(hidden, 200)
        self.assertFalse(hidden.data["substitute_onhand"])
        self.assertEqual(hidden.data["substitute"], [])

        self._share()
        shared = self.client.get(url)
        self.assert_status(shared, 200)
        self.assertTrue(shared.data["substitute_onhand"])
        self.assertIn(self.private_food.pk, {row["id"] for row in shared.data["substitute"]})

    def test_replenishment_ignores_reference_package_with_foreign_unit(self):
        with scopes_disabled():
            PackageFormat.objects.filter(pk=self.public_package.pk).update(unit=self.foreign_unit)
            self.public_package.refresh_from_db()
            before = self._write_counts()

        response = self.client.post("/api/cuaderno/replenishment/", {}, format="json")
        self.assert_status(response, 200)
        row = next(item for item in response.data["items"] if item["food"] == self.public_food.pk)
        self.assertEqual(row["unit"], self.unit.pk)
        self.assertIsNone(row["package"])
        self.assertIsNone(row["reference_price"])
        self.assertEqual(Decimal(row["usable_stock"]), Decimal("4"))
        self.assertNotIn(self.foreign_unit.name, str(response.data))
        self.assertEqual(self._write_counts(), before)

    def test_guest_and_foreign_relations_fail_closed_without_writes_or_names(self):
        guest = self._client(self.guest)
        guest_vectors = (
            ("get", "/api/cuaderno/packages/", None),
            ("get", f"/api/cuaderno/packages/{self.private_package.pk}/prices/", None),
            ("get", "/api/cuaderno/purchase-offers/", None),
            ("get", "/api/cuaderno/purchase-orders/", None),
            ("get", "/api/cuaderno/stock-minimums/", None),
            ("post", "/api/cuaderno/replenishment/", {}),
            ("get", "/api/cuaderno/movements/", None),
            ("get", "/api/inventory-entry/?empty=true", None),
            ("post", "/api/cuaderno/allergens/", {
                "food": self.private_food.pk, "name": "Guest marker", "state": "unknown",
            }),
        )
        for method, path, data in guest_vectors:
            with self.subTest(role="guest", method=method, path=path):
                expected = (404 if "/prices/" in path else 200) if method == "get" else 403
                response = self._request(guest, method, path, data)
                self.assert_status(response, expected)
                if expected == 200:
                    self.assertNotIn(self.private_food.name, str(response.data))
                    self.assertNotIn(self.foreign_food.name, str(response.data))
        # CustomRecipePermission intentionally lets guests read public recipes,
        # but that must not make a private Food's package visible by direct ID.
        guest_impact = guest.get(
            f"/api/cuaderno/recipes/{self.visible_recipe.pk}/price-impact/"
            f"?package={self.private_package.pk}&servings=4"
        )
        self.assert_status(guest_impact, 404)

        before = self._write_counts()
        foreign_vectors = (
            ("post", "/api/cuaderno/packages/", {
                "food": self.foreign_food.pk, "unit": self.foreign_unit.pk,
                "label": "Foreign denied package", "quantity": "1",
            }),
            ("get", f"/api/cuaderno/packages/{self.corrupt_package.pk}/prices/", None),
            ("post", "/api/cuaderno/purchase-offers/", {
                "package": self.public_package.pk, "supplier": self.foreign_supplier.pk, "amount": "2",
            }),
            ("post", "/api/cuaderno/purchase-orders/", self._order_payload(
                package=self.corrupt_package, supplier=self.supplier,
            )),
            ("put", "/api/cuaderno/stock-minimums/", {
                "food": self.foreign_food.pk, "unit": self.foreign_unit.pk,
                "quantity": "1", "location": None,
            }),
            ("post", "/api/cuaderno/movements/", {
                "entry": self.corrupt_entry.pk, "kind": StockMovement.RECEIPT,
                "quantity": "1", "idempotency_key": "foreign-entry-denied",
            }),
            ("get", f"/api/cuaderno/recipes/{self.visible_recipe.pk}/price-impact/"
                    f"?package={self.corrupt_package.pk}&servings=4", None),
            ("post", "/api/cuaderno/allergens/", {
                "food": self.foreign_food.pk, "name": "Foreign marker", "state": "unknown",
            }),
        )
        for method, path, data in foreign_vectors:
            with self.subTest(scope="foreign", method=method, path=path):
                response = self._request(self.client, method, path, data)
                self.assert_status(response, 404)
                rendered = str(getattr(response, "data", ""))
                self.assertNotIn(self.foreign_food.name, rendered)
                self.assertNotIn(self.foreign_supplier.name, rendered)
        self.assertEqual(self._write_counts(), before)


    def test_guest_safe_reads_filter_private_cross_space_and_revoke_immediately(self):
        with scopes_disabled():
            public_offer = PurchaseOffer.objects.create(
                space=self.space, package=self.public_package, supplier=self.supplier,
                amount=Decimal("7"), valid_from=timezone.now(), created_by=self.owner,
            )
            public_order = PurchaseOrder.objects.create(
                space=self.space, household=self.household, food=self.public_food,
                unit=self.unit, quantity=Decimal("2"), supplier=self.supplier,
                package=self.public_package, package_count=Decimal("2"),
                package_quantity_snapshot=self.public_package.quantity,
                package_unit_snapshot=self.unit, created_by=self.owner,
            )
            public_movement = apply_movement(
                entry_id=self.public_entry.pk, space=self.space, user=self.owner,
                kind=StockMovement.RECEIPT, quantity="1",
                idempotency_key="guest-safe-public-movement",
            )
        guest = self._client(self.guest)

        def read_ids(*, private_visible=False):
            packages = guest.get("/api/cuaderno/packages/")
            public_prices = guest.get(
                f"/api/cuaderno/packages/{self.public_package.pk}/prices/"
            )
            private_prices = guest.get(
                f"/api/cuaderno/packages/{self.private_package.pk}/prices/"
            )
            offers = guest.get("/api/cuaderno/purchase-offers/")
            orders = guest.get("/api/cuaderno/purchase-orders/")
            minimums = guest.get("/api/cuaderno/stock-minimums/")
            movements = guest.get("/api/cuaderno/movements/")
            exchange = guest.get("/api/cuaderno/exchange/")
            for response in (packages, public_prices, offers, orders, minimums, movements, exchange):
                self.assert_status(response, 200)
            self.assert_status(private_prices, 200 if private_visible else 404)
            rendered = " ".join(str(getattr(response, "data", response.content)) for response in (
                packages, offers, orders, minimums, movements,
            )) + str(exchange.content)
            self.assertNotIn(self.foreign_food.name, rendered)
            self.assertNotIn(self.foreign_supplier.name, rendered)
            return {
                "packages": {row["id"] for row in packages.data},
                "offers": {row["id"] for row in offers.data},
                "orders": {row["id"] for row in orders.data},
                "minimums": {row["id"] for row in minimums.data["items"]},
                "movements": {row["id"] for row in movements.data},
                "recipes": {row["name"] for row in exchange.json()["recipes"]},
            }

        hidden = read_ids()
        self.assertEqual(hidden["packages"], {self.public_package.pk})
        self.assertEqual(hidden["offers"], {public_offer.pk})
        self.assertEqual(hidden["orders"], {public_order.pk})
        self.assertEqual(hidden["minimums"], {self.public_minimum.pk})
        self.assertEqual(hidden["movements"], {public_movement.pk})
        self.assertNotIn(self.private_recipe.name, hidden["recipes"])

        with scopes_disabled():
            self.private_recipe.shared.add(self.guest)
        shared = read_ids(private_visible=True)
        self.assertIn(self.private_package.pk, shared["packages"])
        self.assertIn(self.private_offer.pk, shared["offers"])
        self.assertIn(self.private_order.pk, shared["orders"])
        self.assertIn(self.private_minimum.pk, shared["minimums"])
        self.assertIn(self.private_movement.pk, shared["movements"])
        self.assertIn(self.private_recipe.name, shared["recipes"])

        with scopes_disabled():
            self.private_recipe.shared.remove(self.guest)
        revoked = read_ids()
        self.assertEqual(revoked, hidden)

    def test_guest_safe_read_permission_never_opens_unsafe_methods(self):
        guest = self._client(self.guest)
        before = self._write_counts()
        vectors = (
            ("post", "/api/cuaderno/packages/", {}),
            ("post", f"/api/cuaderno/packages/{self.public_package.pk}/prices/", {}),
            ("post", "/api/cuaderno/movements/", {}),
            ("post", "/api/cuaderno/services/", {}),
            ("post", "/api/cuaderno/purchase-offers/", {}),
            ("post", "/api/cuaderno/purchase-orders/", {}),
            ("post", "/api/cuaderno/replenishment/", {}),
            ("put", "/api/cuaderno/stock-minimums/", {}),
            ("post", "/api/cuaderno/allergens/", {}),
            ("post", "/api/cuaderno/exchange/", {}),
        )
        for method, path, data in vectors:
            with self.subTest(method=method, path=path):
                response = self._request(guest, method, path, data)
                self.assert_status(response, 403)
        self.assertEqual(self._write_counts(), before)
