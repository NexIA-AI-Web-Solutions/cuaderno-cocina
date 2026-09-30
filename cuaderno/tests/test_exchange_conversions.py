"""Portable exchange preserves native global and food-specific conversions."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Ingredient, Recipe, Space, Step, Unit, UnitConversion, UserSpace
from cuaderno.models import PackageFormat, PriceVersion, RecipeYield
from cuaderno.services.costing import cost_recipe


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExchangeConversionTests(TestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.source = Space.objects.create(name="Origen conversiones")
            self.target = Space.objects.create(name="Destino conversiones")
            self.users = []
            for index, space in enumerate((self.source, self.target)):
                user = get_user_model().objects.create_user(
                    username=f"exchange-conversion-{index}", password="local-test"
                )
                membership = UserSpace.objects.create(user=user, space=space, active=True)
                membership.groups.add(Group.objects.get_or_create(name="user")[0])
                self.users.append(user)

            self.grams = Unit.objects.create(name="g", base_unit="g", space=self.source)
            self.millilitres = Unit.objects.create(name="mL", base_unit="ml", space=self.source)
            self.litres = Unit.objects.create(name="L", base_unit="l", space=self.source)
            oil = Food.add_root(name="Aceite sintético", space=self.source)
            package = PackageFormat.objects.create(
                space=self.source,
                food=oil,
                unit=self.litres,
                label="Garrafa 5 L",
                quantity=Decimal("5"),
                is_reference=True,
            )
            PriceVersion.objects.create(
                space=self.source,
                package=package,
                amount=Decimal("32"),
                valid_from=timezone.now(),
                created_by=self.users[0],
            )

            child = Recipe.objects.create(
                name="Base de aceite", servings=1, created_by=self.users[0], space=self.source
            )
            child_step = Step.objects.create(space=self.source, instruction="Mezclar")
            child_step.ingredients.add(
                Ingredient.objects.create(
                    space=self.source,
                    food=oil,
                    unit=self.millilitres,
                    amount=Decimal("400"),
                )
            )
            child.steps.add(child_step)
            RecipeYield.objects.create(
                space=self.source,
                recipe=child,
                unit=self.grams,
                quantity=Decimal("368"),
                updated_by=self.users[0],
            )
            self.linked_food = Food.add_root(
                name="Base elaborada", recipe=child, space=self.source
            )
            self.specific = UnitConversion.objects.create(
                space=self.source,
                food=self.linked_food,
                base_amount=Decimal("920"),
                base_unit=self.grams,
                converted_amount=Decimal("1000"),
                converted_unit=self.millilitres,
                created_by=self.users[0],
            )
            self.global_conversion = UnitConversion.objects.create(
                space=self.source,
                food=None,
                base_amount=Decimal("1000"),
                base_unit=self.millilitres,
                converted_amount=Decimal("1"),
                converted_unit=self.litres,
                created_by=self.users[0],
            )
            self.parent = Recipe.objects.create(
                name="Plato con conversión", servings=1, created_by=self.users[0], space=self.source
            )
            parent_step = Step.objects.create(space=self.source, instruction="Usar base")
            parent_step.ingredients.add(
                Ingredient.objects.create(
                    space=self.source,
                    food=self.linked_food,
                    unit=self.millilitres,
                    amount=Decimal("400"),
                )
            )
            self.parent.steps.add(parent_step)

            hidden_owner = get_user_model().objects.create_user(username="exchange-hidden-owner")
            hidden = Recipe.objects.create(
                name="Receta privada ajena",
                servings=1,
                private=True,
                created_by=hidden_owner,
                space=self.source,
            )
            hidden_food = Food.add_root(name="Alimento privado", recipe=hidden, space=self.source)
            self.hidden_conversion = UnitConversion.objects.create(
                space=self.source,
                food=hidden_food,
                base_amount=Decimal("1"),
                base_unit=self.grams,
                converted_amount=Decimal("2"),
                converted_unit=self.millilitres,
                created_by=self.users[0],
            )

            foreign_space = Space.objects.create(name="Espacio ajeno conversiones")
            target_grams = Unit.objects.create(name="g ajeno", base_unit="g", space=foreign_space)
            target_millilitres = Unit.objects.create(name="mL ajeno", base_unit="ml", space=foreign_space)
            self.foreign_conversion = UnitConversion.objects.create(
                space=foreign_space,
                food=None,
                base_amount=Decimal("1"),
                base_unit=target_grams,
                converted_amount=Decimal("1"),
                converted_unit=target_millilitres,
                created_by=self.users[0],
            )

        self.source_client = APIClient()
        self.source_client.force_login(self.users[0])
        self.target_client = APIClient()
        self.target_client.force_login(self.users[1])

    def export_payload(self):
        response = self.source_client.get("/api/cuaderno/exchange/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def assert_target_has_no_import_writes(self):
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
            self.assertFalse(Food.objects.filter(space=self.target).exists())
            self.assertFalse(Unit.objects.filter(space=self.target).exists())
            self.assertFalse(PackageFormat.objects.filter(space=self.target).exists())
            self.assertFalse(PriceVersion.objects.filter(space=self.target).exists())
            self.assertFalse(RecipeYield.objects.filter(space=self.target).exists())
            self.assertFalse(UnitConversion.objects.filter(space=self.target).exists())

    def test_export_contains_only_reachable_global_and_food_specific_conversions(self):
        payload = self.export_payload()
        conversions = payload["catalog"]["conversions"]
        self.assertEqual(len(conversions), 2)
        self.assertTrue(all(isinstance(row["ref"], str) and row["ref"] for row in conversions))

        specific = next(row for row in conversions if row["food_ref"] is not None)
        global_row = next(row for row in conversions if row["food_ref"] is None)
        foods = {row["ref"]: row for row in payload["catalog"]["foods"]}
        units = {row["ref"]: row for row in payload["catalog"]["units"]}
        self.assertEqual(foods[specific["food_ref"]]["name"], "Base elaborada")
        self.assertEqual(units[specific["base_unit_ref"]]["name"], "g")
        self.assertEqual(units[specific["converted_unit_ref"]]["name"], "mL")
        self.assertEqual(Decimal(specific["base_amount"]), Decimal("920"))
        self.assertEqual(Decimal(specific["converted_amount"]), Decimal("1000"))
        self.assertEqual(units[global_row["base_unit_ref"]]["name"], "mL")
        self.assertEqual(units[global_row["converted_unit_ref"]]["name"], "L")
        self.assertNotIn(f"conversion:{self.hidden_conversion.pk}", {row["ref"] for row in conversions})

    def test_round_trip_preserves_conversions_and_exact_cost_then_replays_once(self):
        with scopes_disabled():
            before = cost_recipe(self.parent, "1", user=self.users[0])
        self.assertEqual(before["status"], "complete")
        self.assertEqual(Decimal(before["total"]), Decimal("2.56"))

        payload = self.export_payload()
        first = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        with scopes_disabled():
            restored = Recipe.objects.get(space=self.target, name="Plato con conversión")
            rows = list(UnitConversion.objects.filter(space=self.target))
            self.assertEqual(len(rows), 2)
            specific = next(row for row in rows if row.food_id is not None)
            self.assertEqual(specific.food.name, "Base elaborada")
            self.assertEqual(specific.base_amount, Decimal("920"))
            self.assertEqual(specific.converted_amount, Decimal("1000"))
            after = cost_recipe(restored, "1", user=self.users[1])
            self.assertEqual(after["status"], "complete")
            self.assertEqual(Decimal(after["total"]), Decimal("2.56"))

        replay = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data["created"], [])
        with scopes_disabled():
            self.assertEqual(UnitConversion.objects.filter(space=self.target).count(), 2)

    def test_preview_validates_conversions_without_writes(self):
        response = self.target_client.post(
            "/api/cuaderno/exchange/?preview=1", self.export_payload(), format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["writes"], 0)
        self.assert_target_has_no_import_writes()

    def test_missing_conversion_catalog_is_backward_compatible(self):
        payload = self.export_payload()
        payload["catalog"].pop("conversions")
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            self.assertFalse(UnitConversion.objects.filter(space=self.target).exists())

    def test_invalid_conversion_reference_rejects_every_write(self):
        payload = self.export_payload()
        payload["catalog"]["conversions"][0]["base_unit_ref"] = "unit:missing"
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assert_target_has_no_import_writes()

    def test_foreign_conversion_mapping_returns_404_without_writes(self):
        payload = self.export_payload()
        conversion_ref = payload["catalog"]["conversions"][0]["ref"]
        payload["mapping"] = {"conversions": {conversion_ref: self.foreign_conversion.pk}}
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 404, response.data)
        self.assert_target_has_no_import_writes()

    def test_mapped_conversion_with_different_ratio_returns_409_without_preview_writes(self):
        payload = self.export_payload()
        global_row = next(row for row in payload["catalog"]["conversions"] if row["food_ref"] is None)
        units = {row["ref"]: row for row in payload["catalog"]["units"]}
        with scopes_disabled():
            mapped_units = {}
            for ref in (global_row["base_unit_ref"], global_row["converted_unit_ref"]):
                source = units[ref]
                mapped_units[ref] = Unit.objects.create(
                    space=self.target,
                    name=source["name"],
                    base_unit=source["base_unit"],
                    plural_name=source["plural_name"],
                    description=source["description"],
                )
            conflicting = UnitConversion.objects.create(
                space=self.target,
                food=None,
                base_amount=Decimal("1000"),
                base_unit=mapped_units[global_row["base_unit_ref"]],
                converted_amount=Decimal("2"),
                converted_unit=mapped_units[global_row["converted_unit_ref"]],
                created_by=self.users[1],
            )
            before = {
                model.__name__: model.objects.filter(space=self.target).count()
                for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)
            }
        payload["mapping"] = {
            "units": {ref: row.pk for ref, row in mapped_units.items()},
            "conversions": {global_row["ref"]: conflicting.pk},
        }

        response = self.target_client.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        with scopes_disabled():
            after = {
                model.__name__: model.objects.filter(space=self.target).count()
                for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)
            }
        self.assertEqual(after, before)

    def test_conversion_decimal_limits_are_exact_and_never_rounded(self):
        valid = self.export_payload()
        valid_row = valid["catalog"]["conversions"][0]
        valid_row["base_amount"] = "9999999999999999.1234567890123456"
        valid_row["converted_amount"] = "0.0000000000000001"
        response = self.target_client.post("/api/cuaderno/exchange/?preview=1", valid, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_target_has_no_import_writes()

        for invalid in (
            "10000000000000000",
            "1.12345678901234567",
            "0",
            "-1",
            "NaN",
            "Infinity",
        ):
            with self.subTest(invalid=invalid):
                payload = self.export_payload()
                payload["catalog"]["conversions"][0]["base_amount"] = invalid
                response = self.target_client.post(
                    "/api/cuaderno/exchange/?preview=1", payload, format="json"
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assert_target_has_no_import_writes()

    def test_native_parallel_and_reverse_edges_keep_identity_order_and_cost(self):
        # Native uniqueness is directed and excludes NULL food duplicates on
        # PostgreSQL. First PK wins; retain every legal native identity.
        with scopes_disabled():
            duplicate = UnitConversion.objects.create(
                space=self.source, food=None,
                base_amount=Decimal("1000"), base_unit=self.millilitres,
                converted_amount=Decimal("1"), converted_unit=self.litres,
                created_by=self.users[0],
            )
            reverse = UnitConversion.objects.create(
                space=self.source, food=self.linked_food,
                base_amount=Decimal("1000"), base_unit=self.millilitres,
                converted_amount=Decimal("1840"), converted_unit=self.grams,
                created_by=self.users[0],
            )
        payload = self.export_payload()
        self.assertEqual(
            [row["id"] for row in payload["catalog"]["conversions"]],
            [self.specific.pk, self.global_conversion.pk, duplicate.pk, reverse.pk],
        )
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            rows = list(UnitConversion.objects.filter(space=self.target).order_by("pk"))
            self.assertEqual(len(rows), 4)
            self.assertEqual(
                [(row.base_amount, row.converted_amount) for row in rows],
                [(Decimal("920"), Decimal("1000")), (Decimal("1000"), Decimal("1")),
                 (Decimal("1000"), Decimal("1")), (Decimal("1000"), Decimal("1840"))],
            )
            restored = Recipe.objects.get(space=self.target, name="Plato con conversión")
            result = cost_recipe(restored, "1", user=self.users[1])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(Decimal(result["total"]), Decimal("2.56"))
        replay = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data["created"], [])
        with scopes_disabled():
            self.assertEqual(UnitConversion.objects.filter(space=self.target).count(), 4)

    def test_conversion_full_storage_precision_survives_database_round_trip(self):
        payload = self.export_payload()
        row = payload["catalog"]["conversions"][0]
        row["base_amount"] = "9999999999999999.1234567890123456"
        row["converted_amount"] = "0.0000000000000001"
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            restored = UnitConversion.objects.get(space=self.target, food__isnull=False)
            self.assertEqual(restored.base_amount, Decimal(row["base_amount"]))
            self.assertEqual(restored.converted_amount, Decimal(row["converted_amount"]))
        exported = self.target_client.get("/api/cuaderno/exchange/")
        self.assertEqual(exported.status_code, 200, exported.content)
        restored_row = next(row for row in exported.json()["catalog"]["conversions"] if row["food_ref"] is not None)
        self.assertEqual(Decimal(restored_row["base_amount"]), restored.base_amount)
        self.assertEqual(Decimal(restored_row["converted_amount"]), restored.converted_amount)

    def test_native_self_edge_is_portable_without_changing_cost(self):
        with scopes_disabled():
            UnitConversion.objects.create(
                space=self.source, food=None,
                base_amount=Decimal("1"), base_unit=self.grams,
                converted_amount=Decimal("1"), converted_unit=self.grams,
                created_by=self.users[0],
            )
        payload = self.export_payload()
        self.assertEqual(len(payload["catalog"]["conversions"]), 3)
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            self.assertEqual(UnitConversion.objects.filter(space=self.target).count(), 3)
            restored = Recipe.objects.get(space=self.target, name="Plato con conversión")
            self.assertEqual(Decimal(cost_recipe(restored, "1", user=self.users[1])["total"]), Decimal("2.56"))

    def test_duplicate_directed_food_edge_rejects_before_any_write(self):
        payload = self.export_payload()
        specific = next(row for row in payload["catalog"]["conversions"] if row["food_ref"] is not None)
        payload["catalog"]["conversions"].append({**specific, "ref": "conversion:duplicate", "id": 999999})
        response = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assert_target_has_no_import_writes()

    def test_existing_global_edge_requires_mapping_then_reuses_exact_identity(self):
        payload = self.export_payload()
        global_row = next(row for row in payload["catalog"]["conversions"] if row["food_ref"] is None)
        units = {row["ref"]: row for row in payload["catalog"]["units"]}
        with scopes_disabled():
            mapped_units = {}
            for ref in (global_row["base_unit_ref"], global_row["converted_unit_ref"]):
                source = units[ref]
                mapped_units[ref] = Unit.objects.create(
                    space=self.target, name=source["name"], base_unit=source["base_unit"],
                    plural_name=source["plural_name"], description=source["description"],
                )
            existing = UnitConversion.objects.create(
                space=self.target, food=None,
                base_amount=Decimal("1000"), base_unit=mapped_units[global_row["base_unit_ref"]],
                converted_amount=Decimal("1"), converted_unit=mapped_units[global_row["converted_unit_ref"]],
                created_by=self.users[1],
            )
        payload["mapping"] = {"units": {ref: row.pk for ref, row in mapped_units.items()}}
        rejected = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertIn("mapping_required", rejected.data)
        with scopes_disabled():
            self.assertFalse(Recipe.objects.filter(space=self.target).exists())
            self.assertFalse(Food.objects.filter(space=self.target).exists())
            self.assertEqual(Unit.objects.filter(space=self.target).count(), 2)
            self.assertEqual(UnitConversion.objects.filter(space=self.target).count(), 1)
        payload["mapping"]["conversions"] = {global_row["ref"]: existing.pk}
        preview = self.target_client.post("/api/cuaderno/exchange/?preview=1", payload, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["writes"], 0)
        payload["preview_sha256"] = preview.data["preview_sha256"]
        imported = self.target_client.post("/api/cuaderno/exchange/", payload, format="json")
        self.assertEqual(imported.status_code, 201, imported.data)
        with scopes_disabled():
            self.assertEqual(UnitConversion.objects.filter(space=self.target).count(), 2)
            existing.refresh_from_db()
            self.assertEqual(existing.base_amount, Decimal("1000"))
            self.assertEqual(existing.converted_amount, Decimal("1"))
            restored = Recipe.objects.get(space=self.target, name="Plato con conversión")
            self.assertEqual(Decimal(cost_recipe(restored, "1", user=self.users[1])["total"]), Decimal("2.56"))

    def test_export_rejects_corrupt_cross_space_unit_without_exposing_its_name(self):
        with scopes_disabled():
            foreign_unit = self.foreign_conversion.base_unit
            UnitConversion.objects.create(
                space=self.source, food=None,
                base_amount=Decimal("1"), base_unit=self.grams,
                converted_amount=Decimal("1"), converted_unit=foreign_unit,
                created_by=self.users[0],
            )
        response = self.source_client.get("/api/cuaderno/exchange/")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertNotIn(foreign_unit.name, str(response.data))
        self.assert_target_has_no_import_writes()

    def test_native_conversion_lookup_omits_private_recipe_and_retrieval_returns_404(self):
        response = self.source_client.get("/api/unit-conversion/")
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.specific.pk, ids)
        self.assertIn(self.global_conversion.pk, ids)
        self.assertNotIn(self.hidden_conversion.pk, ids)
        self.assertNotIn(self.foreign_conversion.pk, ids)
        hidden = self.source_client.get(f"/api/unit-conversion/{self.hidden_conversion.pk}/")
        self.assertEqual(hidden.status_code, 404, hidden.data)

    def test_native_conversion_lookup_allows_shared_and_owned_private_recipe(self):
        with scopes_disabled():
            child = self.linked_food.recipe
            child.private = True
            child.save(update_fields=["private"])
            shared = self.hidden_conversion.food.recipe
            shared.shared.add(self.users[0])
        for row in (self.specific, self.hidden_conversion, self.global_conversion):
            with self.subTest(conversion=row.pk):
                response = self.source_client.get(f"/api/unit-conversion/{row.pk}/")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["id"], row.pk)
        response = self.source_client.get("/api/unit-conversion/", {"food_id": self.hidden_conversion.food_id})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data["results"]], [self.hidden_conversion.pk])
        with scopes_disabled():
            shared.shared.remove(self.users[0])
        revoked = self.source_client.get(f"/api/unit-conversion/{self.hidden_conversion.pk}/")
        self.assertEqual(revoked.status_code, 404, revoked.data)

    def test_mapping_reversed_destination_priority_rejects_atomically(self):
        with scopes_disabled():
            self.linked_food.recipe = None
            self.linked_food.save(update_fields=["recipe"])
            package = PackageFormat.objects.create(
                space=self.source, food=self.linked_food, unit=self.grams,
                label="Saco sintético 5000 g", quantity=Decimal("5000"), is_reference=True,
            )
            PriceVersion.objects.create(
                space=self.source, package=package, amount=Decimal("32"),
                valid_from=timezone.now(), created_by=self.users[0],
            )
            reverse = UnitConversion.objects.create(
                space=self.source, food=self.linked_food,
                base_amount=Decimal("1000"), base_unit=self.millilitres,
                converted_amount=Decimal("1840"), converted_unit=self.grams,
                created_by=self.users[0],
            )
            from cuaderno.services.subrecipes import convert_native_quantity
            # Native graph quantity oracle: 400 mL * 920 g / 1000 mL = 368 g.
            # Ordinary-food cost does not yet use this density graph; this
            # check characterizes the shared conversion consumer, not a sheet.
            before_quantity = convert_native_quantity(
                Decimal("400"), self.millilitres, self.grams, self.linked_food, self.source,
            )
            self.assertEqual(before_quantity, Decimal("368"))
        payload = self.export_payload()
        source_units = {row["ref"]: row for row in payload["catalog"]["units"]}
        with scopes_disabled():
            mapped_units = {}
            for ref in (f"unit:{self.grams.pk}", f"unit:{self.millilitres.pk}"):
                source = source_units[ref]
                mapped_units[ref] = Unit.objects.create(
                    space=self.target, name=source["name"], base_unit=source["base_unit"],
                    plural_name=source["plural_name"], description=source["description"],
                )
            food = Food.add_root(space=self.target, name=self.linked_food.name)
            dest_reverse = UnitConversion.objects.create(
                space=self.target, food=food,
                base_amount=Decimal("1000"), base_unit=mapped_units[f"unit:{self.millilitres.pk}"],
                converted_amount=Decimal("1840"), converted_unit=mapped_units[f"unit:{self.grams.pk}"],
                created_by=self.users[1],
            )
            dest_forward = UnitConversion.objects.create(
                space=self.target, food=food,
                base_amount=Decimal("920"), base_unit=mapped_units[f"unit:{self.grams.pk}"],
                converted_amount=Decimal("1000"), converted_unit=mapped_units[f"unit:{self.millilitres.pk}"],
                created_by=self.users[1],
            )
            before = {model.__name__: model.objects.filter(space=self.target).count()
                      for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)}
        payload["mapping"] = {
            "foods": {f"food:{self.linked_food.pk}": food.pk},
            "units": {ref: row.pk for ref, row in mapped_units.items()},
            "conversions": {f"conversion:{self.specific.pk}": dest_forward.pk,
                            f"conversion:{reverse.pk}": dest_reverse.pk},
        }
        for suffix in ("?preview=1", ""):
            response = self.target_client.post(f"/api/cuaderno/exchange/{suffix}", payload, format="json")
            self.assertEqual(response.status_code, 409, response.data)
            with scopes_disabled():
                after = {model.__name__: model.objects.filter(space=self.target).count()
                         for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)}
            self.assertEqual(after, before)

    def test_extra_destination_edge_cannot_change_the_imported_native_path(self):
        from cuaderno.services.subrecipes import convert_native_quantity
        with scopes_disabled():
            self.linked_food.recipe = None
            self.linked_food.save(update_fields=["recipe"])
            bridge = Unit.objects.create(space=self.source, name="Puente sintético", base_unit="ml")
            self.specific.converted_unit = bridge
            self.specific.save(update_fields=["converted_unit"])
            UnitConversion.objects.create(
                space=self.source, food=self.linked_food,
                base_amount=Decimal("1000"), base_unit=bridge,
                converted_amount=Decimal("1000"), converted_unit=self.millilitres,
                created_by=self.users[0],
            )
            self.assertEqual(convert_native_quantity(
                Decimal("400"), self.millilitres, self.grams, self.linked_food, self.source,
            ), Decimal("368"))
        payload = self.export_payload()
        source_units = {row["ref"]: row for row in payload["catalog"]["units"]}
        with scopes_disabled():
            mapped_units = {}
            for source_unit in (self.grams, self.millilitres, bridge):
                ref = f"unit:{source_unit.pk}"
                item = source_units[ref]
                mapped_units[ref] = Unit.objects.create(
                    space=self.target, name=item["name"], base_unit=item["base_unit"],
                    plural_name=item["plural_name"], description=item["description"],
                )
            food = Food.add_root(space=self.target, name=self.linked_food.name)
            UnitConversion.objects.create(
                space=self.target, food=food,
                base_amount=Decimal("1840"), base_unit=mapped_units[f"unit:{self.grams.pk}"],
                converted_amount=Decimal("1000"), converted_unit=mapped_units[f"unit:{self.millilitres.pk}"],
                created_by=self.users[1],
            )
            self.assertEqual(convert_native_quantity(
                Decimal("400"), mapped_units[f"unit:{self.millilitres.pk}"],
                mapped_units[f"unit:{self.grams.pk}"], food, self.target,
            ), Decimal("736"))
            before = {model.__name__: model.objects.filter(space=self.target).count()
                      for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)}
        payload["mapping"] = {
            "foods": {f"food:{self.linked_food.pk}": food.pk},
            "units": {ref: row.pk for ref, row in mapped_units.items()},
        }
        for suffix in ("?preview=1", ""):
            response = self.target_client.post(f"/api/cuaderno/exchange/{suffix}", payload, format="json")
            self.assertEqual(response.status_code, 409, response.data)
            with scopes_disabled():
                after = {model.__name__: model.objects.filter(space=self.target).count()
                         for model in (Recipe, Food, Unit, PackageFormat, PriceVersion, RecipeYield, UnitConversion)}
            self.assertEqual(after, before)
