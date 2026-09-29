"""Portable exchange exercises the real native graph and exact persisted prices."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Ingredient, Recipe, Space, Step, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion, RecipeExchangeRecord, RecipeYield
from cuaderno.services.costing import cost_recipe


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PortableExchangeTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.source = Space.objects.create(name="Origen sintético")
            self.target = Space.objects.create(name="Destino sintético")
            self.users = []
            for index, space in enumerate((self.source, self.target)):
                user = get_user_model().objects.create_user(username=f"portable-{index}", password="local-test")
                membership = UserSpace.objects.create(user=user, space=space, active=True)
                membership.groups.add(Group.objects.get_or_create(name="user")[0])
                self.users.append(user)
            self.unit = Unit.objects.create(name="kg", space=self.source)
            raw = Food.add_root(name="Materia prima", space=self.source)
            package = PackageFormat.objects.create(space=self.source, food=raw, unit=self.unit, label="Bolsa", quantity=Decimal("1.25"))
            self.date = timezone.now()
            PriceVersion.objects.create(space=self.source, package=package, amount=Decimal("3.75"), valid_from=self.date, created_by=self.users[0], note="Precio sintético")
            child = Recipe.objects.create(name="Salsa", servings=4, created_by=self.users[0], space=self.source)
            step = Step.objects.create(space=self.source, instruction="Cocinar")
            step.ingredients.add(Ingredient.objects.create(space=self.source, food=raw, unit=self.unit, amount=Decimal("2")))
            child.steps.add(step)
            RecipeYield.objects.create(space=self.source, recipe=child, unit=self.unit, quantity=Decimal("2"), updated_by=self.users[0])
            linked = Food.add_root(name="Salsa elaborada", recipe=child, space=self.source)
            self.parent = Recipe.objects.create(name="Plato", servings=1, created_by=self.users[0], space=self.source)
            parent_step = Step.objects.create(space=self.source, instruction="Usar salsa")
            parent_step.ingredients.add(Ingredient.objects.create(space=self.source, food=linked, unit=self.unit, amount=Decimal("0.3")))
            self.parent.steps.add(parent_step)
            self.child = child
        self.client_source = APIClient()
        self.client_source.force_login(self.users[0])
        self.client_target = APIClient()
        self.client_target.force_login(self.users[1])

    def test_cross_space_round_trip_preserves_graph_yield_price_and_golden_cost(self):
        exported = self.client_source.get("/api/cuaderno/exchange/")
        self.assertEqual(exported.status_code, 200)
        payload = exported.json()
        preview = self.client_target.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
            self.assertFalse(Food.objects.filter(space=self.target).exists())
        payload["preview_sha256"] = preview.data["preview_sha256"]
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            restored = Recipe.objects.get(space=self.target, name="Plato")
            child = Recipe.objects.get(space=self.target, name="Salsa")
            linked = restored.steps.get().ingredients.get().food
            self.assertEqual(linked.recipe_id, child.pk)
            self.assertEqual(child.cuaderno_yield.quantity, Decimal("2"))
            price = PriceVersion.objects.get(space=self.target)
            self.assertEqual(price.amount, Decimal("3.75"))
            self.assertEqual(price.package.quantity, Decimal("1.25"))
            self.assertEqual(price.valid_from, self.date)
            self.assertEqual(Decimal(cost_recipe(restored, "1", user=self.users[1])["total"]), Decimal("0.90"))
        replay = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data["created"], [])
        with scopes_disabled():
            self.assertEqual(PriceVersion.objects.filter(space=self.target).count(), 1)

    def test_changed_mapping_after_preview_returns_409_without_writes(self):
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        preview = self.client_target.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        payload["preview_sha256"] = preview.data["preview_sha256"]
        payload["mapping"] = {"units": {"kg": 999999}}
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 409)
        with scopes_disabled():
            self.assertFalse(RecipeExchangeRecord.objects.filter(space=self.target).exists())

    def test_step_recipe_is_restored_by_external_identity(self):
        with scopes_disabled():
            step = Step.objects.create(space=self.source, instruction="Preparar salsa", step_recipe=self.child)
            self.parent.steps.add(step)
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            child = Recipe.objects.get(space=self.target, name="Salsa")
            parent = Recipe.objects.get(space=self.target, name="Plato")
            self.assertEqual(parent.steps.get(instruction="Preparar salsa").step_recipe_id, child.pk)

    def test_hidden_child_export_is_rejected_without_leaking_identity(self):
        with scopes_disabled():
            hidden_owner = get_user_model().objects.create_user(username="hidden-owner")
            self.child.private = True
            self.child.created_by = hidden_owner
            self.child.save(update_fields=["private", "created_by"])
        response = self.client_source.get("/api/cuaderno/exchange/")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Salsa", str(response.data))

    def test_cycle_rejects_all_writes(self):
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        child = next(row for row in payload["recipes"] if row["name"] == "Salsa")
        child["steps"][0]["step_recipe"] = child["external_id"]
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
            self.assertFalse(Food.objects.filter(space=self.target).exists())
            self.assertFalse(PackageFormat.objects.filter(space=self.target).exists())

    def test_changed_catalog_on_replay_returns_conflict_without_price_write(self):
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        first = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        payload["catalog"]["packages"][0]["prices"][0]["amount"] = "4.00"
        changed = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(changed.status_code, 409)
        with scopes_disabled():
            self.assertEqual(PriceVersion.objects.get(space=self.target).amount, Decimal("3.75"))
            self.assertEqual(Recipe.objects.filter(space=self.target).count(), 2)

    def test_conflicting_catalog_name_requires_mapping_during_preview(self):
        with scopes_disabled():
            Unit.objects.create(space=self.target, name="kg")
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        response = self.client_target.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("mapping_required", response.data)
        with scopes_disabled():
            self.assertFalse(Food.objects.filter(space=self.target).exists())

    def test_foreign_space_mapping_and_unsupported_fields_reject_without_writes(self):
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        payload["mapping"] = {"units": {payload["catalog"]["units"][0]["ref"]: self.unit.pk}}
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 404)
        payload.pop("mapping")
        payload["recipes"][0]["unknown_price_extension"] = "must not vanish"
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())

    def test_exact_price_precision_is_rejected_instead_of_rounded(self):
        payload = self.client_source.get("/api/cuaderno/exchange/").json()
        payload["catalog"]["packages"][0]["prices"][0]["amount"] = "3.12345678901234567"
        response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        with scopes_disabled():
            self.assertFalse(PriceVersion.objects.filter(space=self.target).exists())

    def test_duplicate_catalog_names_fail_preview_without_writes(self):
        for kind in ("foods", "units"):
            payload = self.client_source.get("/api/cuaderno/exchange/").json()
            payload["catalog"][kind].append({**payload["catalog"][kind][0], "ref": "duplicate-name"})
            response = self.client_target.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
            self.assertFalse(Food.objects.filter(space=self.target).exists())

    def test_v1_mapping_rejects_non_integer_ids_without_writes(self):
        for invalid in (True, "1", [1]):
            payload = {"recipes": [{"name": "Importación inválida", "ingredients": [{"food": "X", "quantity": "1", "unit": "kg"}]}],
                       "mapping": {"foods": {"X": invalid}}}
            response = self.client_target.post("/api/cuaderno/exchange/", payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
