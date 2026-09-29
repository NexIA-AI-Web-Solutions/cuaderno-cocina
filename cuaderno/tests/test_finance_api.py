"""Persist finance on native recipe properties, with synthetic PostgreSQL data."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Household, Ingredient, Recipe, Space, Step, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecipeFinanceApiTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Synthetic finance API")
            self.owner = get_user_model().objects.create_user(username="finance-api", password="synthetic-only")
            household = Household.objects.create(space=self.space, name="Synthetic team")
            member = UserSpace.objects.create(space=self.space, user=self.owner, household=household, active=True)
            member.groups.add(Group.objects.get_or_create(name="user")[0])
            self.other = get_user_model().objects.create_user(username="finance-other", password="synthetic-only")
            other_member = UserSpace.objects.create(space=self.space, user=self.other, household=household, active=True)
            other_member.groups.add(Group.objects.get_or_create(name="user")[0])
            SpaceProfile.objects.create(space=self.space, edition="profesional", price_policy="net")
            unit = Unit.objects.create(space=self.space, name="L")
            food = Food.add_root(space=self.space, name="Synthetic oil")
            self.package = PackageFormat.objects.create(space=self.space, food=food, unit=unit, quantity=5, label="Synthetic 5 L")
            PriceVersion.objects.create(space=self.space, package=self.package, amount=32, valid_from=timezone.now(), created_by=self.owner)
            self.recipe = Recipe.objects.create(space=self.space, created_by=self.owner, name="Synthetic recipe", private=True, servings=4)
            step = Step.objects.create(space=self.space)
            step.ingredients.add(Ingredient.objects.create(space=self.space, food=food, unit=unit, amount=Decimal("0.4")))
            self.recipe.steps.add(step)
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.url = f"/api/cuaderno/recipes/{self.recipe.pk}/finance/"

    def test_native_finance_persists_and_reports_exact_non_profit_indicators(self):
        response = self.client.put(self.url, {"selling_price_per_serving": "2,00", "budget_per_person": "1"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.get("Content-Type", "").startswith("application/json"), "Finance API is missing; HTML SPA fallback is not an API.")
        finance = response.data["finance"]
        self.assertEqual(Decimal(finance["ingredient_cost_per_serving"]), Decimal("0.64"))
        self.assertEqual(Decimal(finance["difference_per_serving"]), Decimal("1.36"))
        self.assertEqual(Decimal(finance["food_cost_ratio"]), Decimal("0.32"))
        self.assertEqual(Decimal(finance["budget_gap_per_person"]), Decimal("0.36"))
        self.assertEqual(finance["price_policy"], "net")
        self.assertIsNone(finance["net_profit"])
        persisted = self.client.get(self.url)
        self.assertEqual(persisted.data["finance"], finance)
        with scopes_disabled():
            self.assertEqual(self.recipe.properties.count(), 2)
        configured = self.client.put(self.url, {"selling_price_per_serving": "2", "budget_per_person": "1"}, format="json")
        self.assertEqual(configured.status_code, 200)
        self.assertTrue(configured.get("Content-Type", "").startswith("application/json"), "Finance API is missing; HTML SPA fallback is not an API.")
        with scopes_disabled():
            self.assertEqual(self.recipe.properties.count(), 2)

    def test_private_acl_and_zero_unknown_invalid_values(self):
        other = APIClient()
        other.force_login(self.other)
        self.assertEqual(other.get(self.url).status_code, 404)
        self.assertEqual(other.put(self.url, {"selling_price_per_serving": "1"}, format="json").status_code, 404)
        response = self.client.put(self.url, {"selling_price_per_serving": "0", "budget_per_person": None}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.data["finance"]["food_cost_ratio"])
        self.assertIsNone(response.data["finance"]["budget_per_person"])
        for invalid in ("-1", "NaN", "0.12345", "1e999"):
            with self.subTest(value=invalid):
                self.assertEqual(self.client.put(self.url, {"budget_per_person": invalid}, format="json").status_code, 400)
                unchanged = self.client.get(self.url).data["finance"]
                self.assertEqual(Decimal(unchanged["selling_price_per_serving"]), Decimal("0"))
                self.assertIsNone(unchanged["budget_per_person"])

    def test_confirmed_service_freezes_finance_and_price_policy(self):
        self.assertEqual(self.client.put(self.url, {"selling_price_per_serving": "2", "budget_per_person": "1"}, format="json").status_code, 200)
        created = self.client.post("/api/cuaderno/services/", {"recipe": self.recipe.pk, "covers": "4", "service_date": "2026-10-01", "title": "Synthetic service"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        plan_url = f"/api/cuaderno/services/{created.data['id']}/"
        confirmed = self.client.post(plan_url, {"action": "confirm"}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        frozen = confirmed.data["snapshot"]["finance"]
        self.assertEqual(Decimal(frozen["selling_price_per_serving"]), Decimal("2"))
        self.assertEqual(Decimal(frozen["ingredient_cost_per_serving"]), Decimal("0.64"))
        self.assertEqual(self.client.put(self.url, {"selling_price_per_serving": "9", "budget_per_person": "8"}, format="json").status_code, 200)
        with scopes_disabled():
            PriceVersion.objects.create(space=self.space, package=self.package, amount=35, valid_from=timezone.now(), created_by=self.owner)
            SpaceProfile.objects.filter(space=self.space).update(price_policy="gross")
        self.assertEqual(self.client.get(plan_url).data["snapshot"]["finance"], frozen)
        self.assertEqual(Decimal(self.client.get(self.url).data["finance"]["ingredient_cost_per_serving"]), Decimal("0.70"))
