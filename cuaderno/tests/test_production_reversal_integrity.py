from copy import deepcopy
from decimal import Decimal

from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.exceptions import ValidationError

from cookbook.models import InventoryEntry, InventoryLocation, InventoryLog
from cuaderno.models import ServicePlan, SpaceProfile, StockMovement
from cuaderno.services.ledger import apply_movement, reverse_movement
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductionReversalIntegrityTests(ServiceFixtureMixin, TestCase):
    def produce_integral_service(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        with scopes_disabled():
            location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Almacén de producción",
                created_by=self.user,
            )
            entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("10"),
                created_by=self.user,
            )
        _, plan = self.create_plan(covers=20)
        confirmed = self.transition(plan, "confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        produced = self.transition(plan, "produce", key="valid-production-key")
        self.assertEqual(produced.status_code, 200, produced.data)
        with scopes_disabled():
            entry.refresh_from_db()
            plan.refresh_from_db()
            movement = StockMovement.objects.get(pk=produced.data["movement_ids"][0])
        self.assertEqual(entry.amount, Decimal("6"))
        self.assertEqual(plan.state, ServicePlan.PRODUCED)
        return entry, plan, movement

    def integrity_snapshot(self, entry, plan):
        with scopes_disabled():
            entry.refresh_from_db()
            plan.refresh_from_db()
            movements = list(
                StockMovement.objects.order_by("pk").values(
                    "id", "kind", "quantity", "balance_after", "reverses_id", "metadata_snapshot"
                )
            )
            logs = list(
                InventoryLog.objects.order_by("pk").values(
                    "id", "entry_id", "booking_type", "old_amount", "new_amount", "note"
                )
            )
        return {
            "balance": entry.amount,
            "state": plan.state,
            "snapshot": deepcopy(plan.snapshot),
            "produced_at": plan.produced_at,
            "produced_key": plan.produced_key,
            "movements": movements,
            "logs": logs,
        }

    def test_generic_reversal_api_rejects_production_movement_without_any_mutation(self):
        entry, plan, movement = self.produce_integral_service()
        before = self.integrity_snapshot(entry, plan)

        response = self.client_for(self.user).post(
            "/api/cuaderno/movements/",
            {"reverse_of": movement.pk, "idempotency_key": "forbidden-production-reversal"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, getattr(response, "data", response.content))
        self.assertIn("reverse_of", response.data)
        self.assertIn("reversión completa", str(response.data["reverse_of"]))
        self.assertIn("aún no está disponible", str(response.data["reverse_of"]))
        self.assertEqual(self.integrity_snapshot(entry, plan), before)

    def test_direct_helper_rejects_production_movement_without_any_mutation(self):
        entry, plan, movement = self.produce_integral_service()
        before = self.integrity_snapshot(entry, plan)

        with scopes_disabled(), self.assertRaises(ValidationError):
            reverse_movement(
                movement_id=movement.pk,
                space=self.space,
                user=self.user,
                idempotency_key="forbidden-direct-production-reversal",
            )

        self.assertEqual(self.integrity_snapshot(entry, plan), before)

    def test_forged_service_origin_is_protected_without_resolving_its_claimed_id(self):
        entry, plan, _ = self.produce_integral_service()
        with scopes_disabled():
            forged = apply_movement(
                entry_id=entry.pk,
                space=self.space,
                user=self.user,
                kind=StockMovement.CONSUME,
                quantity="1",
                idempotency_key="forged-service-origin",
                origin={"type": "service_plan", "id": 9223372036854775807},
            )
        before = self.integrity_snapshot(entry, plan)

        with scopes_disabled(), self.assertRaises(ValidationError):
            reverse_movement(
                movement_id=forged.pk,
                space=self.space,
                user=self.user,
                idempotency_key="forged-service-origin-reversal",
            )

        self.assertEqual(self.integrity_snapshot(entry, plan), before)

    def test_standalone_waste_reversal_remains_allowed(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        with scopes_disabled():
            location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Almacén de mermas",
                created_by=self.user,
            )
            entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("10"),
                created_by=self.user,
            )
            waste = apply_movement(
                entry_id=entry.pk,
                space=self.space,
                user=self.user,
                kind=StockMovement.WASTE,
                quantity="1.25",
                idempotency_key="standalone-waste",
                origin={"type": "standalone_waste", "cause": "caducidad"},
            )
            reversal = reverse_movement(
                movement_id=waste.pk,
                space=self.space,
                user=self.user,
                idempotency_key="reverse-standalone-waste",
            )
            entry.refresh_from_db()

        self.assertEqual(entry.amount, Decimal("10"))
        self.assertEqual(reversal.kind, StockMovement.RECEIPT)
        self.assertEqual(reversal.reverses_id, waste.pk)
        self.assertEqual(reversal.metadata_snapshot["origin"], waste.metadata_snapshot["origin"])
