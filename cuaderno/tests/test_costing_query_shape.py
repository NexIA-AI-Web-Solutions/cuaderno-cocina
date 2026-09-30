"""Query-shape contracts for recipe ACL and direct native costing."""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, Household, Ingredient, Recipe, Space, Step, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion
from cuaderno.services.costing import cost_recipe, visible_recipes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CostingQueryShapeTests(TestCase):
    INGREDIENT_COUNT = 15

    def make_user(self, username, space, household, group="user"):
        user = get_user_model().objects.create_user(username=username, password="synthetic-only")
        membership = UserSpace.objects.create(
            user=user,
            space=space,
            household=household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name=group)[0])
        return user

    def setUp(self):
        with scopes_disabled():
            self.space = Space.objects.create(name="Forma SQL escandallos")
            self.household = Household.objects.create(space=self.space, name="Cocina SQL")
            self.owner = self.make_user("query-shape-owner", self.space, self.household)
            self.other = self.make_user("query-shape-other", self.space, self.household)
            self.admin = self.make_user("query-shape-admin", self.space, self.household, "admin")
            self.space.created_by = self.admin
            self.space.save(update_fields=["created_by"])

            self.foreign_space = Space.objects.create(name="Espacio SQL ajeno")
            foreign_household = Household.objects.create(space=self.foreign_space, name="Cocina ajena")
            self.foreign_user = self.make_user(
                "query-shape-foreign", self.foreign_space, foreign_household,
            )
            self.foreign_space.created_by = self.foreign_user
            self.foreign_space.save(update_fields=["created_by"])

            self.public = Recipe.objects.create(
                space=self.space, name="Pública SQL", servings=1, created_by=self.other,
            )
            self.owner_private = Recipe.objects.create(
                space=self.space, name="Privada propia SQL", servings=1,
                created_by=self.owner, private=True,
            )
            self.shared_private = Recipe.objects.create(
                space=self.space, name="Privada compartida SQL", servings=1,
                created_by=self.other, private=True,
            )
            self.shared_private.shared.add(self.owner)
            self.denied_private = Recipe.objects.create(
                space=self.space, name="Privada no compartida SQL", servings=1,
                created_by=self.other, private=True,
            )
            self.foreign_recipe = Recipe.objects.create(
                space=self.foreign_space, name="Receta SQL ajena", servings=1,
                created_by=self.foreign_user,
            )

            self.unit = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.cost_recipe = Recipe.objects.create(
                space=self.space,
                name="Coste SQL con quince ingredientes",
                servings=1,
                created_by=self.owner,
            )
            step = Step.objects.create(space=self.space, name="Preparar quince ingredientes")
            now = timezone.now()
            for index in range(self.INGREDIENT_COUNT):
                food = Food.objects.create(space=self.space, name=f"Ingrediente SQL {index:02d}")
                step.ingredients.add(Ingredient.objects.create(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    amount=Decimal("0.1"),
                    order=index,
                ))
                package = PackageFormat.objects.create(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    label=f"Formato SQL {index:02d}",
                    quantity=Decimal("1"),
                    is_reference=True,
                )
                PriceVersion.objects.create(
                    space=self.space,
                    package=package,
                    amount=Decimal("10"),
                    valid_from=now,
                    created_by=self.owner,
                )
            self.cost_recipe.steps.add(step)

    def recipe_ids(self, user):
        with scopes_disabled():
            return set(visible_recipes(user, self.space).values_list("pk", flat=True))

    def test_visible_recipes_uses_exists_without_join_distinct_and_preserves_acl(self):
        with scopes_disabled():
            queryset = visible_recipes(self.owner, self.space)
            sql = str(queryset.query)
            owner_ids = set(queryset.values_list("pk", flat=True))

        self.assertEqual(owner_ids, {
            self.public.pk,
            self.owner_private.pk,
            self.shared_private.pk,
            self.cost_recipe.pk,
        })
        upper_sql = " ".join(sql.upper().split())
        self.assertIn("EXISTS", upper_sql)
        self.assertIn("COOKBOOK_RECIPE_SHARED", upper_sql)
        self.assertNotIn("LEFT OUTER JOIN", upper_sql)
        self.assertNotIn("SELECT DISTINCT", upper_sql)

        self.assertEqual(self.recipe_ids(self.admin), {self.public.pk, self.cost_recipe.pk})
        self.assertNotIn(self.foreign_recipe.pk, owner_ids)
        self.assertNotIn(self.denied_private.pk, owner_ids)

        with scopes_disabled():
            self.shared_private.shared.remove(self.owner)
        revoked_ids = self.recipe_ids(self.owner)
        self.assertNotIn(self.shared_private.pk, revoked_ids)
        self.assertEqual(revoked_ids, {self.public.pk, self.owner_private.pk, self.cost_recipe.pk})

    def test_direct_cost_of_fifteen_ingredients_uses_joined_graph_in_at_most_seven_queries(self):
        with scopes_disabled(), CaptureQueriesContext(connection) as captured:
            result = cost_recipe(self.cost_recipe, "1", user=self.owner)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(Decimal(result["unrounded"]), Decimal("15"))
        self.assertEqual(Decimal(result["known_subtotal"]), Decimal("15"))
        self.assertEqual(len(result["lines"]), self.INGREDIENT_COUNT)
        self.assertTrue(all(
            line["status"] == "complete" and Decimal(line["unrounded"]) == Decimal("1")
            for line in result["lines"]
        ))
        self.assertLessEqual(len(captured), 7, [query["sql"] for query in captured.captured_queries])

        normalized = [" ".join(query["sql"].lower().split()) for query in captured.captured_queries]
        ingredient_queries = [sql for sql in normalized if 'from "cookbook_ingredient"' in sql]
        self.assertEqual(len(ingredient_queries), 1, normalized)
        self.assertIn('join "cookbook_food"', ingredient_queries[0])
        self.assertIn('join "cookbook_unit"', ingredient_queries[0])
        self.assertFalse(
            any(re.search(r'\bfrom\s+"cookbook_food"(?:\s|$)', sql) for sql in normalized),
            normalized,
        )
        self.assertFalse(
            any(re.search(r'\bfrom\s+"cookbook_unit"(?:\s|$)', sql) for sql in normalized),
            normalized,
        )
