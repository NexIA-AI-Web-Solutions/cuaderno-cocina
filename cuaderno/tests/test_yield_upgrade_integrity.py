"""Regression contracts for yield-policy upgrades on native Food relations."""

import hashlib
import json
from decimal import Decimal
from threading import Barrier, Lock, Thread

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory

from cookbook.models import Food, Household, Ingredient, Recipe, SearchFields, Space, Step, Unit, UserSpace
from cookbook.serializer import IngredientExportSerializer, IngredientSerializer, IngredientSimpleSerializer
from cuaderno.domain.errors import DomainError
from cuaderno.models import RecipeExchangeRecord, SpaceProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class YieldUpgradeIntegrityTests(TestCase):
    LEGACY_SHA256 = "448cd7a1427350d4950f45067de97d121b3eb4ba476ce9a61792cb56971666a6"
    LEGACY_DOCUMENT = {
        "source": "legacy",
        "recipes": [
            {
                "external_id": "r-1",
                "name": "Sopa",
                "servings": "2",
                "ingredients": [{"food": "Patata", "quantity": "1", "unit": "kg"}],
            }
        ],
    }
    # This is the exact normalized payload hashed before yield policy fields were
    # added. It is deliberately independent from the production normalizer.
    LEGACY_NORMALIZED_ITEM = {
        "source": "legacy",
        "external_id": "r-1",
        "name": "Sopa",
        "description": "",
        "private": False,
        "servings": "2",
        "ingredients": [
            {
                "food": "Patata",
                "quantity": "1",
                "unit": "kg",
                "food_id": None,
                "unit_id": None,
                "note": None,
                "original_text": None,
                "is_header": False,
                "no_amount": False,
            }
        ],
        "steps": [
            {
                "name": "",
                "instruction": "",
                "step_recipe": None,
                "ingredients": [
                    {
                        "food": "Patata",
                        "food_id": None,
                        "quantity": "1",
                        "unit": "kg",
                        "unit_id": None,
                        "note": None,
                        "original_text": None,
                        "is_header": False,
                        "no_amount": False,
                        "food_ref": None,
                        "unit_ref": None,
                    }
                ],
            }
        ],
        "yield": None,
        "mapping": {},
        "catalog": None,
    }

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.space = Space.objects.create(name="Synthetic yield-upgrade integrity")
            self.household = Household.objects.create(space=self.space, name="Synthetic kitchen")
            self.owner = self._make_user("yield-upgrade-owner")
            self.other_user = self._make_user("yield-upgrade-other")
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)
            self.kg = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.child = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Synthetic child recipe",
                private=True,
                servings=1,
            )
        self.client = APIClient()
        self.client.force_login(self.owner)

    def _make_user(self, username):
        user = get_user_model().objects.create_user(username=username, password="synthetic-only")
        membership = UserSpace.objects.create(
            user=user,
            space=self.space,
            household=self.household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name="user")[0])
        return user

    def _food_used_by_ingredient(self, name, *, active=True):
        food = Food.add_root(space=self.space, name=name)
        recipe = Recipe.objects.create(
            space=self.space,
            created_by=self.owner,
            name=f"Recipe using {name}",
            private=True,
            servings=1,
        )
        step = Step.objects.create(space=self.space, instruction="Synthetic preparation")
        ingredient = Ingredient.objects.create(
            space=self.space,
            food=food,
            unit=self.kg,
            amount=Decimal("1"),
            quantity_basis="net_usable" if active else "gross",
            yield_ratio=Decimal("0.8") if active else None,
        )
        step.ingredients.add(ingredient)
        recipe.steps.add(step)
        return food, ingredient

    def _assert_relation_preserved(self, food_id, ingredient_id):
        with scopes_disabled():
            food = Food.objects.get(pk=food_id)
            ingredient = Ingredient.objects.get(pk=ingredient_id)
            self.assertIsNone(food.recipe_id)
            self.assertEqual(ingredient.food_id, food_id)
            self.assertEqual(ingredient.quantity_basis, "net_usable")
            self.assertEqual(ingredient.yield_ratio, Decimal("0.8"))

    def test_food_patch_rejects_subrecipe_link_when_an_active_yield_policy_exists(self):
        with scopes_disabled():
            food, ingredient = self._food_used_by_ingredient("Active-yield source")

        response = self.client.patch(
            f"/api/food/{food.pk}/",
            {"recipe": {"id": self.child.pk, "name": self.child.name}},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self._assert_relation_preserved(food.pk, ingredient.pk)

    def test_food_patch_allows_subrecipe_link_without_an_active_yield_policy(self):
        with scopes_disabled():
            food, ingredient = self._food_used_by_ingredient("Gross source", active=False)

        response = self.client.patch(
            f"/api/food/{food.pk}/",
            {"recipe": {"id": self.child.pk, "name": self.child.name}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        with scopes_disabled():
            food.refresh_from_db()
            ingredient.refresh_from_db()
            self.assertEqual(food.recipe_id, self.child.pk)
            self.assertEqual(ingredient.food_id, food.pk)
            self.assertEqual(ingredient.quantity_basis, "gross")
            self.assertIsNone(ingredient.yield_ratio)

    def test_food_patch_cannot_link_another_users_private_recipe_or_disclose_it(self):
        private_name = "Private child must not leak 7f927"
        with scopes_disabled():
            private_child = Recipe.objects.create(
                space=self.space,
                created_by=self.other_user,
                name=private_name,
                private=True,
                servings=1,
            )
            food = Food.add_root(space=self.space, name="Privacy source")

        response = self.client.patch(
            f"/api/food/{food.pk}/",
            {"recipe": {"id": private_child.pk, "name": private_child.name}},
            format="json",
        )

        self.assertIn(response.status_code, (400, 404), response.content)
        self.assertNotIn(private_name, response.content.decode(errors="replace"))
        with scopes_disabled():
            food.refresh_from_db()
            self.assertIsNone(food.recipe_id)

    def test_native_ingredient_serializers_recheck_food_when_validation_becomes_stale(self):
        for serializer_class in (IngredientSimpleSerializer, IngredientSerializer, IngredientExportSerializer):
            with self.subTest(serializer=serializer_class.__name__), scopes_disabled():
                food, ingredient = self._food_used_by_ingredient(
                    f"Stale validation {serializer_class.__name__}", active=False
                )
                request = APIRequestFactory().patch("/api/ingredient/")
                request.space = self.space
                request.user = self.owner
                serializer = serializer_class(
                    ingredient,
                    data={"quantity_basis": "net_usable", "yield_ratio": "0.8"},
                    partial=True,
                    context={"request": request},
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)

                # The Food changes after serializer validation, just before the
                # write. Persistence must validate fresh state, not cached attrs.
                food.recipe = self.child
                food.save(update_fields=["recipe"])
                with self.assertRaises(serializers.ValidationError):
                    serializer.save()

                ingredient.refresh_from_db()
                self.assertEqual(ingredient.quantity_basis, "gross")
                self.assertIsNone(ingredient.yield_ratio)
                self.assertEqual(ingredient.food.recipe_id, self.child.pk)

    def test_food_merge_endpoint_rejects_target_subrecipe_for_active_yield_source(self):
        with scopes_disabled():
            source, ingredient = self._food_used_by_ingredient("Merge endpoint source")
            target = Food.add_root(space=self.space, name="Merge endpoint target", recipe=self.child)

        response = self.client.put(f"/api/food/{source.pk}/merge/{target.pk}/", {}, format="json")

        self.assertIn(response.status_code, (400, 409), response.content)
        self._assert_relation_preserved(source.pk, ingredient.pk)
        with scopes_disabled():
            self.assertTrue(Food.objects.filter(pk=target.pk, recipe=self.child).exists())

    def test_food_model_merge_rejects_target_subrecipe_for_active_yield_source(self):
        with scopes_disabled():
            source, ingredient = self._food_used_by_ingredient("Model merge source")
            target = Food.add_root(space=self.space, name="Model merge target", recipe=self.child)
            with self.assertRaises(DomainError):
                source.merge_into(target)

        self._assert_relation_preserved(source.pk, ingredient.pk)
        with scopes_disabled():
            self.assertTrue(Food.objects.filter(pk=target.pk, recipe=self.child).exists())

    def test_legacy_exchange_digest_replays_but_active_yield_change_conflicts(self):
        canonical = json.dumps(
            self.LEGACY_NORMALIZED_ITEM,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), self.LEGACY_SHA256)

        with scopes_disabled():
            imported = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Sopa",
                private=False,
                servings=2,
            )
            RecipeExchangeRecord.objects.create(
                space=self.space,
                source="legacy",
                external_id="r-1",
                payload_sha256=self.LEGACY_SHA256,
                recipe=imported,
                created_by=self.owner,
            )

        replay = self.client.post("/api/cuaderno/exchange/", self.LEGACY_DOCUMENT, format="json")
        self.assertIn(replay.status_code, (200, 201), replay.content)
        self.assertIn(imported.pk, replay.json()["replayed"])
        with scopes_disabled():
            self.assertEqual(RecipeExchangeRecord.objects.count(), 1)
            self.assertEqual(Recipe.objects.filter(space=self.space).count(), 2)

        changed = json.loads(json.dumps(self.LEGACY_DOCUMENT))
        changed["recipes"][0]["ingredients"][0].update(
            {"quantity_basis": "net_usable", "yield_ratio": "0.8"}
        )
        conflict = self.client.post("/api/cuaderno/exchange/", changed, format="json")
        self.assertEqual(conflict.status_code, 409, conflict.content)
        with scopes_disabled():
            self.assertEqual(RecipeExchangeRecord.objects.count(), 1)
            self.assertEqual(Recipe.objects.filter(space=self.space).count(), 2)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class YieldUpgradeConcurrencyTests(TransactionTestCase):
    """The two individually valid native PATCHes must not create a double policy."""

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.space = Space.objects.create(name="Synthetic yield-upgrade race")
            self.household = Household.objects.create(space=self.space, name="Synthetic race kitchen")
            self.owner = get_user_model().objects.create_user(
                username="yield-upgrade-race-owner", password="synthetic-only"
            )
            membership = UserSpace.objects.create(
                user=self.owner,
                space=self.space,
                household=self.household,
                active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)
            unit = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.child = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Race child recipe",
                private=True,
                servings=1,
            )
            parent = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Race parent recipe",
                private=True,
                servings=1,
            )
            step = Step.objects.create(space=self.space, instruction="Race preparation")
            self.food = Food.add_root(space=self.space, name="Race source food")
            self.ingredient = Ingredient.objects.create(
                space=self.space,
                food=self.food,
                unit=unit,
                amount=Decimal("1"),
                quantity_basis="gross",
                yield_ratio=None,
            )
            step.ingredients.add(self.ingredient)
            parent.steps.add(step)

    def test_food_recipe_and_ingredient_yield_patches_serialize_to_one_valid_winner(self):
        barrier = Barrier(2)
        result_lock = Lock()
        results = []

        def patch_food():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.owner.pk)
                client = APIClient()
                client.force_login(user)
                barrier.wait(timeout=10)
                response = client.patch(
                    f"/api/food/{self.food.pk}/",
                    {"recipe": {"id": self.child.pk, "name": self.child.name}},
                    format="json",
                )
                result = ("food", response.status_code)
            except Exception as exc:  # Captured so thread failures remain assertions.
                result = ("food-error", type(exc).__name__)
            finally:
                connections.close_all()
            with result_lock:
                results.append(result)

        def patch_ingredient():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.owner.pk)
                client = APIClient()
                client.force_login(user)
                barrier.wait(timeout=10)
                response = client.patch(
                    f"/api/ingredient/{self.ingredient.pk}/",
                    {"quantity_basis": "net_usable", "yield_ratio": "0.8"},
                    format="json",
                )
                result = ("ingredient", response.status_code)
            except Exception as exc:  # Captured so thread failures remain assertions.
                result = ("ingredient-error", type(exc).__name__)
            finally:
                connections.close_all()
            with result_lock:
                results.append(result)

        threads = [Thread(target=patch_food), Thread(target=patch_ingredient)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads), "La carrera no terminó; posible deadlock")
        statuses = [status for _, status in results]
        self.assertEqual(sum(type(status) is int and 200 <= status < 300 for status in statuses), 1, results)
        self.assertEqual(sum(status in (400, 409) for status in statuses), 1, results)

        with scopes_disabled():
            food = Food.objects.get(pk=self.food.pk)
            ingredient = Ingredient.objects.get(pk=self.ingredient.pk)
            valid_food_winner = (
                food.recipe_id == self.child.pk
                and ingredient.quantity_basis == "gross"
                and ingredient.yield_ratio is None
            )
            valid_yield_winner = (
                food.recipe_id is None
                and ingredient.quantity_basis == "net_usable"
                and ingredient.yield_ratio == Decimal("0.8")
            )
            self.assertTrue(valid_food_winner or valid_yield_winner, results)
