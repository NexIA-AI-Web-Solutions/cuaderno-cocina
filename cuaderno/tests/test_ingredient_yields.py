"""Persisted gross/useful ingredient yield contracts on native Tandoor rows."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient, APIRequestFactory

from cookbook.models import Food, Household, Ingredient, Recipe, Space, Step, Unit, UserSpace
from cookbook.serializer import IngredientExportSerializer, IngredientSimpleSerializer, IngredientSerializer
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
from cuaderno.services.costing import cost_recipe
from cuaderno.services.subrecipes import sheet_from_recipes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IngredientYieldApiTests(TestCase):
    def make_user(self, username, group="user", *, space=None, household=None):
        user = get_user_model().objects.create_user(username=username, password="synthetic-only")
        membership = UserSpace.objects.create(
            user=user,
            space=space or self.space,
            household=household or self.household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name=group)[0])
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Synthetic ingredient yields")
            self.household = Household.objects.create(space=self.space, name="Synthetic kitchen")
            self.owner = self.make_user("yield-owner")
            self.helper = self.make_user("yield-helper")
            self.guest = self.make_user("yield-guest", "guest")
            self.space.created_by = self.owner
            self.space.save(update_fields=["created_by"])
            self.profile = SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)
            self.kg = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.g = Unit.objects.create(space=self.space, name="g", base_unit="g")
            self.food = Food.add_root(space=self.space, name="Synthetic potato")
            package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.kg,
                quantity=Decimal("1"),
                label="Synthetic 1 kg",
            )
            PriceVersion.objects.create(
                space=self.space,
                package=package,
                amount=Decimal("12"),
                valid_from=timezone.now(),
                created_by=self.owner,
            )
            self.recipe = Recipe.objects.create(
                space=self.space,
                created_by=self.owner,
                name="Synthetic useful potato",
                private=True,
                servings=4,
            )
            self.step = Step.objects.create(space=self.space, instruction="Prepare synthetic potato")
            self.ingredient = Ingredient.objects.create(
                space=self.space,
                food=self.food,
                unit=self.g,
                amount=Decimal("600"),
            )
            self.step.ingredients.add(self.ingredient)
            self.recipe.steps.add(self.step)
        self.url = f"/api/cuaderno/recipes/{self.recipe.pk}/ingredient-yields/"
        self.client = self.client_for(self.owner)

    def put_policy(self, *, basis="net_usable", ratio="0.8", client=None, ingredient=None):
        current = self.client.get(self.url)
        self.assert_json(current)
        revision = current.data.get("revision")
        self.assertIsInstance(revision, str)
        self.assertRegex(revision, r"^[0-9a-f]{64}$")
        return (client or self.client).put(
            self.url,
            {
                "ingredient": (ingredient or self.ingredient).pk,
                "quantity_basis": basis,
                "yield_ratio": ratio,
                "revision": revision,
            },
            format="json",
        )

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(
            response.get("Content-Type", "").startswith("application/json"),
            "The ingredient-yield API is missing; the HTML SPA fallback is not an API.",
        )

    def test_get_and_put_persist_native_ingredient_policy_with_strict_decimal_strings(self):
        initial = self.client.get(self.url)
        self.assert_json(initial)
        self.assertEqual(initial.data["edition"], SpaceProfile.PROFESIONAL)
        self.assertEqual(len(initial.data["ingredients"]), 1)
        self.assertEqual(initial.data["ingredients"][0]["quantity_basis"], "gross")
        self.assertIsNone(initial.data["ingredients"][0]["yield_ratio"])
        self.assertFalse(initial.data["ingredients"][0]["is_subrecipe"])

        updated = self.put_policy()
        self.assert_json(updated)
        line = updated.data["ingredients"][0]
        self.assertEqual(line["id"], self.ingredient.pk)
        self.assertEqual(line["food_name"], "Synthetic potato")
        self.assertEqual(Decimal(line["amount"]), Decimal("600"))
        self.assertEqual(line["unit"], "g")
        self.assertEqual(line["quantity_basis"], "net_usable")
        self.assertEqual(Decimal(line["yield_ratio"]), Decimal("0.8"))

        for invalid in (0.8, True, "0", "-0.1", "1.0000000000000001", "0.12345678901234567", "NaN", "Infinity"):
            with self.subTest(invalid=invalid):
                response = self.put_policy(ratio=invalid)
                self.assert_json(response, 400)
        self.assert_json(self.put_policy(ratio=None), 400)

    def test_any_edition_can_read_but_only_professional_user_can_write(self):
        with scopes_disabled():
            self.recipe.shared.add(self.helper, self.guest)
            self.profile.edition = SpaceProfile.ESENCIAL
            self.profile.save(update_fields=["edition"])
        self.assert_json(self.client.get(self.url))
        self.assert_json(self.client.put(
            self.url,
            {"ingredient": self.ingredient.pk, "quantity_basis": "gross", "yield_ratio": None},
            format="json",
        ), 403)
        self.assert_json(self.client_for(self.helper).get(self.url))
        self.assert_json(self.client_for(self.guest).get(self.url))
        self.assert_json(self.put_policy(client=self.client_for(self.guest)), 403)

        with scopes_disabled():
            self.profile.edition = SpaceProfile.PROFESIONAL
            self.profile.save(update_fields=["edition"])
        self.assert_json(self.put_policy())

    def test_private_and_cross_recipe_space_or_shared_ingredient_fail_closed(self):
        self.assertEqual(self.client_for(self.helper).get(self.url).status_code, 404)
        with scopes_disabled():
            other_recipe = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Other recipe", private=True, servings=1,
            )
            other_step = Step.objects.create(space=self.space)
            other_ingredient = Ingredient.objects.create(
                space=self.space, food=self.food, unit=self.g, amount=Decimal("1"),
            )
            other_step.ingredients.add(other_ingredient)
            other_recipe.steps.add(other_step)
        self.assert_json(self.put_policy(ingredient=other_ingredient), 404)

        with scopes_disabled():
            other_recipe.steps.add(self.step)
        self.assert_json(self.put_policy(), 400)

        with scopes_disabled():
            other_space = Space.objects.create(name="Other yield space")
            other_g = Unit.objects.create(space=other_space, name="g", base_unit="g")
            other_food = Food.add_root(space=other_space, name="Other food")
            foreign = Ingredient.objects.create(
                space=other_space, food=other_food, unit=other_g, amount=Decimal("1"),
            )
        self.assert_json(self.put_policy(ingredient=foreign), 404)

    def test_subrecipe_policy_is_rejected_by_api_and_costing_runtime(self):
        with scopes_disabled():
            child = Recipe.objects.create(
                space=self.space, created_by=self.owner, name="Synthetic child", private=True, servings=1,
            )
            child_food = Food.add_root(space=self.space, name="Synthetic child food", recipe=child)
            child_use = Ingredient.objects.create(
                space=self.space, food=child_food, unit=self.g, amount=Decimal("100"),
            )
            self.step.ingredients.add(child_use)
        self.assert_json(self.put_policy(ingredient=child_use), 400)

        with scopes_disabled():
            Ingredient.objects.filter(pk=child_use.pk).update(
                quantity_basis="net_usable", yield_ratio=Decimal("0.8"),
            )
        cost = self.client.get(f"/api/cuaderno/recipes/{self.recipe.pk}/cost/?servings=4")
        self.assert_json(cost, 400)

    def test_useful_policy_drives_persisted_cost_and_scaled_production_needs_once(self):
        self.assert_json(self.put_policy())
        with scopes_disabled():
            cost = cost_recipe(self.recipe, "4", user=self.owner)
            scaled_cost = cost_recipe(self.recipe, "8", user=self.owner)
            sheet = sheet_from_recipes([self.recipe.pk], self.space, self.owner)
            scaled_sheet = sheet_from_recipes(
                [self.recipe.pk], self.space, self.owner, factors={self.recipe.pk: Decimal("2")},
            )
        self.assertEqual(Decimal(cost["total"]), Decimal("9"))
        self.assertEqual(Decimal(scaled_cost["total"]), Decimal("18"))
        self.assertEqual(Decimal(sheet["needs"]["Synthetic potato"]), Decimal("750"))
        self.assertEqual(Decimal(scaled_sheet["needs"]["Synthetic potato"]), Decimal("1500"))
        trace = sheet["ingredient_yields"][0]
        self.assertEqual(trace["ingredient_id"], self.ingredient.pk)
        self.assertEqual(Decimal(trace["useful_quantity"]), Decimal("600"))
        self.assertEqual(Decimal(trace["purchased_quantity"]), Decimal("750"))
        self.assertEqual(Decimal(trace["waste_quantity"]), Decimal("150"))

    def test_gross_basis_never_adjusts_amount_even_with_a_valid_ratio(self):
        self.assert_json(self.put_policy(basis="gross", ratio="0.8"))
        with scopes_disabled():
            cost = cost_recipe(self.recipe, "4", user=self.owner)
            sheet = sheet_from_recipes([self.recipe.pk], self.space, self.owner)
        self.assertEqual(Decimal(cost["total"]), Decimal("7.2"))
        self.assertEqual(Decimal(sheet["needs"]["Synthetic potato"]), Decimal("600"))
        self.assert_json(self.put_policy(basis="gross", ratio=None))

    def test_confirmed_service_freezes_yield_trace_cost_and_needs(self):
        self.assert_json(self.put_policy())
        created = self.client.post(
            "/api/cuaderno/services/",
            {
                "recipe": self.recipe.pk,
                "covers": "4",
                "service_date": "2026-10-25",
                "title": "Synthetic yield snapshot",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        detail_url = f"/api/cuaderno/services/{created.data['id']}/"
        confirmed = self.client.post(detail_url, {"action": "confirm"}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        frozen = confirmed.data["snapshot"]
        self.assertEqual(frozen["schema_version"], 2)
        self.assertEqual(Decimal(frozen["cost"]["total"]), Decimal("9"))
        self.assertEqual(Decimal(frozen["needs"][0]["quantity"]), Decimal("750"))
        trace = frozen["ingredient_yields"][0]
        self.assertEqual(trace["ingredient_id"], self.ingredient.pk)
        self.assertEqual(trace["quantity_basis"], "net_usable")
        self.assertEqual(Decimal(trace["yield_ratio"]), Decimal("0.8"))
        self.assertEqual(Decimal(trace["waste_quantity"]), Decimal("150"))

        self.assert_json(self.put_policy(ratio="0.5"))
        current = self.client.get(f"/api/cuaderno/recipes/{self.recipe.pk}/cost/?servings=4")
        self.assert_json(current)
        self.assertEqual(Decimal(current.data["total"]), Decimal("14.4"))
        reread = self.client.get(detail_url)
        self.assertEqual(reread.status_code, 200, reread.content)
        self.assertEqual(reread.data["snapshot"], frozen)

    def test_native_serializers_expose_and_validate_yield_fields_without_parallel_model(self):
        self.assert_json(self.put_policy())
        self.ingredient.refresh_from_db()
        simple = IngredientSimpleSerializer(self.ingredient).data
        exported = IngredientExportSerializer(self.ingredient).data
        for payload in (simple, exported):
            self.assertEqual(payload["quantity_basis"], "net_usable")
            self.assertEqual(Decimal(payload["yield_ratio"]), Decimal("0.8"))

        request = APIRequestFactory().patch("/api/ingredient/")
        request.space = self.space
        request.user = self.owner
        serializer = IngredientSimpleSerializer(
            self.ingredient,
            data={"quantity_basis": "gross", "yield_ratio": None},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.quantity_basis, "gross")
        self.assertIsNone(updated.yield_ratio)

    def test_native_serializer_writers_reject_subrecipe_yield_on_update_and_create(self):
        with scopes_disabled():
            child = Recipe.objects.create(space=self.space, created_by=self.owner, name="Native child", servings=1)
            food = Food.add_root(space=self.space, name="Native child food", recipe=child)
            ingredient = Ingredient.objects.create(space=self.space, food=food, unit=self.g, amount=1)
        request = APIRequestFactory().patch("/api/ingredient/")
        request.space = self.space
        request.user = self.owner
        for serializer_class in (IngredientSimpleSerializer, IngredientSerializer, IngredientExportSerializer):
            for instance in (ingredient, None):
                with self.subTest(serializer=serializer_class.__name__, create=instance is None):
                    data = {"quantity_basis": "net_usable", "yield_ratio": "0.8"}
                    if instance is None:
                        data.update({"food": {"id": food.pk, "name": food.name}, "unit": {"name": "g"}, "amount": "1"})
                    serializer = serializer_class(instance, data=data, partial=True, context={"request": request})
                    self.assertFalse(serializer.is_valid())
                    self.assertIn("yield_ratio", serializer.errors)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.quantity_basis, "gross")
        self.assertIsNone(ingredient.yield_ratio)

    def test_backend_rejects_exponential_ratio_like_the_frontend(self):
        self.assert_json(self.put_policy(ratio="8e-1"), 400)

    def test_portable_exchange_preserves_native_yield_policy_and_cost(self):
        self.assert_json(self.put_policy())
        document = self.client.get("/api/cuaderno/exchange/").json()
        line = document["recipes"][0]["steps"][0]["ingredients"][0]
        self.assertEqual(line["quantity_basis"], "net_usable")
        self.assertEqual(Decimal(line["yield_ratio"]), Decimal("0.8"))
        with scopes_disabled():
            target = Space.objects.create(name="Yield import target")
            household = Household.objects.create(space=target, name="Target team")
            user = self.make_user("yield-import-user", space=target, household=household)
            SpaceProfile.objects.create(space=target, edition=SpaceProfile.PROFESIONAL)
        response = self.client_for(user).post("/api/cuaderno/exchange/", document, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        with scopes_disabled():
            restored = Recipe.objects.get(space=target)
            ingredient = restored.steps.get().ingredients.get()
            self.assertEqual(ingredient.quantity_basis, "net_usable")
            self.assertEqual(ingredient.yield_ratio, Decimal("0.8"))
            self.assertEqual(Decimal(cost_recipe(restored, "4", user=user)["total"]), Decimal("9"))
