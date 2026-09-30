"""Native detail must not bypass ACL through nested serializers."""

from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Ingredient, Recipe, ShareLink, Space, Step, Unit
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeRecipeVisibilityTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.guest = self.make_user("native-recipe-guest", "guest", self.household)
            self.child = Recipe.objects.create(
                space=self.space, name="Subreceta secreta", private=True, created_by=self.user,
            )
            self.child_step = Step.objects.create(space=self.space, name="Paso secreto")
            self.child.steps.add(self.child_step)
            self.child_food = Food.objects.create(space=self.space, name="Preparación secreta", recipe=self.child)
            self.root_step = self.recipe.steps.get()

    def read(self, user=None, *, share=None, anonymous=False):
        client = APIClient() if anonymous else self.client_for(user or self.helper)
        return client.get(f"/api/recipe/{self.recipe.pk}/", {"share": share} if share else {})

    def assert_denied(self, response):
        self.assertEqual(response.status_code, 404, response.content)
        for name in (self.child.name, self.child_food.name, self.child_step.name):
            self.assertNotIn(name, str(response.data))

    def test_private_food_recipe_cannot_leak_from_public_root_after_revocation(self):
        with scopes_disabled():
            self.root_step.ingredients.add(Ingredient.objects.create(space=self.space, food=self.child_food))
            self.child.shared.add(self.helper)
        self.assertEqual(self.read().status_code, 200)
        with scopes_disabled():
            self.child.shared.clear()
        self.assert_denied(self.read())
        self.assert_denied(self.read(self.guest))
        self.assertEqual(self.read(self.user).status_code, 200)

    def test_private_step_recipe_cannot_leak_from_public_root_after_revocation(self):
        with scopes_disabled():
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
            self.child.shared.add(self.helper)
        self.assertEqual(self.read().status_code, 200)
        with scopes_disabled():
            self.child.shared.clear()
        self.assert_denied(self.read())
        self.assert_denied(self.read(self.guest))
        self.assertEqual(self.read(self.user).status_code, 200)

    def test_native_patch_response_does_not_bypass_private_graph_and_rolls_back(self):
        with scopes_disabled():
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
            previous = self.recipe.description
        response = self.client_for(self.helper).patch(
            f"/api/recipe/{self.recipe.pk}/", {"description": "Cambio no autorizado al grafo"}, format="json",
        )
        self.assert_denied(response)
        with scopes_disabled():
            self.recipe.refresh_from_db()
            self.assertEqual(self.recipe.description, previous)

    def test_direct_ingredient_detail_cannot_serialize_hidden_food_recipe(self):
        with scopes_disabled():
            ingredient = Ingredient.objects.create(space=self.space, food=self.child_food)
            self.root_step.ingredients.add(ingredient)
        client = self.client_for(self.helper)
        for params in ({}, {"simple": "true"}):
            self.assert_denied(client.get(f"/api/ingredient/{ingredient.pk}/", params))
        with scopes_disabled():
            self.child.shared.add(self.helper)
        self.assertEqual(client.get(f"/api/ingredient/{ingredient.pk}/").status_code, 200)

    def test_direct_step_detail_cannot_expose_private_step_recipe_identifier(self):
        with scopes_disabled():
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
        response = self.client_for(self.helper).get(f"/api/step/{self.root_step.pk}/")
        self.assert_denied(response)
        with scopes_disabled():
            self.child.shared.add(self.helper)
        self.assertEqual(self.client_for(self.helper).get(f"/api/step/{self.root_step.pk}/").status_code, 200)

    def test_ingredient_list_filters_hidden_and_foreign_references_before_pagination(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="List foreign space")
            foreign_food = Food.objects.create(space=foreign_space, name="List foreign food secret")
            foreign_unit = Unit.objects.create(space=foreign_space, name="List foreign unit secret")
            bad = [
                Ingredient.objects.create(space=self.space, food=self.child_food),
                Ingredient.objects.create(space=self.space, food=foreign_food),
                Ingredient.objects.create(space=self.space, food=self.food, unit=foreign_unit),
                Ingredient.objects.create(space=foreign_space, food=self.food),
            ]
            self.root_step.ingredients.add(*bad)
            good_id = self.root_step.ingredients.exclude(pk__in=[row.pk for row in bad]).get().pk
        response = self.client_for(self.helper).get("/api/ingredient/", {"page_size": 1})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([row["id"] for row in response.data["results"]], [good_id])
        for name in (self.child_food.name, foreign_food.name, foreign_unit.name):
            self.assertNotIn(name, str(response.data))
        for row in bad:
            self.assertEqual(self.client_for(self.helper).get(f"/api/ingredient/{row.pk}/").status_code, 404)

    def test_step_list_filters_contaminated_graphs_without_poisoning_valid_rows(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="Step list foreign space")
            foreign_food = Food.objects.create(space=foreign_space, name="Step list foreign food secret")
            foreign_unit = Unit.objects.create(space=foreign_space, name="Step list foreign unit secret")
            bad = [Step.objects.create(space=self.space, name="Hidden step child", step_recipe=self.child)]
            for ingredient in (
                Ingredient.objects.create(space=self.space, food=self.child_food),
                Ingredient.objects.create(space=self.space, food=foreign_food),
                Ingredient.objects.create(space=self.space, food=self.food, unit=foreign_unit),
                Ingredient.objects.create(space=foreign_space, food=self.food),
            ):
                step = Step.objects.create(space=self.space, name="Contaminated step")
                step.ingredients.add(ingredient)
                bad.append(step)
            self.recipe.steps.add(*bad)
        response = self.client_for(self.helper).get("/api/step/", {"page_size": 1})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual([row["id"] for row in response.data["results"]], [self.root_step.pk])
        for name in (self.child_food.name, foreign_food.name, foreign_unit.name):
            self.assertNotIn(name, str(response.data))
        for row in bad:
            self.assertEqual(self.client_for(self.helper).get(f"/api/step/{row.pk}/").status_code, 404)

    def test_delete_external_response_obeys_private_graph_without_touching_metadata(self):
        with scopes_disabled():
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
            previous = (self.recipe.storage_id, self.recipe.file_path, self.recipe.file_uid)
        response = self.client_for(self.helper).patch(f"/api/recipe/{self.recipe.pk}/delete_external/", {}, format="json")
        self.assert_denied(response)
        with scopes_disabled():
            self.recipe.refresh_from_db()
            self.assertEqual((self.recipe.storage_id, self.recipe.file_path, self.recipe.file_uid), previous)

    def test_native_create_with_hidden_child_rolls_back_all_new_recipe_nodes(self):
        with scopes_disabled():
            before = (Recipe.objects.count(), Step.objects.count(), Ingredient.objects.count())
        response = self.client_for(self.helper).post("/api/recipe/", {
            "name": "Intento con hijo oculto", "steps": [{
                "name": "Paso con hijo privado", "ingredients": [], "step_recipe": self.child.pk,
            }],
        }, format="json")
        self.assert_denied(response)
        with scopes_disabled():
            self.assertEqual((Recipe.objects.count(), Step.objects.count(), Ingredient.objects.count()), before)

    def test_used_in_recipes_excludes_private_and_foreign_references(self):
        with scopes_disabled():
            ingredient = self.root_step.ingredients.get()
            self.child_step.ingredients.add(ingredient)
            foreign_space = Space.objects.create(name="Espacio ajeno sintético")
            foreign_recipe = Recipe.objects.create(
                space=foreign_space, name="Receta ajena secreta", created_by=self.user,
            )
            foreign_step = Step.objects.create(space=foreign_space, name="Paso ajeno")
            foreign_step.ingredients.add(ingredient)
            foreign_recipe.steps.add(foreign_step)
        response = self.read()
        self.assertEqual(response.status_code, 200, response.content)
        used = response.data["steps"][0]["ingredients"][0]["used_in_recipes"]
        self.assertEqual(used, [{"id": self.recipe.pk, "name": self.recipe.name}])

    def test_share_capability_preserves_private_root_without_granting_private_children(self):
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.save(update_fields=["private"])
            share = ShareLink.objects.create(space=self.space, recipe=self.recipe, created_by=self.user)
        allowed = self.read(share=str(share.uuid), anonymous=True)
        self.assertEqual(allowed.status_code, 200, allowed.content)
        with scopes_disabled():
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
        self.assert_denied(self.read(share=str(share.uuid), anonymous=True))
        self.assertEqual(self.read(self.user, share=str(share.uuid)).status_code, 200)

    def test_visible_cycles_remain_readable_for_native_editing(self):
        with scopes_disabled():
            self.child.private = False
            self.child.save(update_fields=["private"])
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
            self.child_step.step_recipe = self.recipe
            self.child_step.save(update_fields=["step_recipe"])
        response = self.read()
        self.assertEqual(response.status_code, 200, response.content)

    def test_foreign_step_relation_fails_closed(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="Otro espacio de receta")
            foreign_step = Step.objects.create(space=foreign_space, name="Paso ajeno secreto")
            self.recipe.steps.add(foreign_step)
        response = self.read()
        self.assertEqual(response.status_code, 404, response.content)
        self.assertNotIn(foreign_step.name, str(response.data))

    def test_foreign_ingredient_food_and_unit_relations_fail_closed(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="Espacio relaciones ajenas")
            food = Food.objects.create(space=foreign_space, name="Alimento ajeno secreto")
            unit = Unit.objects.create(space=foreign_space, name="Unidad ajena secreta")
            ingredient = self.root_step.ingredients.get()
        for field, value, original in (
            ("space", foreign_space, self.space), ("food", food, self.food), ("unit", unit, self.kg),
        ):
            with self.subTest(field=field), scopes_disabled():
                setattr(ingredient, field, value)
                ingredient.save(update_fields=[field])
                self.assert_denied(self.read())
                setattr(ingredient, field, original)
                ingredient.save(update_fields=[field])
        self.assertEqual(self.read().status_code, 200)

    def test_share_root_self_links_and_public_child_remain_readable(self):
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.save(update_fields=["private"])
            share = ShareLink.objects.create(space=self.space, recipe=self.recipe, created_by=self.user)
            self.child.private = False
            self.child.save(update_fields=["private"])
            self.root_step.step_recipe = self.child
            self.root_step.save(update_fields=["step_recipe"])
            self.child_step.step_recipe = self.recipe
            self.child_step.save(update_fields=["step_recipe"])
            root_food = Food.objects.create(space=self.space, name="Preparación raíz compartida", recipe=self.recipe)
            self.root_step.ingredients.add(Ingredient.objects.create(space=self.space, food=root_food))
        response = self.read(share=str(share.uuid), anonymous=True)
        self.assertEqual(response.status_code, 200, response.content)
        used = response.data["steps"][0]["ingredients"][0]["used_in_recipes"]
        self.assertEqual(used, [{"id": self.recipe.pk, "name": self.recipe.name}])
