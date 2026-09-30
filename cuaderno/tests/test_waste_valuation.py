from datetime import timedelta
from decimal import Decimal

from django.db.models import JSONField, Value
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError

from cookbook.models import Food, InventoryEntry, InventoryLocation, Space, Unit
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile, StockMovement
from cuaderno.services.ledger import apply_movement, reverse_movement
from cuaderno.services.stock_valuation import replacement_valuation
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WasteReplacementValuationTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.price_policy = SpaceProfile.NET
        self.profile.save(update_fields=["edition", "price_policy"])
        with scopes_disabled():
            self.location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Almacén de valoración",
                created_by=self.user,
            )
            self.entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.g,
                amount=Decimal("10000"),
                created_by=self.user,
            )

    def waste(self, quantity, key, *, entry=None):
        with scopes_disabled():
            return apply_movement(
                entry_id=(entry or self.entry).pk,
                space=self.space,
                user=self.user,
                kind=StockMovement.WASTE,
                quantity=quantity,
                idempotency_key=key,
                origin={"type": "standalone_waste", "cause": "preparación"},
            )

    def test_625_grams_freezes_1_25_eur_replacement_estimate(self):
        movement = self.waste("625", "valued-625g")

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["policy"], "replacement_estimate")
        self.assertEqual(valuation["status"], "complete")
        self.assertEqual(valuation["amount"], "1.25")
        self.assertEqual(valuation["currency"], "EUR")
        self.assertEqual(valuation["price_policy"], SpaceProfile.NET)
        self.assertEqual(valuation["input"], {
            "quantity": "625", "unit_id": self.g.pk, "unit_name": "g",
        })
        self.assertEqual(valuation["package"], {
            "id": self.package.pk,
            "label": "Saco 5 kg",
            "quantity": "5",
            "unit_id": self.kg.pk,
            "unit_name": "kg",
        })
        price = PriceVersion.objects.get(package=self.package)
        self.assertEqual(valuation["price_version"], {
            "id": price.pk,
            "amount": "10",
            "explicit_free": False,
            "valid_from": price.valid_from.isoformat(),
        })
        self.assertEqual(valuation["calculation"], {
            "quantity_in_package_unit": "0.625",
            "package_fraction": "0.125",
            "computed_amount": "1.25",
            "working_precision": 64,
            "rounding": "HALF_EVEN",
        })
        self.assertIsNone(valuation["reason"])
        self.assertEqual(timezone.datetime.fromisoformat(valuation["as_of"]).tzinfo is not None, True)

    def test_high_precision_quantity_is_not_rounded_before_valuation(self):
        with scopes_disabled():
            kilogram_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("1"),
                created_by=self.user,
            )

        movement = self.waste("0.0000000000000001", "valued-high-precision", entry=kilogram_entry)

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["amount"], "0.0000000000000002")
        self.assertEqual(valuation["calculation"]["quantity_in_package_unit"], "0.0000000000000001")

    def test_missing_price_is_unknown_not_zero_and_waste_still_posts(self):
        with scopes_disabled():
            PriceVersion.objects.filter(package=self.package).delete()

        movement = self.waste("625", "unknown-price")

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["status"], "unknown")
        self.assertIsNone(valuation["amount"])
        self.assertEqual(valuation["reason"], "price_missing")
        self.assertIsNone(valuation["price_version"])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("9375"))

    def test_missing_conversion_is_unknown_not_an_implicit_mass_conversion(self):
        with scopes_disabled():
            unknown_unit = Unit.objects.create(space=self.space, name="caja", base_unit="")
            boxed = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=unknown_unit,
                amount=Decimal("10"),
                created_by=self.user,
            )

        movement = self.waste("1", "unknown-conversion", entry=boxed)

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["status"], "unknown")
        self.assertIsNone(valuation["amount"])
        self.assertEqual(valuation["reason"], "conversion_missing")
        self.assertIsNotNone(valuation["package"])
        self.assertIsNotNone(valuation["price_version"])

    def test_explicitly_free_reference_price_is_complete_zero(self):
        with scopes_disabled():
            PriceVersion.objects.filter(package=self.package).delete()
            free = PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("0"),
                explicit_free=True,
                valid_from=timezone.now() - timedelta(minutes=1),
                created_by=self.admin,
            )

        movement = self.waste("625", "explicit-free-waste")

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["status"], "complete")
        self.assertEqual(valuation["amount"], "0")
        self.assertEqual(valuation["price_version"]["id"], free.pk)
        self.assertIs(valuation["price_version"]["explicit_free"], True)

    def test_future_price_is_not_selected(self):
        current = PriceVersion.objects.get(package=self.package)
        with scopes_disabled():
            PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("30"),
                valid_from=timezone.now() + timedelta(days=1),
                created_by=self.admin,
            )

        movement = self.waste("625", "ignore-future-price")

        valuation = movement.metadata_snapshot["valuation"]
        self.assertEqual(valuation["price_version"]["id"], current.pk)
        self.assertEqual(valuation["amount"], "1.25")

    def test_price_change_retry_and_reversal_do_not_rewrite_frozen_valuation(self):
        movement = self.waste("1000", "frozen-waste")
        frozen = movement.metadata_snapshot["valuation"]
        with scopes_disabled():
            PriceVersion.objects.create(
                space=self.space,
                package=self.package,
                amount=Decimal("20"),
                valid_from=timezone.now(),
                created_by=self.admin,
            )

        replay = self.waste("1000.0", "frozen-waste")
        with scopes_disabled():
            reversal = reverse_movement(
                movement_id=movement.pk,
                space=self.space,
                user=self.user,
                idempotency_key="reverse-frozen-waste",
            )

        self.assertEqual(replay.pk, movement.pk)
        self.assertEqual(replay.metadata_snapshot["valuation"], frozen)
        self.assertEqual(reversal.metadata_snapshot["valuation"], frozen)

    def test_cross_space_legacy_relations_are_unknown_without_foreign_valuation_details(self):
        with scopes_disabled():
            foreign_space = Space.objects.create(name="Valoración ajena", created_by=self.admin)
            foreign_food = Food.objects.create(space=foreign_space, name="Ingrediente secreto")
            foreign_unit = Unit.objects.create(space=foreign_space, name="unidad secreta", base_unit="kg")
            foreign_package = PackageFormat.objects.create(
                space=foreign_space,
                food=foreign_food,
                unit=foreign_unit,
                label="Formato secreto",
                quantity=Decimal("3"),
            )
            PriceVersion.objects.create(
                space=foreign_space,
                package=foreign_package,
                amount=Decimal("99"),
                valid_from=timezone.now() - timedelta(days=1),
                created_by=self.admin,
            )
            legacy_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=foreign_food,
                unit=foreign_unit,
                amount=Decimal("2"),
                created_by=self.user,
            )

            valuation = replacement_valuation(
                entry=legacy_entry,
                quantity=Decimal("1"),
                as_of=timezone.now(),
            )

        self.assertEqual(valuation["status"], "unknown")
        self.assertIsNone(valuation["amount"])
        self.assertEqual(valuation["reason"], "scope_mismatch")
        self.assertIsNone(valuation["package"])
        self.assertIsNone(valuation["price_version"])
        self.assertNotIn("Ingrediente secreto", str(valuation))
        self.assertNotIn("unidad secreta", str(valuation))
        self.assertNotIn("Formato secreto", str(valuation))

    def test_repeating_replacement_cost_declares_decimal64_half_even_computation(self):
        with scopes_disabled():
            self.package.quantity = Decimal("3")
            self.package.save(update_fields=["quantity"])
            price = PriceVersion.objects.get(package=self.package)
            price.amount = Decimal("1")
            price.save(update_fields=["amount"])
            kilogram_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=self.location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("2"),
                created_by=self.user,
            )

        movement = self.waste("1", "repeating-one-third", entry=kilogram_entry)

        calculation = movement.metadata_snapshot["valuation"]["calculation"]
        expected = "0.3333333333333333333333333333333333333333333333333333333333333333"
        self.assertEqual(calculation["computed_amount"], expected)
        self.assertEqual(movement.metadata_snapshot["valuation"]["amount"], expected)
        self.assertEqual(calculation["working_precision"], 64)
        self.assertEqual(calculation["rounding"], "HALF_EVEN")

    def test_malformed_movement_or_valuation_snapshot_cannot_be_reversed(self):
        malformed_snapshots = (
            "scalar",
            ["list"],
            Value(None, output_field=JSONField()),
            {"origin": {"type": "standalone_waste"}, "valuation": "scalar"},
            {"origin": {"type": "standalone_waste"}, "valuation": ["list"]},
        )
        for index, malformed in enumerate(malformed_snapshots):
            with self.subTest(index=index):
                movement = self.waste("1", f"malformed-snapshot-{index}")
                with scopes_disabled():
                    StockMovement.objects.filter(pk=movement.pk).update(metadata_snapshot=malformed)
                    self.entry.refresh_from_db()
                    balance = self.entry.amount
                    movement_count = StockMovement.objects.count()
                    with self.assertRaises(ValidationError):
                        reverse_movement(
                            movement_id=movement.pk,
                            space=self.space,
                            user=self.user,
                            idempotency_key=f"reject-malformed-{index}",
                        )
                    self.entry.refresh_from_db()
                    self.assertEqual(self.entry.amount, balance)
                    self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_legacy_waste_without_valuation_reverses_without_inventing_money(self):
        movement = self.waste("1", "legacy-without-valuation")
        with scopes_disabled():
            StockMovement.objects.filter(pk=movement.pk).update(
                metadata_snapshot={"origin": {"type": "standalone_waste", "cause": "legacy"}}
            )
            reversal = reverse_movement(
                movement_id=movement.pk,
                space=self.space,
                user=self.user,
                idempotency_key="reverse-legacy-without-valuation",
            )

        self.assertNotIn("valuation", reversal.metadata_snapshot)
