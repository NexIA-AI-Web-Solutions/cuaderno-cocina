from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Space, Unit, UserSpace
from cuaderno.models import PackageFormat, PriceVersion


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PriceValidationTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Validación de precios")
            self.user = get_user_model().objects.create_user(
                username="price-validation-user", password="local-test-only"
            )
            membership = UserSpace.objects.create(user=self.user, space=self.space, active=True)
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.space.created_by = self.user
            self.space.save(update_fields=["created_by"])
            self.food = Food.objects.create(space=self.space, name="Harina")
            self.unit = Unit.objects.create(space=self.space, name="kg")
            self.package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.unit,
                label="Saco existente",
                quantity="1",
                is_reference=True,
            )

            other_space = Space.objects.create(name="Otro espacio", created_by=self.user)
            self.other_food = Food.objects.create(space=other_space, name="Harina ajena")
            self.other_unit = Unit.objects.create(space=other_space, name="kg ajeno")
            self.other_package = PackageFormat.objects.create(
                space=other_space,
                food=self.other_food,
                unit=self.other_unit,
                label="Formato ajeno",
                quantity="1",
            )

        self.client = APIClient()
        self.client.force_login(self.user)
        self.client.raise_request_exception = False

    def package_payload(self, **overrides):
        payload = {
            "food": self.food.pk,
            "unit": self.unit.pk,
            "label": "Bolsa nueva",
            "quantity": "1",
        }
        payload.update(overrides)
        return payload

    def assert_package_rejected(self, payload, status=400):
        with scopes_disabled():
            packages_before = PackageFormat.objects.count()
            prices_before = PriceVersion.objects.count()
        response = self.client.post("/api/cuaderno/packages/", payload, format="json")
        self.assertEqual(response.status_code, status, getattr(response, "data", response.content))
        with scopes_disabled():
            self.assertEqual(PackageFormat.objects.count(), packages_before)
            self.assertEqual(PriceVersion.objects.count(), prices_before)

    def assert_price_rejected(self, payload, status=400, package=None):
        target = package or self.package
        with scopes_disabled():
            prices_before = PriceVersion.objects.count()
        response = self.client.post(f"/api/cuaderno/packages/{target.pk}/prices/", payload, format="json")
        self.assertEqual(response.status_code, status, getattr(response, "data", response.content))
        with scopes_disabled():
            self.assertEqual(PriceVersion.objects.count(), prices_before)

    def test_explicit_free_requires_a_json_boolean_on_both_write_routes(self):
        for value in (None, "true", "false", "0", "yes", 0, 1, [], {}):
            with self.subTest(route="package", value=value):
                self.assert_package_rejected(
                    self.package_payload(price="2.50", explicit_free=value)
                )
            with self.subTest(route="price", value=value):
                self.assert_price_rejected({"amount": "2.50", "explicit_free": value})

    def test_free_flag_and_amount_must_be_equivalent_and_omission_defaults_false(self):
        valid_packages = (
            {"price": "2.50"},
            {"price": "2.50", "explicit_free": False},
            {"price": "0", "explicit_free": True},
        )
        for index, values in enumerate(valid_packages):
            with self.subTest(route="package", values=values):
                response = self.client.post(
                    "/api/cuaderno/packages/",
                    self.package_payload(label=f"Formato válido {index}", **values),
                    format="json",
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["current_price"]["explicit_free"], values.get("explicit_free", False))

        valid_prices = (
            {"amount": "2.50"},
            {"amount": "2.50", "explicit_free": False},
            {"amount": "0", "explicit_free": True},
        )
        for values in valid_prices:
            with self.subTest(route="price", values=values):
                response = self.client.post(
                    f"/api/cuaderno/packages/{self.package.pk}/prices/", values, format="json"
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["explicit_free"], values.get("explicit_free", False))

        for values in ({"price": "2.50", "explicit_free": True}, {"price": "0"}, {"price": "0", "explicit_free": False}):
            with self.subTest(route="package-invalid", values=values):
                self.assert_package_rejected(self.package_payload(**values))
        for values in ({"amount": "2.50", "explicit_free": True}, {"amount": "0"}, {"amount": "0", "explicit_free": False}):
            with self.subTest(route="price-invalid", values=values):
                self.assert_price_rejected(values)

    def test_package_label_is_non_blank_text_bounded_to_model_length(self):
        for label in (None, "", "   ", True, 7, [], ["x"], {}, {"x": 1}, "x" * 129):
            with self.subTest(label=label):
                self.assert_package_rejected(self.package_payload(label=label))

        response = self.client.post(
            "/api/cuaderno/packages/", self.package_payload(label="x" * 128), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["label"]), 128)

    def test_food_and_unit_require_positive_integer_ids_and_preserve_space_scope(self):
        invalid_values = (None, True, False, 0, -1, "1", "abc", [], {})
        for field in ("food", "unit"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    self.assert_package_rejected(self.package_payload(**{field: value}))

        for field, value in (("food", self.other_food.pk), ("unit", self.other_unit.pk)):
            with self.subTest(field=field, kind="cross-space"):
                self.assert_package_rejected(self.package_payload(**{field: value}), status=404)
        for field in ("food", "unit"):
            with self.subTest(field=field, kind="missing"):
                self.assert_package_rejected(self.package_payload(**{field: 2_147_483_647}), status=404)

        self.assert_price_rejected(
            {"amount": "1", "explicit_free": False}, status=404, package=self.other_package
        )
        response = self.client.post(
            "/api/cuaderno/packages/2147483647/prices/",
            {"amount": "1", "explicit_free": False},
            format="json",
        )
        self.assertEqual(response.status_code, 404, getattr(response, "data", response.content))

    def test_decimal_limits_are_exact_without_rounding_and_json_floats_are_rejected(self):
        exact = "1234567890123456.1234567890123456"
        response = self.client.post(
            "/api/cuaderno/packages/",
            self.package_payload(label="Precisión exacta", quantity=exact, price=exact),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity"], exact)
        self.assertEqual(response.data["current_price"]["amount"], exact)

        integer_response = self.client.post(
            "/api/cuaderno/packages/",
            self.package_payload(label="Enteros JSON", quantity=2, price=3),
            format="json",
        )
        self.assertEqual(integer_response.status_code, 201, integer_response.data)
        self.assertEqual(Decimal(integer_response.data["quantity"]), Decimal("2"))
        self.assertEqual(Decimal(integer_response.data["current_price"]["amount"]), Decimal("3"))

        for value in (1.25, "12345678901234567.1234567890123456", "1.12345678901234567"):
            with self.subTest(field="quantity", value=value):
                self.assert_package_rejected(self.package_payload(quantity=value))
            with self.subTest(field="price", value=value):
                self.assert_price_rejected({"amount": value, "explicit_free": False})

    def test_omitting_price_keeps_unknown_distinct_from_free(self):
        response = self.client.post(
            "/api/cuaderno/packages/", self.package_payload(label="Sin precio"), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["current_price"])
        with scopes_disabled():
            self.assertFalse(PriceVersion.objects.filter(package_id=response.data["id"]).exists())

    def test_database_rejects_free_flag_inconsistent_with_amount(self):
        for amount, flag in (("2", True), ("0", False), ("-1", False)):
            with self.subTest(amount=amount, flag=flag), scopes_disabled():
                with self.assertRaises(IntegrityError), transaction.atomic():
                    PriceVersion.objects.create(
                        space=self.space, package=self.package, amount=amount,
                        explicit_free=flag, valid_from=timezone.now(), created_by=self.user,
                    )

    def test_portable_price_import_rejects_inconsistent_flag_before_any_write(self):
        for amount, flag in (("2", True), ("0", False)):
            with self.subTest(amount=amount, flag=flag):
                document = {
                    "format": "cuaderno-recipes-v2", "source": "price-validation",
                    "recipes": [{"external_id": "synthetic", "name": "Synthetic import", "servings": "1", "steps": []}],
                    "catalog": {
                        "foods": [{"ref": "f", "name": "Synthetic imported flour"}],
                        "units": [{"ref": "u", "name": "Synthetic unit"}],
                        "packages": [{
                            "ref": "p", "food_ref": "f", "unit_ref": "u", "label": "Synthetic pack",
                            "quantity": "1", "is_reference": True,
                            "prices": [{"amount": amount, "explicit_free": flag, "valid_from": "2026-01-01T00:00:00Z"}],
                        }],
                    },
                }
                from cookbook.models import Recipe
                from cuaderno.models import RecipeExchangeRecord
                models = (Recipe, RecipeExchangeRecord, Food, Unit, PackageFormat, PriceVersion)
                with scopes_disabled():
                    before = [model.objects.count() for model in models]
                response = self.client.post("/api/cuaderno/exchange/", document, format="json")
                self.assertEqual(response.status_code, 400, getattr(response, "data", response.content))
                with scopes_disabled():
                    self.assertEqual([model.objects.count() for model in models], before)
