"""Native ingredient quantities retain database precision and reject bad input."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient, APIRequestFactory

from cookbook.models import Food, Household, Ingredient, Recipe, Space, Step, Unit, UserSpace
from cookbook.serializer import IngredientExportSerializer, IngredientSerializer, IngredientSimpleSerializer
from cuaderno.models import SpaceProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeIngredientAmountPrecisionTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Synthetic native amount precision")
            self.household = Household.objects.create(space=self.space, name="Synthetic amount kitchen")
            self.user = get_user_model().objects.create_user(username="native-amount-owner", password="synthetic-only")
            membership = UserSpace.objects.create(user=self.user, space=self.space, household=self.household, active=True)
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.space.created_by = self.user
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)
            self.unit = Unit.objects.create(space=self.space, name="Synthetic amount g", base_unit="g")
            self.food = Food.add_root(space=self.space, name="Synthetic amount food")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.client.raise_request_exception = False

    def payload(self, amounts, *, new_nested=False):
        return {
            "name": "Synthetic precision recipe", "private": False, "servings": 4,
            "steps": [{"name": "Synthetic precision step", "instruction": "Synthetic data only.",
                       "ingredients": [{
                           "food": {"name": f"Synthetic rejected food {i}"} if new_nested else {"id": self.food.pk, "name": self.food.name},
                           "unit": {"name": f"Synthetic rejected unit {i}"} if new_nested else {"id": self.unit.pk, "name": self.unit.name},
                           "amount": amount, "no_amount": False,
                       } for i, amount in enumerate(amounts)]}],
        }

    def counts(self):
        with scopes_disabled():
            return tuple(model.objects.count() for model in (Recipe, Step, Ingredient, Food, Unit))

    def assert_amount_error(self, response):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(response.get("Content-Type", "").startswith("application/json"))
        self.assertIn("amount", str(response.data))
        self.assertIn("cantidad", str(response.data).lower())

    def test_native_recipe_post_persists_maximum_tiny_and_normalized_comma_without_float(self):
        values = ["9999999999999999.1234567890123456", "0.0000000000000001", " 400,5000000000000001 "]
        expected = [Decimal("9999999999999999.1234567890123456"), Decimal("0.0000000000000001"), Decimal("400.5000000000000001")]
        response = self.client.post("/api/recipe/", self.payload(values), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        with scopes_disabled():
            recipe = Recipe.objects.get(pk=response.data["id"])
            persisted = list(recipe.steps.get().ingredients.order_by("pk"))
            self.assertEqual([row.amount for row in persisted], expected)
        detail = self.client.get(f"/api/cuaderno/recipes/{recipe.pk}/ingredient-yields/")
        self.assertEqual(detail.status_code, 200, detail.content)
        by_id = {row["id"]: row["amount"] for row in detail.data["ingredients"]}
        for row, amount in zip(persisted, expected):
            self.assertIsInstance(by_id[row.pk], str)
            self.assertEqual(Decimal(by_id[row.pk]), amount)

    def test_invalid_nested_quantities_return_spanish_400_without_any_orphan(self):
        for invalid in ("10000000000000000", "NaN", "Infinity", "-Infinity", True, False,
                        "0.12345678901234567", "", "   ", "not-a-number", "+-1.00", "1..00", None):
            with self.subTest(invalid=invalid):
                before = self.counts()
                response = self.client.post("/api/recipe/", self.payload(["1", invalid], new_nested=True), format="json")
                self.assert_amount_error(response)
                self.assertEqual(self.counts(), before)

    def test_redundant_fraction_zeroes_negative_quantity_and_header_zero_remain_lossless(self):
        payload = self.payload(["400.00000000000000000", "0.00000000000000010", "-2.5000000000000000", "0"])
        payload["steps"][0]["ingredients"][-1].update(is_header=True, no_amount=True)
        response = self.client.post("/api/recipe/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        with scopes_disabled():
            recipe = Recipe.objects.get(pk=response.data["id"])
            rows = list(recipe.steps.get().ingredients.order_by("pk"))
            self.assertEqual([row.amount for row in rows], [Decimal("400"), Decimal("0.0000000000000001"), Decimal("-2.5"), Decimal("0")])
            self.assertTrue(rows[-1].is_header)
            self.assertTrue(rows[-1].no_amount)

    def test_native_ingredient_patch_is_exact_and_invalid_values_leave_existing_amount(self):
        with scopes_disabled():
            ingredient = Ingredient.objects.create(space=self.space, food=self.food, unit=self.unit, amount=Decimal("2"))
            recipe = Recipe.objects.create(space=self.space, created_by=self.user, name="Synthetic patch recipe", private=False)
            step = Step.objects.create(space=self.space, name="Synthetic patch step")
            step.ingredients.add(ingredient)
            recipe.steps.add(step)
        url = f"/api/ingredient/{ingredient.pk}/"
        response = self.client.patch(url, {"amount": "400,5000000000000001"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        with scopes_disabled():
            ingredient.refresh_from_db()
            self.assertEqual(ingredient.amount, Decimal("400.5000000000000001"))
        for invalid in ("10000000000000000", "NaN", True, "0.12345678901234567", ""):
            with self.subTest(invalid=invalid):
                before = self.counts()
                response = self.client.patch(url, {"amount": invalid}, format="json")
                self.assert_amount_error(response)
                self.assertEqual(self.counts(), before)
                with scopes_disabled():
                    ingredient.refresh_from_db()
                    self.assertEqual(ingredient.amount, Decimal("400.5000000000000001"))

    def test_all_three_native_ingredient_serializers_persist_and_return_exact_decimal_strings(self):
        request = APIRequestFactory().post("/api/ingredient/", {}, format="json")
        request.user = self.user
        request.space = self.space
        for serializer_class in (IngredientSimpleSerializer, IngredientSerializer, IngredientExportSerializer):
            with self.subTest(serializer=serializer_class.__name__), scopes_disabled():
                serializer = serializer_class(data={"food": None, "unit": None, "amount": "12,3456789012345678"}, context={"request": request})
                self.assertTrue(serializer.is_valid(), serializer.errors)
                ingredient = serializer.save()
                ingredient.refresh_from_db()
                self.assertEqual(ingredient.amount, Decimal("12.3456789012345678"))
                self.assertEqual(serializer_class(ingredient, context={"request": request}).data["amount"], "12.3456789012345678")
                rejected = serializer_class(data={"food": None, "unit": None, "amount": "NaN"}, context={"request": request})
                before = self.counts()
                self.assertFalse(rejected.is_valid())
                self.assertIn("cantidad", str(rejected.errors).lower())
                self.assertEqual(self.counts(), before)

    def test_native_json_get_put_roundtrip_and_note_edit_preserve_amounts_and_ids(self):
        values = ["9999999999999999.1234567890123456", "0.0000000000000001", "400.1234567890123456", "-0.000", "12.50000"]
        expected = [Decimal(value) for value in values]
        created = self.client.post("/api/recipe/", self.payload(values), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        url = f"/api/recipe/{created.data['id']}/"
        detail = self.client.get(url)
        self.assertEqual(detail.status_code, 200, detail.content)
        # Decode the actual wire JSON, as a browser does; response.data can hide
        # a Decimal encoder converting the amount to a lossy JSON number.
        payload = detail.json()
        rows = payload["steps"][0]["ingredients"]
        ids = [row["id"] for row in rows]
        self.assertEqual([row["amount"] for row in rows], [values[0], values[1], values[2], "0", "12.5"])
        for edit in (False, True):
            if edit:
                payload["name"] = "Synthetic recipe renamed without amount edits"
                rows[0]["note"] = "Synthetic note edit"
            saved = self.client.put(url, payload, format="json")
            self.assertEqual(saved.status_code, 200, saved.content)
            with scopes_disabled():
                persisted = list(Recipe.objects.get(pk=created.data["id"]).steps.get().ingredients.order_by("pk"))
                self.assertEqual([row.pk for row in persisted], ids)
                self.assertEqual([row.amount for row in persisted], expected)
            self.assertEqual([row["amount"] for row in self.client.get(url).json()["steps"][0]["ingredients"]],
                             [values[0], values[1], values[2], "0", "12.5"])

    def test_native_recipe_put_normalizes_comma_and_rejects_invalid_edits_atomically(self):
        created = self.client.post("/api/recipe/", self.payload(["1", "2"]), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        url = f"/api/recipe/{created.data['id']}/"
        payload = self.client.get(url).json()
        payload["steps"][0]["ingredients"][0]["amount"] = " 400,5000000000000001 "
        saved = self.client.put(url, payload, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        payload = self.client.get(url).json()
        self.assertEqual(payload["steps"][0]["ingredients"][0]["amount"], "400.5000000000000001")
        for invalid in ("NaN", "10000000000000000", "0.12345678901234567", ""):
            with self.subTest(invalid=invalid):
                before = self.counts()
                payload["name"] = "Invalid edit must not change recipe"
                payload["steps"][0]["ingredients"][0]["amount"] = "3"
                payload["steps"][0]["ingredients"][1]["amount"] = invalid
                rejected = self.client.put(url, payload, format="json")
                self.assert_amount_error(rejected)
                self.assertEqual(self.counts(), before)
                unchanged = self.client.get(url).json()
                self.assertEqual(unchanged["name"], "Synthetic precision recipe")
                self.assertEqual([row["amount"] for row in unchanged["steps"][0]["ingredients"]], ["400.5000000000000001", "2"])
