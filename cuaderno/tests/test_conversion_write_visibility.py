"""Write authorization for native food-specific unit conversions."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    Household,
    Recipe,
    SearchFields,
    Space,
    Unit,
    UnitConversion,
    UserSpace,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UnitConversionWriteVisibilityTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.owner = get_user_model().objects.create_user(
                username="conversion-private-owner", password="synthetic-only"
            )
            self.observer = get_user_model().objects.create_user(
                username="conversion-private-observer", password="synthetic-only"
            )
            self.space = Space.objects.create(
                name="Conversion visibility", created_by=self.owner
            )
            user_group = Group.objects.get_or_create(name="user")[0]
            for user, household_name in (
                (self.owner, "Owner kitchen"),
                (self.observer, "Observer kitchen"),
            ):
                household = Household.objects.create(
                    space=self.space, name=household_name
                )
                membership = UserSpace.objects.create(
                    user=user,
                    space=self.space,
                    household=household,
                    active=True,
                )
                membership.groups.add(user_group)

            self.units = [
                Unit.objects.create(
                    space=self.space,
                    name=f"visibility-unit-{index}",
                    base_unit=f"visibility-base-{index}",
                )
                for index in range(12)
            ]
            self.hidden_recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Private conversion recipe",
                servings=1,
                private=True,
            )
            self.hidden_food = Food.add_root(
                space=self.space,
                name="Private conversion food",
                recipe=self.hidden_recipe,
            )
            self.hidden_conversion = self._create_conversion(
                self.units[0], self.units[1], self.hidden_food, self.owner
            )

            self.shared_recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Shared conversion recipe",
                servings=1,
                private=True,
            )
            self.shared_recipe.shared.add(self.observer)
            self.shared_food = Food.add_root(
                space=self.space,
                name="Shared conversion food",
                recipe=self.shared_recipe,
            )
            self.ordinary_food = Food.add_root(
                space=self.space, name="Ordinary conversion food"
            )
            self.visible_conversion = self._create_conversion(
                self.units[2], self.units[3], self.ordinary_food, self.observer
            )

            self.foreign_space = Space.objects.create(
                name="Foreign conversion visibility", created_by=self.owner
            )
            self.foreign_unit = Unit.objects.create(
                space=self.foreign_space,
                name="foreign-visibility-unit",
                base_unit="foreign-visibility-base",
            )
            self.foreign_food = Food.add_root(
                space=self.foreign_space, name="Foreign conversion food"
            )

        self.client = APIClient()
        self.client.force_login(self.observer)

    def _create_conversion(self, base_unit, converted_unit, food, created_by):
        return UnitConversion.objects.create(
            space=self.space,
            created_by=created_by,
            food=food,
            base_amount=Decimal("1"),
            base_unit=base_unit,
            converted_amount=Decimal("2"),
            converted_unit=converted_unit,
        )

    @staticmethod
    def _nested_unit(unit):
        return {"id": unit.pk, "name": unit.name}

    @staticmethod
    def _nested_food(food):
        if food is None:
            return None
        # Deliberately omit recipe: this is the compact payload emitted by
        # existing native selectors and must not bypass recipe visibility.
        return {"id": food.pk, "name": food.name}

    def _payload(self, base_unit, converted_unit, food):
        return {
            "base_amount": "1",
            "base_unit": self._nested_unit(base_unit),
            "converted_amount": "2",
            "converted_unit": self._nested_unit(converted_unit),
            "food": self._nested_food(food),
        }

    def assert_private_rejection(self, response):
        self.assertEqual(response.status_code, 400, getattr(response, "data", response.content))
        self.assertNotIn(self.hidden_recipe.name, str(getattr(response, "data", "")))

    def test_post_cannot_retrieve_an_existing_hidden_conversion(self):
        with scopes_disabled():
            before = UnitConversion.objects.filter(space=self.space).count()
        response = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[0], self.units[1], self.hidden_food),
            format="json",
        )
        self.assert_private_rejection(response)
        with scopes_disabled():
            self.assertEqual(UnitConversion.objects.filter(space=self.space).count(), before)
            self.hidden_conversion.refresh_from_db()
            self.assertEqual(self.hidden_conversion.created_by, self.owner)

    def test_post_cannot_create_a_new_pair_for_hidden_food(self):
        response = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[4], self.units[5], self.hidden_food),
            format="json",
        )
        self.assert_private_rejection(response)
        with scopes_disabled():
            self.assertFalse(
                UnitConversion.objects.filter(
                    space=self.space,
                    food=self.hidden_food,
                    base_unit=self.units[4],
                    converted_unit=self.units[5],
                ).exists()
            )

    def test_patch_cannot_replace_visible_food_with_hidden_food(self):
        before = (
            self.visible_conversion.food_id,
            self.visible_conversion.base_amount,
            self.visible_conversion.converted_amount,
        )
        response = self.client.patch(
            f"/api/unit-conversion/{self.visible_conversion.pk}/",
            {"food": self._nested_food(self.hidden_food)},
            format="json",
        )
        self.assert_private_rejection(response)
        with scopes_disabled():
            self.visible_conversion.refresh_from_db()
            self.assertEqual(
                (
                    self.visible_conversion.food_id,
                    self.visible_conversion.base_amount,
                    self.visible_conversion.converted_amount,
                ),
                before,
            )

    def test_shared_food_is_writable_but_revocation_is_effective_immediately(self):
        allowed = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[4], self.units[5], self.shared_food),
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, getattr(allowed, "data", allowed.content))
        with scopes_disabled():
            self.assertTrue(
                UnitConversion.objects.filter(
                    space=self.space,
                    food=self.shared_food,
                    base_unit=self.units[4],
                    converted_unit=self.units[5],
                ).exists()
            )
            self.shared_recipe.shared.remove(self.observer)

        revoked = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[6], self.units[7], self.shared_food),
            format="json",
        )
        self.assertEqual(revoked.status_code, 400, getattr(revoked, "data", revoked.content))
        self.assertNotIn(self.shared_recipe.name, str(getattr(revoked, "data", "")))
        with scopes_disabled():
            self.assertFalse(
                UnitConversion.objects.filter(
                    space=self.space,
                    food=self.shared_food,
                    base_unit=self.units[6],
                    converted_unit=self.units[7],
                ).exists()
            )

    def test_ordinary_and_global_conversions_remain_writable(self):
        ordinary = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[6], self.units[7], self.ordinary_food),
            format="json",
        )
        self.assertEqual(ordinary.status_code, 201, getattr(ordinary, "data", ordinary.content))
        global_response = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[8], self.units[9], None),
            format="json",
        )
        self.assertEqual(
            global_response.status_code,
            201,
            getattr(global_response, "data", global_response.content),
        )
        with scopes_disabled():
            self.assertTrue(
                UnitConversion.objects.filter(
                    space=self.space,
                    food=self.ordinary_food,
                    base_unit=self.units[6],
                    converted_unit=self.units[7],
                ).exists()
            )
            self.assertTrue(
                UnitConversion.objects.filter(
                    space=self.space,
                    food__isnull=True,
                    base_unit=self.units[8],
                    converted_unit=self.units[9],
                ).exists()
            )

    def test_foreign_food_and_unit_references_are_rejected_without_local_copies(self):
        vectors = (
            self._payload(self.units[8], self.units[9], self.foreign_food),
            self._payload(self.foreign_unit, self.units[10], self.ordinary_food),
        )
        for payload in vectors:
            with self.subTest(payload=payload):
                with scopes_disabled():
                    conversions_before = UnitConversion.objects.filter(space=self.space).count()
                    foods_before = Food.objects.filter(space=self.space).count()
                    units_before = Unit.objects.filter(space=self.space).count()
                response = self.client.post("/api/unit-conversion/", payload, format="json")
                self.assertEqual(
                    response.status_code,
                    400,
                    getattr(response, "data", response.content),
                )
                with scopes_disabled():
                    self.assertEqual(
                        UnitConversion.objects.filter(space=self.space).count(),
                        conversions_before,
                    )
                    self.assertEqual(Food.objects.filter(space=self.space).count(), foods_before)
                    self.assertEqual(Unit.objects.filter(space=self.space).count(), units_before)

    def test_private_owner_can_reuse_their_native_conversion(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[0], self.units[1], self.hidden_food), format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["id"], self.hidden_conversion.pk)

    def test_hidden_name_plural_and_bare_id_do_not_bypass_visibility(self):
        with scopes_disabled():
            self.hidden_food.plural_name = "Private conversion plural"
            self.hidden_food.save(update_fields=["plural_name"])
        for target in (
            {"name": self.hidden_food.name},
            {"name": self.hidden_food.plural_name},
            {"id": self.ordinary_food.pk, "name": self.hidden_food.name},
            self.hidden_food.pk,
        ):
            with self.subTest(target=target), scopes_disabled():
                before = UnitConversion.objects.count()
                payload = self._payload(self.units[4], self.units[5], self.ordinary_food)
                payload["food"] = target
                response = self.client.post("/api/unit-conversion/", payload, format="json")
                self.assert_private_rejection(response)
                self.assertEqual(UnitConversion.objects.count(), before)

    def test_put_cannot_replace_visible_food_with_hidden_food(self):
        payload = self._payload(self.units[2], self.units[3], self.hidden_food)
        response = self.client.put(
            f"/api/unit-conversion/{self.visible_conversion.pk}/", payload, format="json",
        )
        self.assert_private_rejection(response)
        with scopes_disabled():
            self.visible_conversion.refresh_from_db()
            self.assertEqual(self.visible_conversion.food_id, self.ordinary_food.pk)

    def test_foreign_bare_ids_are_validation_errors_not_copies_or_server_errors(self):
        for field, identifier in (("food", self.foreign_food.pk), ("base_unit", self.foreign_unit.pk)):
            with self.subTest(field=field), scopes_disabled():
                before = (Food.objects.count(), Unit.objects.count(), UnitConversion.objects.count())
                payload = self._payload(self.units[4], self.units[5], self.ordinary_food)
                payload[field] = identifier
                response = self.client.post("/api/unit-conversion/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual((Food.objects.count(), Unit.objects.count(), UnitConversion.objects.count()), before)

    def test_null_food_with_parallel_native_global_rows_reuses_the_first_identity(self):
        with scopes_disabled():
            first = self._create_conversion(self.units[8], self.units[9], None, self.owner)
            second = self._create_conversion(self.units[8], self.units[9], None, self.owner)
        response = self.client.post(
            "/api/unit-conversion/", self._payload(self.units[8], self.units[9], None), format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["id"], first.pk)
        with scopes_disabled():
            self.assertEqual(list(UnitConversion.objects.filter(
                food__isnull=True, base_unit=self.units[8], converted_unit=self.units[9],
            ).order_by("pk").values_list("pk", flat=True)), [first.pk, second.pk])

    def test_dedupe_never_returns_a_corrupt_foreign_food_with_the_same_local_name(self):
        marker = "Metadata sintética exclusivamente ajena"
        with scopes_disabled():
            self.foreign_food.name = self.ordinary_food.name
            self.foreign_food.description = marker
            self.foreign_food.save(update_fields=["name", "description"])
            corrupt = self._create_conversion(self.units[4], self.units[5], self.foreign_food, self.owner)
        response = self.client.post(
            "/api/unit-conversion/",
            self._payload(self.units[4], self.units[5], self.ordinary_food), format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotEqual(response.data["id"], corrupt.pk)
        self.assertEqual(response.data["food"]["id"], self.ordinary_food.pk)
        self.assertNotIn(marker, str(response.data))
        with scopes_disabled():
            corrupt.refresh_from_db()
            self.assertEqual(corrupt.food_id, self.foreign_food.pk)
