"""Optimistic concurrency and native audit contract for ingredient-yield editing."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Household, Ingredient, Recipe, SearchFields, Space, Step, Unit, UserSpace
from cuaderno.models import SpaceProfile


REVISION_RE = re.compile(r"^[0-9a-f]{64}$")


class YieldEditFixtureMixin:
    def set_up_yield_fixture(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.space = Space.objects.create(name="Yield conflict space")
            self.household = Household.objects.create(space=self.space, name="Yield conflict household")
            self.owner = self.make_user("yield-conflict-owner", self.space, self.household)
            self.helper = self.make_user("yield-conflict-helper", self.space, self.household)
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)
            self.g = Unit.objects.create(space=self.space, name="g", base_unit="g")
            self.ml = Unit.objects.create(space=self.space, name="ml", base_unit="ml")
            self.food = Food.add_root(space=self.space, name="Conflict potato")
            self.other_food = Food.add_root(space=self.space, name="Conflict onion")
            self.recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Private conflict recipe",
                private=True,
                servings=4,
            )
            self.step = Step.objects.create(space=self.space, instruction="Prepare")
            self.ingredient = Ingredient.objects.create(
                space=self.space,
                food=self.food,
                unit=self.g,
                amount=Decimal("600"),
            )
            self.step.ingredients.add(self.ingredient)
            self.recipe.steps.add(self.step)

            other_space = Space.objects.create(name="Other yield conflict space")
            other_household = Household.objects.create(space=other_space, name="Other household")
            self.outsider = self.make_user("yield-conflict-outsider", other_space, other_household)
            other_space.created_by = self.outsider
            other_space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=other_space, edition=SpaceProfile.PROFESIONAL)

        self.url = f"/api/cuaderno/recipes/{self.recipe.pk}/ingredient-yields/"
        self.client = self.client_for(self.owner)

    @staticmethod
    def make_user(username, space, household):
        user = get_user_model().objects.create_user(username=username, password="synthetic-only")
        membership = UserSpace.objects.create(
            user=user,
            space=space,
            household=household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name="user")[0])
        return user

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_login(user)
        return client

    def get_revision(self):
        response = self.client.get(self.url)
        self.assert_json(response, 200)
        revision = response.data.get("revision")
        self.assertIsInstance(revision, str)
        self.assertRegex(revision, REVISION_RE)
        return revision

    def put_policy(self, revision, *, ratio="0.8", basis="net_usable", client=None):
        return (client or self.client).put(
            self.url,
            {
                "ingredient": self.ingredient.pk,
                "quantity_basis": basis,
                "yield_ratio": ratio,
                "revision": revision,
            },
            format="json",
        )

    def recipe_logs(self):
        content_type = ContentType.objects.get_for_model(Recipe)
        return LogEntry.objects.filter(
            content_type=content_type,
            object_id=str(self.recipe.pk),
            action_flag=CHANGE,
        ).order_by("pk")

    def assert_json(self, response, status):
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(response.get("Content-Type", "").startswith("application/json"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class YieldEditConflictTests(YieldEditFixtureMixin, TestCase):
    def setUp(self):
        self.set_up_yield_fixture()

    def test_revision_tracks_semantic_state_and_native_recipe_changes_without_raw_orm_aba_claim(self):
        revisions = [self.get_revision()]
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(amount=Decimal("601"))
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(unit=self.ml)
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(food=self.other_food)
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(
                quantity_basis="net_usable", yield_ratio=Decimal("0.8"),
            )
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=self.ingredient.pk).update(quantity_basis="gross", yield_ratio=None)
        revisions.append(self.get_revision())
        with scopes_disabled():
            child = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Revision child", servings=1,
            )
            Food.objects.filter(pk=self.other_food.pk).update(recipe=child)
        revisions.append(self.get_revision())
        with scopes_disabled():
            Recipe.objects.filter(pk=self.recipe.pk).update(updated_at=timezone.now() + timedelta(seconds=1))
        revisions.append(self.get_revision())
        LogEntry.objects.create(
            user=self.owner,
            content_type=ContentType.objects.get_for_model(Recipe),
            object_id=str(self.recipe.pk),
            object_repr=str(self.recipe),
            action_flag=CHANGE,
            change_message="Native recipe edit",
        )
        revisions.append(self.get_revision())

        for before, after in zip(revisions, revisions[1:]):
            self.assertNotEqual(before, after)
        self.assertEqual(revisions[3], revisions[5])
        self.assertEqual(len(set(revisions)), len(revisions) - 1)

    def test_revision_envelope_tracks_a_second_line_content_order_and_membership(self):
        revisions = [self.get_revision()]
        with scopes_disabled():
            second = Ingredient.objects.create(
                space=self.space,
                food=self.other_food,
                unit=self.g,
                amount=Decimal("25"),
                order=1,
            )
            self.step.ingredients.add(second)
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=second.pk).update(amount=Decimal("30"))
        revisions.append(self.get_revision())
        with scopes_disabled():
            Ingredient.objects.filter(pk=second.pk).update(order=7)
        revisions.append(self.get_revision())
        with scopes_disabled():
            self.step.ingredients.remove(second)
        revisions.append(self.get_revision())

        for before, after in zip(revisions, revisions[1:]):
            self.assertNotEqual(before, after)
        self.assertEqual(revisions[-1], revisions[0])

    def test_put_requires_a_valid_revision_before_mutating(self):
        payload = {
            "ingredient": self.ingredient.pk,
            "quantity_basis": "net_usable",
            "yield_ratio": "0.8",
        }
        missing = self.client.put(self.url, payload, format="json")
        self.assert_json(missing, 428)
        for invalid in (
            None,
            True,
            1,
            10 ** 63,
            "0" * 63,
            "0" * 65,
            "A" * 64,
            "g" * 64,
            ("0" * 63) + "\n",
            " " + ("0" * 63),
        ):
            with self.subTest(revision=invalid):
                response = self.client.put(self.url, {**payload, "revision": invalid}, format="json")
                self.assert_json(response, 400)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.quantity_basis, "gross")
        self.assertIsNone(self.ingredient.yield_ratio)
        self.assertFalse(self.recipe_logs().exists())

    def test_non_object_json_bodies_are_rejected_without_mutation_or_audit(self):
        self.recipe.refresh_from_db()
        updated_at = self.recipe.updated_at
        for payload in (None, True, 1, [], [{}], "foo"):
            with self.subTest(payload=payload):
                response = self.client.generic(
                    "PUT",
                    self.url,
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assert_json(response, 400)
        self.ingredient.refresh_from_db()
        self.recipe.refresh_from_db()
        self.assertEqual(self.ingredient.quantity_basis, "gross")
        self.assertIsNone(self.ingredient.yield_ratio)
        self.assertEqual(self.recipe.updated_at, updated_at)
        self.assertFalse(self.recipe_logs().exists())

    def test_current_noop_is_idempotent_without_timestamp_or_audit_noise(self):
        revision = self.get_revision()
        self.recipe.refresh_from_db()
        updated_at = self.recipe.updated_at

        response = self.put_policy(revision, basis="gross", ratio=None)

        self.assert_json(response, 200)
        self.assertEqual(response.data["revision"], revision)
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.updated_at, updated_at)
        self.assertFalse(self.recipe_logs().exists())

    def test_stale_revision_fails_and_a_to_b_to_a_never_reuses_a_revision(self):
        revision_a = self.get_revision()
        changed = self.put_policy(revision_a)
        self.assert_json(changed, 200)
        revision_b = changed.data["revision"]
        restored = self.put_policy(revision_b, basis="gross", ratio=None)
        self.assert_json(restored, 200)
        revision_a_again = restored.data["revision"]

        self.assertEqual(len({revision_a, revision_b, revision_a_again}), 3)
        stale = self.put_policy(revision_a, ratio="0.7")
        self.assert_json(stale, 409)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.quantity_basis, "gross")
        self.assertIsNone(self.ingredient.yield_ratio)
        self.assertEqual(self.recipe_logs().count(), 2)

    def test_changed_policy_bumps_recipe_and_writes_native_recipe_audit_trace(self):
        revision = self.get_revision()
        self.recipe.refresh_from_db()
        previous_updated_at = self.recipe.updated_at

        response = self.put_policy(revision)

        self.assert_json(response, 200)
        self.assertRegex(response.data["revision"], REVISION_RE)
        self.assertNotEqual(response.data["revision"], revision)
        self.recipe.refresh_from_db()
        self.assertGreater(self.recipe.updated_at, previous_updated_at)
        log = self.recipe_logs().get()
        self.assertEqual(log.user_id, self.owner.pk)
        trace = json.loads(log.change_message)[0]["changed"]
        self.assertEqual(trace["ingredient_id"], self.ingredient.pk)
        self.assertEqual(trace["before"], {"quantity_basis": "gross", "yield_ratio": None})
        self.assertEqual(trace["after"], {"quantity_basis": "net_usable", "yield_ratio": "0.8"})

    def test_private_and_cross_space_writers_cannot_change_policy_or_audit(self):
        revision = self.get_revision()
        for user in (self.helper, self.outsider):
            with self.subTest(user=user.username):
                response = self.put_policy(revision, client=self.client_for(user))
                self.assert_json(response, 404)
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.quantity_basis, "gross")
        self.assertIsNone(self.ingredient.yield_ratio)
        self.assertFalse(self.recipe_logs().exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class YieldEditRaceTests(YieldEditFixtureMixin, TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        self.set_up_yield_fixture()

    def test_two_writers_with_one_revision_produce_one_change_and_one_conflict(self):
        revision = self.get_revision()
        barrier = Barrier(2)

        def write(ratio):
            close_old_connections()
            try:
                client = self.client_for(self.owner)
                barrier.wait(timeout=30)
                response = self.put_policy(revision, ratio=ratio, client=client)
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(write, ("0.7", "0.8")))

        self.assertEqual(statuses, [200, 409])
        self.ingredient.refresh_from_db()
        self.assertEqual(self.ingredient.quantity_basis, "net_usable")
        self.assertIn(self.ingredient.yield_ratio, {Decimal("0.7"), Decimal("0.8")})
        self.assertEqual(self.recipe_logs().count(), 1)
