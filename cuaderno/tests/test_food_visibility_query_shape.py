"""SQL shape and privacy contracts for native Food visibility."""

import json
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django_scopes import scopes_disabled

from cookbook.models import Food, Household, Recipe, SearchFields, Space, UserSpace
from cuaderno.services.visibility import visible_foods


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FoodVisibilityQueryShapeTests(TestCase):
    PLAIN_FOOD_COUNT = 1500
    TREE_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    @classmethod
    def _root_path(cls, ordinal):
        value = ordinal
        digits = []
        while value:
            value, remainder = divmod(value, len(cls.TREE_ALPHABET))
            digits.append(cls.TREE_ALPHABET[remainder])
        return "".join(reversed(digits or ["0"])).rjust(4, "0")

    @staticmethod
    def _user(username, space, household):
        user = get_user_model().objects.create_user(
            username=username, password="synthetic-only",
        )
        membership = UserSpace.objects.create(
            user=user, space=space, household=household, active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name="user")[0])
        return user

    def setUp(self):
        if connection.vendor != "postgresql":
            self.fail("La forma SQL de visibilidad exige PostgreSQL real.")
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            bootstrap = get_user_model().objects.create_user(
                username="food-shape-bootstrap", password="synthetic-only",
            )
            self.space = Space.objects.create(name="Food query shape", created_by=bootstrap)
            self.household = Household.objects.create(space=self.space, name="Food query kitchen")
            self.owner = self._user("food-shape-owner", self.space, self.household)
            self.observer = self._user("food-shape-observer", self.space, self.household)
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])

            self.foreign_space = Space.objects.create(
                name="Foreign food query shape", created_by=bootstrap,
            )
            foreign_household = Household.objects.create(
                space=self.foreign_space, name="Foreign query kitchen",
            )
            self.foreign_owner = self._user(
                "food-shape-foreign", self.foreign_space, foreign_household,
            )
            self.foreign_space.created_by = self.foreign_owner
            self.foreign_space.save(update_fields=["created_by"])

            self.public_recipe = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Public food shape", servings=1,
            )
            self.private_recipe = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Private food shape",
                servings=1, private=True,
            )
            self.denied_recipe = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Denied food shape",
                servings=1, private=True,
            )
            self.foreign_recipe = Recipe.objects.create(
                space=self.foreign_space, created_by=self.foreign_owner,
                name="Foreign food shape", servings=1,
            )

            self.ordinary = Food.add_root(space=self.space, name="Ordinary visible food")
            self.public_linked = Food.add_root(
                space=self.space, name="Public linked food", recipe=self.public_recipe,
            )
            self.private_parent = Food.add_root(
                space=self.space, name="Private linked parent", recipe=self.private_recipe,
            )
            self.private_child = self.private_parent.add_child(
                space=self.space, name="Private child",
            )
            self.private_sibling = self.private_parent.add_child(
                space=self.space, name="Private sibling",
            )
            self.denied_linked = Food.add_root(
                space=self.space, name="Denied linked food", recipe=self.denied_recipe,
            )
            self.foreign_recipe_link = Food.add_root(
                space=self.space, name="Foreign recipe FK",
            )
            # Characterize a legacy/corrupt cross-Space FK without asking the
            # current write guard to create an invalid relation.
            Food._base_manager.filter(pk=self.foreign_recipe_link.pk).update(
                recipe_id=self.foreign_recipe.pk,
            )
            self.foreign_recipe_link.recipe_id = self.foreign_recipe.pk

            self.plain_space = Space.objects.create(
                name="Food query shape no recipes", created_by=self.owner,
            )
            Food.objects.bulk_create([
                Food(
                    space=self.plain_space,
                    name=f"Plain root {index:04d}",
                    # Treebeard paths are globally unique, not partitioned by
                    # Space. Reserve a distant deterministic root interval
                    # from the handful of roots created above.
                    path=self._root_path(index + 10000),
                    depth=1,
                    numchild=0,
                )
                for index in range(self.PLAIN_FOOD_COUNT)
            ])

    @staticmethod
    def _plan_nodes(plan):
        yield plan
        for child in plan.get("Plans", []):
            yield from FoodVisibilityQueryShapeTests._plan_nodes(child)

    def _evaluated_ids(self, queryset):
        with CaptureQueriesContext(connection) as captured:
            identifiers = list(queryset.order_by("pk").values_list("pk", flat=True))
        self.assertEqual(len(captured), 1, [query["sql"] for query in captured.captured_queries])
        return identifiers

    def _visible_ids(self, user, *, recipes=None):
        with scopes_disabled(), CaptureQueriesContext(connection) as lazy_queries:
            queryset = visible_foods(user, self.space, recipes=recipes)
        self.assertEqual(len(lazy_queries), 0, lazy_queries.captured_queries)
        with scopes_disabled():
            return set(self._evaluated_ids(queryset))

    def test_no_linked_food_fastpath_is_one_query_and_skips_correlated_ancestry(self):
        with scopes_disabled(), CaptureQueriesContext(connection) as lazy_queries:
            queryset = visible_foods(self.owner, self.plain_space)
        self.assertEqual(len(lazy_queries), 0, lazy_queries.captured_queries)

        with scopes_disabled(), CaptureQueriesContext(connection) as evaluated:
            identifiers = list(queryset.values_list("pk", flat=True))
        self.assertEqual(len(evaluated), 1, [query["sql"] for query in evaluated.captured_queries])
        self.assertEqual(len(identifiers), self.PLAIN_FOOD_COUNT)
        sql = " ".join(evaluated[0]["sql"].upper().split())
        self.assertRegex(
            sql,
            re.compile(r"NOT EXISTS\s*\(.+RECIPE_ID.+IS NOT NULL.+\)\s+OR\s+NOT EXISTS\s*\(", re.DOTALL),
        )

        with scopes_disabled():
            explained = json.loads(queryset.explain(analyze=True, buffers=True, format="json"))
        self.assertIsInstance(explained, list)
        self.assertEqual(len(explained), 1)
        nodes = list(self._plan_nodes(explained[0]["Plan"]))
        init_plans = [node for node in nodes if node.get("Parent Relationship") == "InitPlan"]
        correlated = [node for node in nodes if node.get("Parent Relationship") == "SubPlan"]
        self.assertTrue(init_plans, explained)
        self.assertTrue(correlated, explained)
        self.assertTrue(all(node.get("Actual Loops") == 1 for node in init_plans), init_plans)
        self.assertTrue(all(node.get("Actual Loops") == 0 for node in correlated), correlated)

    def test_acl_tree_sharing_revocation_foreign_fk_and_explicit_policy_remain_single_sql(self):
        expected_public = {self.ordinary.pk, self.public_linked.pk}
        self.assertEqual(self._visible_ids(self.observer), expected_public)
        self.assertNotIn(self.foreign_recipe_link.pk, self._visible_ids(self.observer))

        with scopes_disabled():
            self.private_recipe.shared.add(self.observer)
        expected_shared = expected_public | {
            self.private_parent.pk, self.private_child.pk, self.private_sibling.pk,
        }
        self.assertEqual(self._visible_ids(self.observer), expected_shared)

        with scopes_disabled():
            self.private_recipe.shared.remove(self.observer)
        self.assertEqual(self._visible_ids(self.observer), expected_public)

        with scopes_disabled():
            explicit = Recipe.objects.filter(pk=self.private_recipe.pk)
        self.assertEqual(
            self._visible_ids(self.observer, recipes=explicit),
            {
                self.ordinary.pk,
                self.private_parent.pk,
                self.private_child.pk,
                self.private_sibling.pk,
            },
        )
