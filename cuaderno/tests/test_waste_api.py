import hashlib
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Food, Household, InventoryEntry, InventoryLocation, InventoryLog, Space, Unit
from cuaderno.models import SpaceProfile, StockMovement
from cuaderno.services.ledger import apply_movement
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StandaloneWasteApiTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.price_policy = SpaceProfile.NET
        self.profile.save(update_fields=["edition", "price_policy"])
        with scopes_disabled():
            self.guest = self.make_user("waste-guest", "guest", self.household)
            self.location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Almacén de desperdicio",
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

    def payload(self, **changes):
        value = {
            "entry": self.entry.pk,
            "kind": StockMovement.WASTE,
            "quantity": "625",
            "cause": "Limpieza",
            "idempotency_key": "standalone-waste-api",
        }
        value.update(changes)
        return value

    def post(self, payload=None, *, user=None, client=None):
        return (client or self.client_for(user or self.user)).post(
            "/api/cuaderno/movements/",
            payload or self.payload(),
            format="json",
        )

    def test_waste_strips_cause_decrements_stock_and_freezes_replacement_value(self):
        response = self.post(self.payload(cause=" Limpieza "))

        self.assertEqual(response.status_code, 201, getattr(response, "data", response.content))
        self.entry.refresh_from_db()
        movement = StockMovement.objects.get(pk=response.data["movement_id"])
        self.assertEqual(self.entry.amount, Decimal("9375"))
        self.assertEqual(movement.metadata_snapshot["origin"], {
            "type": "standalone_waste", "cause": "Limpieza",
        })
        self.assertEqual(movement.metadata_snapshot["valuation"]["status"], "complete")
        self.assertEqual(movement.metadata_snapshot["valuation"]["amount"], "1.25")

    def test_same_canonical_payload_replays_once_but_changed_cause_conflicts(self):
        first = self.post(self.payload(cause=" Preparación "))
        replay = self.post(self.payload(cause="Preparación"))
        conflict = self.post(self.payload(cause="Caducidad"))

        self.assertEqual(first.status_code, 201, getattr(first, "data", first.content))
        self.assertEqual(replay.status_code, 201, getattr(replay, "data", replay.content))
        self.assertEqual(replay.data["movement_id"], first.data["movement_id"])
        self.assertEqual(conflict.status_code, 409, getattr(conflict, "data", conflict.content))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("9375"))
        self.assertEqual(StockMovement.objects.count(), 1)
        movement = StockMovement.objects.get(pk=first.data["movement_id"])
        canonical_origin = json.dumps(
            {"type": "standalone_waste", "cause": "Preparación"},
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertIn("Preparaci\\u00f3n", canonical_origin)
        expected_fingerprint = hashlib.sha256(
            (
                f"entry={self.entry.pk};kind=waste;quantity=625;reverses=;"
                f"origin={canonical_origin}"
            ).encode()
        ).hexdigest()
        self.assertEqual(movement.fingerprint, expected_fingerprint)
        with scopes_disabled():
            self.assertEqual(InventoryLog.objects.count(), 1)

    def test_invalid_causes_write_neither_ledger_nor_native_log(self):
        invalid = (
            ("missing", None, False),
            ("null", None, True),
            ("empty", "", True),
            ("whitespace", "   ", True),
            ("list", ["Limpieza"], True),
            ("integer", 7, True),
            ("nul", "limpieza\x00", True),
            ("trailing_newline", "limpieza\n", True),
            ("leading_c1", "\x85limpieza", True),
            ("embedded_c1", "limpieza\x85pendiente", True),
            ("unpaired_surrogate", "\ud800", True),
            ("too_long", "x" * 257, True),
        )
        for index, (label, cause, include) in enumerate(invalid):
            with self.subTest(cause=label):
                payload = self.payload(idempotency_key=f"invalid-cause-{index}")
                if not include:
                    payload.pop("cause")
                else:
                    payload["cause"] = cause
                if label == "unpaired_surrogate":
                    client = self.client_for(self.user)
                    response = client.generic(
                        "POST",
                        "/api/cuaderno/movements/",
                        data=json.dumps(payload, ensure_ascii=True).encode("ascii"),
                        content_type="application/json",
                    )
                else:
                    response = self.post(payload)
                self.assertEqual(response.status_code, 400, getattr(response, "data", response.content))

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("10000"))
        self.assertFalse(StockMovement.objects.exists())
        with scopes_disabled():
            self.assertFalse(InventoryLog.objects.exists())

    def test_256_unicode_codepoints_are_valid_and_replay_without_duplicate(self):
        cause = "🍳" * 256
        payload = self.payload(
            quantity="1",
            cause=cause,
            idempotency_key="unicode-cause-boundary",
        )

        first = self.post(payload)
        replay = self.post(payload)

        self.assertEqual(first.status_code, 201, getattr(first, "data", first.content))
        self.assertEqual(replay.status_code, 201, getattr(replay, "data", replay.content))
        self.assertEqual(replay.data["movement_id"], first.data["movement_id"])
        movement = StockMovement.objects.get(pk=first.data["movement_id"])
        self.assertEqual(movement.metadata_snapshot["origin"]["cause"], cause)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("9999"))

    @scopes_disabled()
    def test_legacy_waste_without_cause_can_only_replay_the_existing_payload(self):
        original = apply_movement(
            entry_id=self.entry.pk, space=self.space, user=self.user,
            kind=StockMovement.WASTE, quantity="625", idempotency_key="legacy-waste",
        )
        old_payload = self.payload(idempotency_key="legacy-waste")
        old_payload.pop("cause")

        replay = self.post(old_payload)
        conflict = self.post({**old_payload, "quantity": "626"})
        missing = self.post({**old_payload, "idempotency_key": "new-without-cause"})

        self.assertEqual(replay.status_code, 201, getattr(replay, "data", replay.content))
        self.assertEqual(replay.data["movement_id"], original.pk)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(missing.status_code, 400)
        self.assertNotIn("origin", replay.data["metadata_snapshot"])
        for ignored_cause in (None, "Campo ignorado por la API anterior"):
            with self.subTest(legacy_cause=ignored_cause):
                old_replay = self.post({**old_payload, "cause": ignored_cause})
                self.assertEqual(old_replay.status_code, 201)
                self.assertEqual(old_replay.data["movement_id"], original.pk)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("9375"))
        self.assertEqual(StockMovement.objects.count(), 1)
        with scopes_disabled():
            self.assertEqual(InventoryLog.objects.count(), 1)

    @scopes_disabled()
    def test_origin_size_cap_uses_utf8_bytes_and_rejects_overflow_before_writes(self):
        from rest_framework.exceptions import ValidationError

        overhead = len(b'{"note":""}')
        for label, note in (("ascii", "x" * (2048 - overhead)),
                            ("utf8", "é" * ((2048 - overhead) // 2) + "x")):
            with self.subTest(boundary=label):
                origin = {"note": note}
                self.assertEqual(len(json.dumps(origin, separators=(",", ":"), ensure_ascii=False).encode("utf-8")), 2048)
                movement = apply_movement(
                    entry_id=self.entry.pk, space=self.space, user=self.user,
                    kind=StockMovement.RECEIPT, quantity="1", idempotency_key=f"limit-{label}", origin=origin,
                )
                self.assertEqual(movement.metadata_snapshot["origin"], origin)
                with self.assertRaises(ValidationError) as failure:
                    apply_movement(
                        entry_id=self.entry.pk, space=self.space, user=self.user,
                        kind=StockMovement.RECEIPT, quantity="1", idempotency_key=f"overflow-{label}",
                        origin={"note": note + "x"},
                    )
                self.assertIn("origin", failure.exception.detail)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("10002"))
        self.assertEqual(StockMovement.objects.count(), 2)
        with scopes_disabled():
            self.assertEqual(InventoryLog.objects.count(), 2)

    @scopes_disabled()
    def test_legacy_replay_never_bypasses_modern_cause_or_a_different_kind(self):
        modern = self.post()
        self.assertEqual(modern.status_code, 201)
        no_cause = self.payload()
        no_cause.pop("cause")
        self.assertEqual(self.post(no_cause).status_code, 400)
        receipt = apply_movement(
            entry_id=self.entry.pk, space=self.space, user=self.user,
            kind=StockMovement.RECEIPT, quantity="1", idempotency_key="receipt-key",
        )
        conflict = self.post(self.payload(quantity="1", idempotency_key=receipt.idempotency_key))
        self.assertEqual(conflict.status_code, 409)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("9376"))
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(InventoryLog.objects.count(), 2)

    def test_entry_in_another_household_is_hidden_from_normal_user(self):
        with scopes_disabled():
            location = InventoryLocation.objects.create(
                space=self.space,
                household=self.other_household,
                name="Almacén de otro hogar",
                created_by=self.outsider,
            )
            foreign_household_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=location,
                food=self.food,
                unit=self.g,
                amount=Decimal("1000"),
                created_by=self.outsider,
            )

        response = self.post(self.payload(
            entry=foreign_household_entry.pk,
            idempotency_key="waste-other-household",
        ))

        self.assertEqual(response.status_code, 404)
        foreign_household_entry.refresh_from_db()
        self.assertEqual(foreign_household_entry.amount, Decimal("1000"))
        self.assertFalse(StockMovement.objects.exists())

    def test_entry_in_another_space_is_hidden(self):
        with scopes_disabled():
            other_space = Space.objects.create(name="Espacio ajeno", created_by=self.admin)
            other_household = Household.objects.create(space=other_space, name="Hogar ajeno")
            other_location = InventoryLocation.objects.create(
                space=other_space,
                household=other_household,
                name="Almacén ajeno",
                created_by=self.admin,
            )
            other_food = Food.objects.create(space=other_space, name="Alimento ajeno")
            other_unit = Unit.objects.create(space=other_space, name="g", base_unit="g")
            other_entry = InventoryEntry.objects.create(
                space=other_space,
                inventory_location=other_location,
                food=other_food,
                unit=other_unit,
                amount=Decimal("1000"),
                created_by=self.admin,
            )

        response = self.post(self.payload(
            entry=other_entry.pk,
            idempotency_key="waste-other-space",
        ))

        self.assertEqual(response.status_code, 404)
        with scopes_disabled():
            other_entry.refresh_from_db()
            self.assertEqual(other_entry.amount, Decimal("1000"))
            self.assertFalse(StockMovement.objects.exists())

    def test_esencial_and_profesional_cannot_record_waste(self):
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL):
            with self.subTest(edition=edition):
                self.profile.edition = edition
                self.profile.save(update_fields=["edition"])
                response = self.post(self.payload(idempotency_key=f"waste-{edition}"))
                self.assertEqual(response.status_code, 403, getattr(response, "data", response.content))

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("10000"))
        self.assertFalse(StockMovement.objects.exists())

    def test_guest_cannot_record_waste(self):
        response = self.post(self.payload(idempotency_key="guest-waste"), user=self.guest)

        self.assertEqual(response.status_code, 403, getattr(response, "data", response.content))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("10000"))
        self.assertFalse(StockMovement.objects.exists())

    def test_reversal_restores_stock_and_preserves_cause_and_valuation(self):
        created = self.post()
        self.assertEqual(created.status_code, 201, getattr(created, "data", created.content))
        original = StockMovement.objects.get(pk=created.data["movement_id"])

        reversed_response = self.post({
            "reverse_of": original.pk,
            "idempotency_key": "reverse-standalone-waste-api",
        })

        self.assertEqual(
            reversed_response.status_code,
            201,
            getattr(reversed_response, "data", reversed_response.content),
        )
        self.entry.refresh_from_db()
        reversal = StockMovement.objects.get(pk=reversed_response.data["movement_id"])
        self.assertEqual(self.entry.amount, Decimal("10000"))
        self.assertEqual(reversal.reverses_id, original.pk)
        self.assertEqual(reversal.metadata_snapshot["origin"], original.metadata_snapshot["origin"])
        self.assertEqual(reversal.metadata_snapshot["valuation"], original.metadata_snapshot["valuation"])

    def test_session_post_without_csrf_token_is_rejected_before_writing(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = self.post(self.payload(idempotency_key="csrf-waste"), client=client)

        self.assertEqual(response.status_code, 403, getattr(response, "data", response.content))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, Decimal("10000"))
        self.assertFalse(StockMovement.objects.exists())
