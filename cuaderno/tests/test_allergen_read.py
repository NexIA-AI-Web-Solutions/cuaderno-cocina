"""Declared/unknown allergen reads over the native recipe graph."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled

from cookbook.models import Food, Ingredient, Recipe, Space, Step
from cuaderno.models import AllergenDeclaration, ServicePlan, SpaceProfile
from cuaderno.tests.test_services import ServiceFixtureMixin
from cuaderno.services.allergens import _assessment


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AllergenReadTests(ServiceFixtureMixin, TestCase):
    url = "/api/cuaderno/allergens/"

    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.guest = self.make_user("allergen-guest", "guest", self.household)

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(
            response.get("Content-Type", "").startswith("application/json"),
            "The allergen API is missing; the HTML SPA fallback is not an API.",
        )
        return response.data

    def food_get(self, food=None, *, user=None):
        return self.client_for(user or self.user).get(self.url, {"food": (food or self.food).pk})

    def recipe_get(self, recipe=None, *, user=None):
        return self.client_for(user or self.user).get(self.url, {"recipe": (recipe or self.recipe).pk})

    def declare(self, food, name, state, *, user=None):
        return self.client_for(user or self.user).post(
            self.url,
            {"food": food.pk, "name": name, "state": state},
            format="json",
        )

    def test_food_without_declarations_is_explicitly_unknown_not_absent(self):
        data = self.assert_json(self.food_get())

        self.assertEqual(data, {
            "scope": {"type": "food", "id": self.food.pk, "name": self.food.name},
            "assessment": AllergenDeclaration.UNKNOWN,
            "undeclared_means_absent": False,
            "unknown_ingredients": False,
            "foods": [{"id": self.food.pk, "name": self.food.name, "declarations": []}],
        })
        self.assertNotIn(data["assessment"], ("absent", "safe"))
        self.assertNotIn("safe", str(data).lower())

    def test_latest_append_only_declaration_wins_per_exact_food_and_name(self):
        with scopes_disabled():
            old = AllergenDeclaration.objects.create(
                space=self.space, food=self.food, name="Gluten", state=AllergenDeclaration.DECLARED,
            )
            latest = AllergenDeclaration.objects.create(
                space=self.space, food=self.food, name="Gluten", state=AllergenDeclaration.UNKNOWN,
            )
            nuts = AllergenDeclaration.objects.create(
                space=self.space, food=self.food, name="Frutos secos", state=AllergenDeclaration.DECLARED,
            )

        data = self.assert_json(self.food_get())

        self.assertEqual(data["assessment"], AllergenDeclaration.DECLARED)
        self.assertEqual(data["foods"][0]["declarations"], [
            {"id": nuts.pk, "name": "Frutos secos", "state": AllergenDeclaration.DECLARED, "created_by": None, "created_at": nuts.created_at.isoformat()},
            {"id": latest.pk, "name": "Gluten", "state": AllergenDeclaration.UNKNOWN, "created_by": None, "created_at": latest.created_at.isoformat()},
        ])
        with scopes_disabled():
            self.assertEqual(AllergenDeclaration.objects.filter(pk__in=[old.pk, latest.pk, nuts.pk]).count(), 3)

    def test_recipe_consolidates_direct_food_and_unknown_native_ingredients(self):
        with scopes_disabled():
            declaration = AllergenDeclaration.objects.create(
                space=self.space, food=self.food, name="Apio", state=AllergenDeclaration.DECLARED,
            )
            step = self.recipe.steps.get()
            step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=None, unit=None, amount=Decimal("0"), no_amount=True,
                original_text="Ingrediente sintético sin catálogo",
            ))
            known_without_amount = Food.objects.create(space=self.space, name="Pimienta sintética")
            step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=known_without_amount, unit=None, amount=Decimal("0"), no_amount=True,
            ))

        data = self.assert_json(self.recipe_get())

        self.assertEqual(data["scope"], {"type": "recipe", "id": self.recipe.pk, "name": self.recipe.name})
        self.assertEqual(data["assessment"], AllergenDeclaration.DECLARED)
        self.assertTrue(data["unknown_ingredients"])
        foods = {row["id"]: row for row in data["foods"]}
        self.assertEqual(foods[self.food.pk]["declarations"], [
            {"id": declaration.pk, "name": "Apio", "state": AllergenDeclaration.DECLARED, "created_by": None, "created_at": declaration.created_at.isoformat()},
        ])
        self.assertEqual(foods[known_without_amount.pk]["declarations"], [])

    def test_invalid_legacy_states_are_unknown_without_rewriting_history(self):
        # New database checks reject invalid states. The read boundary remains
        # defensive for historical/imported payloads without corrupting live rows.
        for state in ("absent", "safe", "", "corrupt"):
            with self.subTest(state=state), patch('cuaderno.services.allergens.AllergenDeclaration.objects.filter') as query:
                historical = {'id': 1, 'food_id': self.food.pk, 'name': 'Gluten', 'state': state,
                              'created_by_id': None, 'created_at': None}
                query.return_value.order_by.return_value.values.return_value = [historical]
                data = _assessment({'type': 'food', 'id': self.food.pk, 'name': self.food.name}, [self.food], self.space)
                self.assertEqual(data["assessment"], AllergenDeclaration.UNKNOWN)
                self.assertEqual(data["foods"][0]["declarations"], [{
                    "id": 1, "name": "Gluten", "state": AllergenDeclaration.UNKNOWN, "created_by": None, "created_at": None,
                }])
                self.assertEqual(historical['state'], state)

    def test_step_and_food_subrecipes_are_walked_and_foods_are_deduplicated(self):
        with scopes_disabled():
            child_food = Food.objects.create(space=self.space, name="Leche sintética")
            child = Recipe.objects.create(
                space=self.space, name="Salsa hija", servings=1, created_by=self.user,
            )
            child_step = Step.objects.create(space=self.space, name="Mezclar hija")
            child_step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=child_food, unit=self.kg, amount=Decimal("1"),
            ))
            child.steps.add(child_step)
            output_food = Food.objects.create(space=self.space, name="Salsa enlazada", recipe=child)
            root_step = self.recipe.steps.get()
            root_step.step_recipe = child
            root_step.save(update_fields=["step_recipe"])
            root_step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=output_food, unit=self.kg, amount=Decimal("1"),
            ))
            declaration = AllergenDeclaration.objects.create(
                space=self.space, food=child_food, name="Leche", state=AllergenDeclaration.DECLARED,
            )

        data = self.assert_json(self.recipe_get())

        ids = [row["id"] for row in data["foods"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {self.food.pk, output_food.pk, child_food.pk})
        child_row = next(row for row in data["foods"] if row["id"] == child_food.pk)
        self.assertEqual(child_row["declarations"], [
            {"id": declaration.pk, "name": "Leche", "state": AllergenDeclaration.DECLARED, "created_by": None, "created_at": declaration.created_at.isoformat()},
        ])

    def test_private_child_and_cross_space_ids_fail_closed_without_names(self):
        with scopes_disabled():
            private_child = Recipe.objects.create(
                space=self.space, name="Nombre hijo secreto", servings=1,
                created_by=self.user, private=True,
            )
            root_step = self.recipe.steps.get()
            root_step.step_recipe = private_child
            root_step.save(update_fields=["step_recipe"])
            other_space = Space.objects.create(name="Espacio alérgenos ajeno")
            foreign_user = get_user_model().objects.create_user(
                username="allergen-foreign", password="synthetic-only",
            )
            foreign_recipe = Recipe.objects.create(
                space=other_space, name="Receta ajena secreta", servings=1, created_by=foreign_user,
            )
            foreign_food = Food.objects.create(space=other_space, name="Alimento ajeno secreto")

        private_response = self.recipe_get(user=self.helper)
        foreign_food_response = self.client_for(self.user).get(self.url, {"food": foreign_food.pk})
        foreign_recipe_response = self.client_for(self.user).get(self.url, {"recipe": foreign_recipe.pk})

        for response in (private_response, foreign_food_response, foreign_recipe_response):
            self.assert_json(response, 404)
            rendered = str(response.data)
            self.assertNotIn("Nombre hijo secreto", rendered)
            self.assertNotIn("Receta ajena secreta", rendered)
            self.assertNotIn("Alimento ajeno secreto", rendered)

    def test_guest_can_read_public_food_and_recipe_but_cannot_write(self):
        self.assert_json(self.food_get(user=self.guest))
        self.assert_json(self.recipe_get(user=self.guest))
        denied = self.declare(self.food, "Gluten", AllergenDeclaration.UNKNOWN, user=self.guest)
        self.assert_json(denied, 403)
        with scopes_disabled():
            self.assertFalse(AllergenDeclaration.objects.exists())

    def test_edition_gates_writes_but_not_reads(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.ESENCIAL
            self.profile.save(update_fields=["edition"])
        self.assert_json(self.food_get())
        self.assert_json(self.declare(self.food, "Gluten", AllergenDeclaration.UNKNOWN), 403)

        for edition in (SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            with self.subTest(edition=edition), scopes_disabled():
                self.profile.edition = edition
                self.profile.save(update_fields=["edition"])
            created = self.declare(self.food, f"Declaración {edition}", AllergenDeclaration.UNKNOWN)
            data = self.assert_json(created, 201)
            self.assertEqual(data["state"], AllergenDeclaration.UNKNOWN)
            self.assertFalse(data["undeclared_means_absent"])

    def test_get_requires_exactly_one_strict_positive_identifier(self):
        client = self.client_for(self.user)
        requests = (
            {},
            {"food": self.food.pk, "recipe": self.recipe.pk},
            {"food": "abc"},
            {"food": "0"},
            {"recipe": "-1"},
            {"recipe": "1.5"},
        )
        for params in requests:
            with self.subTest(params=params):
                self.assert_json(client.get(self.url, params), 400)

    def test_post_rejects_malformed_name_state_and_overlength_without_truncation(self):
        client = self.client_for(self.user)
        with scopes_disabled():
            before = AllergenDeclaration.objects.count()
        invalid = (
            {"food": self.food.pk, "name": "", "state": "unknown"},
            {"food": self.food.pk, "name": ["Gluten"], "state": "unknown"},
            {"food": self.food.pk, "name": "x" * 129, "state": "unknown"},
            {"food": self.food.pk, "name": "Gluten", "state": "absent"},
            {"food": self.food.pk, "name": "Gluten", "state": False},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assert_json(client.post(self.url, payload, format="json"), 400)
        with scopes_disabled():
            self.assertEqual(AllergenDeclaration.objects.count(), before)

        accepted = client.post(
            self.url,
            {"food": self.food.pk, "name": " y" + ("x" * 125) + " ", "state": "declared"},
            format="json",
        )
        self.assert_json(accepted, 201)
        with scopes_disabled():
            self.assertEqual(AllergenDeclaration.objects.get(pk=accepted.data["id"]).name, "y" + ("x" * 125))

    def test_recipe_read_is_deterministic_and_does_not_write(self):
        with scopes_disabled():
            second = Food.objects.create(space=self.space, name="Aceite sintético")
            step = self.recipe.steps.get()
            step.ingredients.add(Ingredient.objects.create(
                space=self.space, food=second, unit=self.kg, amount=Decimal("1"),
            ))
            AllergenDeclaration.objects.create(
                space=self.space, food=second, name="Sésamo", state=AllergenDeclaration.UNKNOWN,
            )
            before = AllergenDeclaration.objects.count()

        first = self.assert_json(self.recipe_get())
        second_read = self.assert_json(self.recipe_get())

        self.assertEqual(first, second_read)
        self.assertEqual([row["name"] for row in first["foods"]], sorted(
            [self.food.name, second.name], key=lambda value: value.casefold(),
        ))
        with scopes_disabled():
            self.assertEqual(AllergenDeclaration.objects.count(), before)

    def test_confirmation_freezes_allergens_while_live_declarations_continue(self):
        initial = self.declare(self.food, "Gluten", AllergenDeclaration.DECLARED)
        self.assert_json(initial, 201)
        live_before = self.assert_json(self.recipe_get())
        _, plan = self.create_plan(title="Ficha congelada de alérgenos", covers=10)

        confirmed = self.transition(plan, "confirm")

        self.assert_json(confirmed)
        frozen = confirmed.data["snapshot"]["allergens"]
        self.assertEqual(frozen, live_before)
        changed = self.declare(self.food, "Gluten", AllergenDeclaration.UNKNOWN)
        self.assert_json(changed, 201)
        live_after = self.assert_json(self.recipe_get())
        self.assertEqual(live_after["assessment"], AllergenDeclaration.UNKNOWN)
        self.assertNotEqual(live_after, frozen)

        reread = self.client_for(self.user).get(f"/api/cuaderno/services/{plan.pk}/")
        self.assert_json(reread)
        self.assertEqual(reread.data["snapshot"]["allergens"], frozen)

    def test_legacy_snapshot_without_allergens_remains_unknown_without_lazy_write(self):
        _, plan = self.create_plan(title="Servicio heredado")
        legacy_snapshot = {"schema_version": 1, "recipe_id": self.recipe.pk, "needs": []}
        with scopes_disabled():
            ServicePlan.objects.filter(pk=plan.pk).update(
                state=ServicePlan.CONFIRMED,
                snapshot=legacy_snapshot,
            )

        response = self.client_for(self.user).get(f"/api/cuaderno/services/{plan.pk}/")

        self.assert_json(response)
        self.assertEqual(response.data["snapshot"], legacy_snapshot)
        self.assertIsNone(response.data["snapshot"].get("allergens"))
        with scopes_disabled():
            plan.refresh_from_db()
            self.assertEqual(plan.snapshot, legacy_snapshot)
