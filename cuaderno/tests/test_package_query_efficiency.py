"""Privacy and query-shape contracts for the package list endpoint."""

import json
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Household, Recipe, SearchFields, Space, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion
from cuaderno.services.visibility import visible_packages


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PackageListPrivacyAndQueryTests(TestCase):
    url = "/api/cuaderno/packages/"

    def setUp(self):
        cache.clear()
        if connection.vendor != "postgresql":
            self.fail("La caracterización de consultas exige PostgreSQL real.")
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = get_user_model().objects.create_user(
                username="package-private-owner", password="synthetic-only",
            )
            self.observer = get_user_model().objects.create_user(
                username="package-private-observer", password="synthetic-only",
            )
            self.guest = get_user_model().objects.create_user(
                username="package-private-guest", password="synthetic-only",
            )
            self.foreign_user = get_user_model().objects.create_user(
                username="package-foreign-owner", password="synthetic-only",
            )
            self.space = Space.objects.create(name="Package visibility", created_by=self.owner)
            self.foreign_space = Space.objects.create(
                name="Foreign package visibility", created_by=self.foreign_user,
            )
            user_group = Group.objects.get_or_create(name="user")[0]
            guest_group = Group.objects.get_or_create(name="guest")[0]
            for user, group, household_name in (
                (self.owner, user_group, "Owner kitchen"),
                (self.observer, user_group, "Observer kitchen"),
                (self.guest, guest_group, "Guest kitchen"),
            ):
                household = Household.objects.create(space=self.space, name=household_name)
                membership = UserSpace.objects.create(
                    user=user, space=self.space, household=household, active=True,
                )
                membership.groups.add(group)
            foreign_household = Household.objects.create(
                space=self.foreign_space, name="Foreign kitchen",
            )
            foreign_membership = UserSpace.objects.create(
                user=self.foreign_user,
                space=self.foreign_space,
                household=foreign_household,
                active=True,
            )
            foreign_membership.groups.add(user_group)

            self.unit = Unit.objects.create(
                space=self.space, name="package-local-unit", base_unit="package-local-base",
            )
            self.foreign_unit = Unit.objects.create(
                space=self.foreign_space,
                name="package-foreign-unit",
                base_unit="package-foreign-base",
            )
            self.ordinary_food = Food.add_root(space=self.space, name="Visible package food")
            self.private_recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Private package recipe",
                servings=1,
                private=True,
            )
            self.private_food = Food.add_root(
                space=self.space,
                name="Private package food",
                recipe=self.private_recipe,
            )
            self.foreign_food = Food.add_root(
                space=self.foreign_space, name="Foreign package food",
            )
            self.visible_package = self._package(self.ordinary_food, self.unit, "Visible format")
            self.private_package = self._package(self.private_food, self.unit, "Private format")

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def _package(self, food, unit, label):
        return PackageFormat.objects.create(
            space=self.space,
            food=food,
            unit=unit,
            label=label,
            quantity=Decimal("1"),
            is_reference=False,
        )

    def _price(self, package, amount, valid_from, *, space=None):
        return PriceVersion.objects.create(
            space=space or self.space,
            package=package,
            amount=Decimal(amount),
            explicit_free=False,
            valid_from=valid_from,
            created_by=self.owner,
        )

    @staticmethod
    def _ids(response):
        return {row["id"] for row in response.data}

    @staticmethod
    def _root_selects(captured, table):
        marker = f'"{table}"'
        selected = []
        # Correlated projections may contain FROM before the outer query's FROM.
        # Recognize SQL nesting and quoted literals instead of the first substring.
        tokens = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[()]|\bFROM\b", re.IGNORECASE)
        for query in captured.captured_queries:
            sql, depth = query['sql'], 0
            for token in tokens.finditer(sql):
                value = token.group()
                if value == '(':
                    depth += 1
                elif value == ')':
                    depth -= 1
                elif value.upper() == 'FROM' and depth == 0:
                    if sql[token.end():].lstrip().startswith(marker):
                        selected.append(sql)
                    break
        return selected

    def test_private_recipe_package_is_owner_only_and_guest_read_is_filtered(self):
        observer_response = self.client_for(self.observer).get(self.url)
        self.assertEqual(observer_response.status_code, 200, observer_response.content)
        self.assertEqual(self._ids(observer_response), {self.visible_package.pk})
        self.assertNotIn(self.private_food.name, str(observer_response.data))
        self.assertNotIn(self.private_recipe.name, str(observer_response.data))

        owner_response = self.client_for(self.owner).get(self.url)
        self.assertEqual(owner_response.status_code, 200, owner_response.content)
        self.assertEqual(
            self._ids(owner_response),
            {self.visible_package.pk, self.private_package.pk},
        )

        guest_response = self.client_for(self.guest).get(self.url)
        self.assertEqual(guest_response.status_code, 200, guest_response.content)
        self.assertEqual(self._ids(guest_response), {self.visible_package.pk})
        self.assertNotIn(self.private_food.name, str(getattr(guest_response, "data", "")))

    def test_share_grants_visibility_and_revocation_is_effective_immediately(self):
        client = self.client_for(self.observer)
        with scopes_disabled():
            self.private_recipe.shared.add(self.observer)
        shared = client.get(self.url)
        self.assertEqual(shared.status_code, 200, shared.content)
        self.assertIn(self.private_package.pk, self._ids(shared))

        with scopes_disabled():
            self.private_recipe.shared.remove(self.observer)
        revoked = client.get(self.url)
        self.assertEqual(revoked.status_code, 200, revoked.content)
        self.assertEqual(self._ids(revoked), {self.visible_package.pk})
        self.assertNotIn(self.private_food.name, str(revoked.data))

    def test_package_policy_is_direct_single_sql_and_keeps_private_ancestor_acl(self):
        with scopes_disabled():
            child = self.private_food.add_child(space=self.space, name="Private ancestor child")
            child_package = self._package(child, self.unit, "Private descendant format")
            foreign_recipe = Recipe.objects.create(
                space=self.foreign_space, name="Foreign recipe", servings=1, created_by=self.foreign_user,
            )
            corrupt_food = Food.add_root(space=self.space, name="Corrupt recipe link")
            Food._base_manager.filter(pk=corrupt_food.pk).update(recipe=foreign_recipe)
            corrupt_package = self._package(corrupt_food, self.unit, "Foreign recipe format")

        def identifiers():
            with scopes_disabled(), CaptureQueriesContext(connection) as lazy:
                packages = visible_packages(self.observer, self.space)
            self.assertEqual(len(lazy), 0)
            with scopes_disabled(), CaptureQueriesContext(connection) as captured:
                result = set(packages.values_list("pk", flat=True))
            self.assertEqual(len(captured), 1)
            self.assertNotRegex(captured[0]["sql"], r'food_id"\s+IN\s*\(')
            return result

        self.assertEqual(identifiers(), {self.visible_package.pk})
        with scopes_disabled():
            self.private_recipe.shared.add(self.observer)
        self.assertEqual(identifiers(), {self.visible_package.pk, self.private_package.pk, child_package.pk})
        self.assertNotIn(corrupt_package.pk, identifiers())
        with scopes_disabled():
            self.private_recipe.shared.remove(self.observer)
        self.assertEqual(identifiers(), {self.visible_package.pk})

    def test_latest_price_is_deterministic_and_corrupt_cross_space_rows_are_hidden(self):
        past = timezone.now() - timedelta(days=1)
        first = self._price(self.visible_package, "10", past)
        latest = self._price(self.visible_package, "11", past)
        future = self._price(
            self.visible_package, "99", timezone.now() + timedelta(days=1),
        )
        foreign_price = self._price(
            self.visible_package, "777", past + timedelta(hours=1), space=self.foreign_space,
        )
        corrupt_package = self._package(
            self.foreign_food, self.foreign_unit, "Corrupt foreign relations",
        )

        response = self.client_for(self.observer).get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._ids(response), {self.visible_package.pk})
        row = response.data[0]
        self.assertEqual(row["current_price"]["id"], latest.pk)
        self.assertEqual(row["current_price"]["amount"], "11.0000000000000000")
        self.assertNotIn(first.pk, {row["current_price"]["id"]})
        self.assertNotIn(future.pk, {row["current_price"]["id"]})
        self.assertNotIn(foreign_price.pk, {row["current_price"]["id"]})
        self.assertNotIn(corrupt_package.pk, self._ids(response))
        self.assertNotIn(self.foreign_food.name, str(response.data))
        self.assertNotIn(self.foreign_unit.name, str(response.data))

    def test_package_and_price_queries_are_constant_and_prices_use_a_database_relation(self):
        with scopes_disabled():
            self.private_package.delete()
            self.visible_package.delete()
            foods = [
                Food.add_root(space=self.space, name=f"Query package food {index:02d}")
                for index in range(50)
            ]
            packages = PackageFormat.objects.bulk_create([
                PackageFormat(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    label=f"Query format {index:02d}",
                    quantity=Decimal("5"),
                    is_reference=True,
                )
                for index, food in enumerate(foods)
            ])
            now = timezone.now() - timedelta(minutes=1)
            PriceVersion.objects.bulk_create([
                PriceVersion(
                    space=self.space,
                    package=package,
                    amount=Decimal(index + 1),
                    explicit_free=False,
                    valid_from=now,
                    created_by=self.owner,
                )
                for index, package in enumerate(packages)
            ])

        client = self.client_for(self.observer)
        with scopes_disabled():
            PackageFormat.objects.filter(pk__in=[row.pk for row in packages[10:]]).update(
                space=self.foreign_space,
            )
        with CaptureQueriesContext(connection) as ten_queries:
            ten = client.get(self.url)
        self.assertEqual(ten.status_code, 200, ten.content)
        self.assertEqual(len(ten.data), 10)

        with scopes_disabled():
            PackageFormat.objects.filter(pk__in=[row.pk for row in packages[10:]]).update(
                space=self.space,
            )
        with CaptureQueriesContext(connection) as fifty_queries:
            fifty = client.get(self.url)
        self.assertEqual(fifty.status_code, 200, fifty.content)
        self.assertEqual(len(fifty.data), 50)
        self.assertEqual(
            [(row["id"], row["current_price"]["id"]) for row in ten.data],
            [(row["id"], row["current_price"]["id"]) for row in fifty.data[:10]],
        )
        self.assertEqual(len(ten_queries), len(fifty_queries))

        for captured in (ten_queries, fifty_queries):
            package_selects = [
                query["sql"] for query in captured.captured_queries
                if '"cuaderno_packageformat"' in query["sql"]
            ]
            self.assertEqual(len(package_selects), 1)
            sql = package_selects[0]
            normalized = sql.upper()
            self.assertIn("LATEST_PRICES AS MATERIALIZED", normalized)
            self.assertIn("DISTINCT ON", normalized)
            self.assertIn("ROW_TO_JSON(", normalized)
            self.assertIn("JSON_AGG(", normalized)
            self.assertLessEqual(len(captured), 5)
            self.assertIn('"cuaderno_priceversion"', sql)
            self.assertRegex(sql, r'latest_price\.package_id\s*=\s*package\.id')
            self.assertNotRegex(sql, r'WHERE\s+price\.package_id\s*=\s*package\.id')

    def test_empty_package_list_is_a_json_array_and_exposes_lazy_data(self):
        with scopes_disabled():
            PackageFormat.objects.filter(space=self.space).delete()

        response = self.client_for(self.observer).get(self.url)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.content, b"[]")
        self.assertEqual(response.data, [])

    def test_package_json_keeps_pk_order_null_price_and_exact_timestamp_shape(self):
        exact_time = timezone.now().replace(microsecond=123456) - timedelta(minutes=1)
        with scopes_disabled():
            self.ordinary_food.name = "Aceite ñandú"
            self.ordinary_food.save(update_fields=["name"])
            self.visible_package.label = "Botella única"
            self.visible_package.save(update_fields=["label"])
            priced = self._price(self.visible_package, "12.34", exact_time)
            unpriced_food = Food.add_root(space=self.space, name="Sin precio")
            unpriced = self._package(unpriced_food, self.unit, "Formato sin precio")
            priced.refresh_from_db()
            self.visible_package.refresh_from_db()

        response = self.client_for(self.observer).get(self.url)

        self.assertEqual(response.status_code, 200, response.content)
        decoded = json.loads(response.content)
        self.assertEqual(decoded, response.data)
        self.assertEqual(
            [row["id"] for row in decoded],
            sorted([self.visible_package.pk, unpriced.pk]),
        )
        self.assertTrue(all(set(row) == {
            "id", "food", "food_name", "unit", "unit_name", "label",
            "quantity", "is_reference", "current_price",
        } for row in decoded))
        by_id = {row["id"]: row for row in decoded}
        current = by_id[self.visible_package.pk]["current_price"]
        self.assertEqual(current, {
            "id": priced.pk,
            "amount": format(priced.amount, "f"),
            "explicit_free": False,
            "valid_from": priced.valid_from.isoformat(),
        })
        self.assertIs(current["explicit_free"], False)
        self.assertEqual(by_id[self.visible_package.pk]["food_name"], "Aceite ñandú")
        self.assertEqual(by_id[self.visible_package.pk]["label"], "Botella única")
        self.assertIsNone(by_id[unpriced.pk]["current_price"])
