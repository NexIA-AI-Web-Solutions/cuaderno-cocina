from datetime import time
from decimal import Decimal

from django.test import TestCase
from django_scopes import scopes_disabled

from cuaderno.models import CustomerReservation, MenuTemplate, ReservationService, ServicePlan, SpaceProfile
from cuaderno.tests.test_services import ServiceFixtureMixin


class ReservationProjectionTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        _, self.plan = self.create_plan()
        with scopes_disabled():
            template = MenuTemplate.objects.create(space=self.space, name="Menú reservado", created_by=self.user)
            self.reservation = CustomerReservation.objects.create(
                space=self.space, household=self.household, customer_name="Grupo sintético",
                phone="600000000", service_date=self.plan.service_date, service_time=time(13),
                template=template, meal_type=self.plan.meal_plan.meal_type, covers=20,
                created_by=self.user, updated_by=self.user,
            )
            ReservationService.objects.create(reservation=self.reservation, service=self.plan, revision=1, position=0)

    def test_generic_service_transition_requires_reservation_flow(self):
        response = self.client_for(self.user).post(f"/api/cuaderno/services/{self.plan.pk}/", {"action": "confirm"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reserva", str(response.data).lower())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.state, ServicePlan.DRAFT)

    def test_production_endpoint_requires_reservation_flow(self):
        response = self.client_for(self.user).post("/api/cuaderno/production/", {
            "service_plan": self.plan.pk, "action": "produce", "idempotency_key": "own-projection-test",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reserva", str(response.data).lower())

    def test_native_calendar_edit_keeps_reservation_projection(self):
        response = self.client_for(self.user).patch(f"/api/meal-plan/{self.plan.meal_plan_id}/", {"title": "Changed outside reservation"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reserva", str(response.data).lower())

    def test_native_calendar_delete_keeps_reservation_projection(self):
        response = self.client_for(self.user).delete(f"/api/meal-plan/{self.plan.meal_plan_id}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reserva", str(response.data).lower())

    def test_retired_projection_is_hidden_from_calendars_but_kept_in_history(self):
        client = self.client_for(self.user)
        params = {"from_date": "2026-10-25", "to_date": "2026-10-25"}
        before = client.get("/api/meal-plan/", params)
        self.assertIn(self.plan.meal_plan_id, [row["id"] for row in before.data["results"]])
        ReservationService.objects.filter(service=self.plan).update(active=False)
        after = client.get("/api/meal-plan/", params)
        self.assertNotIn(self.plan.meal_plan_id, [row["id"] for row in after.data["results"]])
        from cuaderno.services.planning import visible_plans
        from types import SimpleNamespace
        request = SimpleNamespace(user=self.user, space=self.space, user_space=self.user.userspace_set.get())
        with scopes_disabled():
            self.assertFalse(visible_plans(request).filter(pk=self.plan.meal_plan_id).exists())
            self.assertTrue(ReservationService.objects.filter(service=self.plan, active=False).exists())
            self.assertIsNotNone(self.plan.meal_plan)


class ReservationReplenishmentRangeTests(ServiceFixtureMixin, TestCase):
    def test_period_limits_needs_and_rejects_reversed_range(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save()
        for day, covers in (("2026-10-25", 20), ("2026-10-26", 30)):
            _, plan = self.create_plan(covers=covers, service_date=day)
            self.transition(plan, "confirm")
        client = self.client_for(self.user)
        response = client.post("/api/cuaderno/replenishment/", {"from_date": "2026-10-25", "to_date": "2026-10-25"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["items"][0]["required"], "4")
        self.assertEqual(client.post("/api/cuaderno/replenishment/", {"from_date": "2026-10-26", "to_date": "2026-10-25"}, format="json").status_code, 400)

    def test_newer_unconfirmed_services_do_not_hide_older_confirmed_needs(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save()
        _, plan = self.create_plan(covers=20)
        self.transition(plan, "confirm")
        ServicePlan.objects.bulk_create([
            ServicePlan(space=self.space, household=self.household, title=f"New draft {i}", covers=1,
                        created_by=self.user, service_date=plan.service_date)
            for i in range(105)
        ])
        response = self.client_for(self.user).post("/api/cuaderno/replenishment/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data.get("items", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1, response.data)
        self.assertEqual(rows[0]["required"], "4")


class ProductionStoragePrecisionTests(ServiceFixtureMixin, TestCase):
    def test_recurring_yield_consumes_at_storage_precision_and_reverses_exactly(self):
        from cookbook.models import Ingredient, InventoryEntry, InventoryLocation
        from cuaderno.models import StockMovement
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save()
        with scopes_disabled():
            ingredient = Ingredient.objects.get(food=self.food)
            ingredient.quantity_basis = "net_usable"
            ingredient.yield_ratio = Decimal("0.9")
            ingredient.save()
            location = InventoryLocation.objects.create(space=self.space, household=self.household,
                                                       name="Precision", created_by=self.admin)
            stock = InventoryEntry.objects.create(space=self.space, inventory_location=location,
                                                  food=self.food, unit=self.kg, amount=100, created_by=self.admin)
        _, plan = self.create_plan(covers=20)
        self.transition(plan, "confirm")
        plan.refresh_from_db()
        exact_need = plan.snapshot["needs"][0]["quantity"]
        self.assertGreater(len(exact_need.split(".")[1]), 16)
        response = self.transition(plan, "produce", key="recurring-yield-produce")
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            movement = StockMovement.objects.get(kind=StockMovement.CONSUME)
            self.assertEqual(movement.quantity, Decimal("4.4444444444444445"))
            self.assertGreaterEqual(movement.quantity, Decimal(exact_need))
            stock.refresh_from_db()
            self.assertEqual(stock.amount, Decimal("95.5555555555555555"))
        plan.refresh_from_db()
        self.assertEqual(plan.snapshot["needs"][0]["quantity"], exact_need)
        self.assertEqual(self.transition(plan, "produce", key="recurring-yield-produce").status_code, 200)
        self.assertEqual(self.transition(plan, "reverse", key="recurring-yield-reverse").status_code, 200)
        with scopes_disabled():
            stock.refresh_from_db()
            self.assertEqual(stock.amount, Decimal("100"))
            self.assertEqual(StockMovement.objects.count(), 2)

    def test_recurring_need_spans_full_gram_lot_and_partial_kilogram_lot(self):
        from cookbook.models import Ingredient, InventoryEntry, InventoryLocation
        from cuaderno.models import StockMovement
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save()
        with scopes_disabled():
            ingredient = Ingredient.objects.get(food=self.food)
            ingredient.quantity_basis = "net_usable"
            ingredient.yield_ratio = Decimal("0.9")
            ingredient.save()
            location = InventoryLocation.objects.create(space=self.space, household=self.household,
                                                       name="Mixed lots", created_by=self.admin)
            first = InventoryEntry.objects.create(space=self.space, inventory_location=location,
                                                  food=self.food, unit=self.g, amount=1000, created_by=self.admin)
            second = InventoryEntry.objects.create(space=self.space, inventory_location=location,
                                                   food=self.food, unit=self.kg, amount=100, created_by=self.admin)
        _, plan = self.create_plan(covers=20)
        self.transition(plan, "confirm")
        response = self.transition(plan, "produce", key="mixed-yield-produce")
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            consumed = dict(StockMovement.objects.filter(kind=StockMovement.CONSUME).values_list("entry_id", "quantity"))
            self.assertEqual(consumed, {first.pk: Decimal("1000"), second.pk: Decimal("3.4444444444444445")})
            first.refresh_from_db(); second.refresh_from_db()
            self.assertEqual(first.amount, 0)
            self.assertEqual(second.amount, Decimal("96.5555555555555555"))
        self.assertEqual(self.transition(plan, "produce", key="mixed-yield-produce").status_code, 200)
        self.assertEqual(self.transition(plan, "reverse", key="mixed-yield-reverse").status_code, 200)
        with scopes_disabled():
            first.refresh_from_db(); second.refresh_from_db()
            self.assertEqual(first.amount, 1000)
            self.assertEqual(second.amount, 100)
            self.assertEqual(StockMovement.objects.count(), 4)

    def test_lot_subtraction_preserves_tail_beyond_default_decimal_context(self):
        from cookbook.models import Ingredient, InventoryEntry, InventoryLocation
        from cuaderno.models import StockMovement
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save()
        with scopes_disabled():
            ingredient = Ingredient.objects.get(food=self.food)
            ingredient.amount = Decimal("1")
            ingredient.quantity_basis = "net_usable"
            ingredient.yield_ratio = Decimal("0.9999999999999999")
            ingredient.save()
            location = InventoryLocation.objects.create(space=self.space, household=self.household,
                                                       name="Decimal boundary", created_by=self.admin)
            InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food,
                                          unit=self.kg, amount=Decimal("0.0000000000000001"), created_by=self.admin)
            second = InventoryEntry.objects.create(space=self.space, inventory_location=location,
                                                   food=self.food, unit=self.kg, amount=100, created_by=self.admin)
        _, plan = self.create_plan(covers=10)
        self.transition(plan, "confirm")
        response = self.transition(plan, "produce", key="tail-precision-produce")
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            movement = StockMovement.objects.get(entry=second, kind=StockMovement.CONSUME)
            self.assertEqual(movement.quantity, Decimal("1.0000000000000001"))
