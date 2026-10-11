"""Persistent read-only worker contracts, using the native operational fixtures."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace

from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.exceptions import PermissionDenied, ValidationError

from cookbook.models import Ingredient, InventoryEntry, InventoryLocation, UserSpace
from cuaderno.models import PriceVersion, PurchaseOrder, ServicePlan, SpaceProfile
from cuaderno.tests.test_services import ServiceFixtureMixin
from cuaderno.services.worker_analysis import build_worker_report


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WorkerAnalysisTests(ServiceFixtureMixin, TestCase):
    def request(self, user=None):
        user = user or self.user
        return SimpleNamespace(user=user, space=self.space,
                               user_space=UserSpace.objects.get(user=user, space=self.space))

    def report(self, kind, **params):
        with scopes_disabled():
            report = build_worker_report(self.request(), kind, params)
            json.dumps(report)
            return report

    def test_unknown_kind_and_invalid_limits_are_rejected(self):
        with scopes_disabled():
            for kind, params in (("imaginary", {}), ("cost_completion", {"limit": True}),
                                 ("cost_completion", {"limit": 101}),
                                 ("cost_completion", {"budget": "1e99999"}),
                                 ("service_briefing", {"date": "11/10/2026"})):
                with self.subTest(kind=kind, params=params), self.assertRaises(ValidationError):
                    build_worker_report(self.request(), kind, params)

    def test_cost_completion_identifies_actual_ingredient_and_missing_price(self):
        with scopes_disabled():
            PriceVersion.objects.all().delete()
            ingredient = Ingredient.objects.get(step__recipe=self.recipe)
        report = self.report("cost_completion")
        item = report["items"][0]
        self.assertEqual(item["recipe_id"], self.recipe.pk)
        self.assertEqual(item["status"], "incomplete")
        blocker = item["blockers"][0]
        self.assertEqual(blocker["ingredient_id"], ingredient.pk)
        self.assertEqual(blocker["food_id"], self.food.pk)
        self.assertIn("precio_desconocido", blocker["codes"])
        self.assertIsNone(item["cost"]["unrounded"])

    def test_cost_completion_never_exposes_private_recipes(self):
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.created_by = self.admin
            self.recipe.save()
        self.assertEqual(self.report("cost_completion")["items"], [])

    def test_price_watch_exact_portfolio_impact_and_frozen_drift(self):
        with scopes_disabled():
            _, plan = self.create_plan(covers=20)
            self.assertEqual(self.transition(plan, "confirm").status_code, 200)
            plan.refresh_from_db()
            frozen = deepcopy(plan.snapshot)
            PriceVersion.objects.create(space=self.space, package=self.package, amount="15",
                                        created_by=self.admin, valid_from=timezone.now() - timedelta(seconds=1))
        report = self.report("price_watch")
        impact = next(row for row in report["items"] if row["type"] == "recipe_price_impact")
        self.assertEqual(Decimal(impact["difference"]), Decimal("2"))
        drift = report["service_drift"][0]
        self.assertEqual(Decimal(drift["difference"]), Decimal("4"))
        with scopes_disabled():
            plan.refresh_from_db()
            self.assertEqual(plan.snapshot, frozen)

    def test_briefing_uses_frozen_needs_and_preparation_not_current_recipe(self):
        with scopes_disabled():
            _, plan = self.create_plan(covers=20)
            self.assertEqual(self.transition(plan, "confirm").status_code, 200)
            Ingredient.objects.filter(step__recipe=self.recipe).update(amount="9")
        report = self.report("service_briefing", date="2026-10-25")
        self.assertEqual(report["items"][0]["service_id"], plan.pk)
        self.assertEqual(Decimal(report["items"][0]["needs"][0]["quantity"]), Decimal("4"))
        self.assertEqual(report["items"][0]["preparation"]["pending"], 1)

    def test_requirements_unknown_is_preserved_and_only_explicit_notes_are_candidates(self):
        with scopes_disabled():
            self.recipe.description = "Preparar sin lactosa. Una ración pequeña."
            self.recipe.save()
        report = self.report("requirements_review")
        self.assertEqual(report["items"][0]["allergens"]["assessment"], "unknown")
        self.assertFalse(report["items"][0]["allergens"]["undeclared_means_absent"])
        self.assertFalse(report["dietary_guarantees"])
        self.assertEqual([candidate["keyword"] for candidate in report["items"][0]["requirement_candidates"]], ["lactosa"])
        self.assertTrue(report["items"][0]["requirement_candidates"][0]["requires_confirmation"])

    def test_menu_candidates_exclude_expired_other_household_and_missing_units(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            location = InventoryLocation.objects.create(space=self.space, household=self.household, name="Despensa", created_by=self.user)
            InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food,
                                          unit=self.kg, amount="2", created_by=self.user,
                                          expires=date(2026, 10, 10))
            InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food,
                                          unit=self.kg, amount="1", created_by=self.user)
            InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food,
                                          unit=None, amount="100", created_by=self.user)
            other_location = InventoryLocation.objects.create(space=self.space, household=self.other_household,
                                                               name="Otro hogar", created_by=self.outsider)
            InventoryEntry.objects.create(space=self.space, inventory_location=other_location, food=self.food,
                                          unit=self.kg, amount="100", created_by=self.outsider)
        report = self.report("menu_candidates", date="2026-10-11", servings="10")
        item = report["items"][0]
        self.assertFalse(item["stock_sufficient"])
        self.assertEqual(Decimal(item["needs"][0]["available"]), Decimal("1"))
        self.assertEqual(Decimal(item["needs"][0]["shortfall"]), Decimal("1"))

    def test_purchase_review_preserves_pending_and_does_not_change_stock(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            order = PurchaseOrder.objects.create(space=self.space, household=self.household, food=self.food,
                unit=self.kg, quantity="5", received_quantity="2", state="part_received", created_by=self.user)
        report = self.report("purchase_review")
        self.assertEqual(report["items"][0]["order_id"], order.pk)
        self.assertEqual(Decimal(report["items"][0]["pending_quantity"]), Decimal("3"))
        self.assertIn("receipt_total_mismatch", report["items"][0]["issues"])
        with scopes_disabled():
            order.refresh_from_db()
            self.assertEqual(order.received_quantity, Decimal("2"))

    def test_service_learning_counts_recorded_services_without_forecasts(self):
        with scopes_disabled():
            for covers in (2, 3):
                ServicePlan.objects.create(space=self.space, household=self.household, title="Comida", covers=covers,
                    created_by=self.user, state="produced", service_date=date(2026, 10, 10),
                    snapshot={"recipe_id": self.recipe.pk, "recipe_graph": {str(self.recipe.pk): []}})
        report = self.report("service_learning", start="2026-10-01", end="2026-10-11")
        self.assertEqual(report["items"][0]["produced_count"], 2)
        self.assertEqual(Decimal(report["items"][0]["produced_covers"]), Decimal("5"))
        self.assertFalse(report["forecast"])

    def test_editions_roles_and_reads_never_create_profile(self):
        with scopes_disabled():
            self.profile.delete()
            before = SpaceProfile.objects.count()
            build_worker_report(self.request(), "cost_completion", {})
            self.assertEqual(SpaceProfile.objects.count(), before)
            with self.assertRaises(PermissionDenied):
                build_worker_report(self.request(), "service_briefing", {})
            with self.assertRaises(PermissionDenied):
                build_worker_report(self.request(), "purchase_review", {})

    def test_cost_questions_group_shared_missing_price_and_link_actual_recipe(self):
        with scopes_disabled():
            PriceVersion.objects.all().delete()
        report = self.report("cost_completion")
        question = report["grouped_questions"][0]
        self.assertEqual(question["food_id"], self.food.pk)
        self.assertEqual(question["affected_recipe_count"], 1)
        self.assertEqual(question["action_url"], f"/recipe/{self.recipe.pk}")

    def test_professional_menu_candidates_keep_stock_unknown(self):
        report = self.report("menu_candidates", servings="10", budget="0")
        item = report["items"][0]
        self.assertFalse(item["stock_known"])
        self.assertIsNone(item["stock_sufficient"])
        self.assertIsNone(item["needs"][0]["available"])
        self.assertFalse(item["within_budget"])

    def test_purchase_needs_do_not_count_pending_orders_as_received_stock(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            _, plan = self.create_plan(covers=20)
            self.assertEqual(self.transition(plan, "confirm").status_code, 200)
            order = PurchaseOrder.objects.create(space=self.space, household=self.household, food=self.food,
                unit=self.kg, quantity="5", state="ordered", created_by=self.user)
        report = self.report("purchase_review", date="2026-10-25")
        need = report["buying_needs"][0]
        self.assertEqual(Decimal(need["missing"]), Decimal("4"))
        self.assertEqual(Decimal(need["packages"]), Decimal("1"))
        self.assertEqual(report["pending_orders"][0]["order_id"], order.pk)
        self.assertTrue(report["pending_orders"][0]["arrival_unknown"])

    def test_receipt_review_converts_order_units_and_preserves_native_balance(self):
        from cuaderno.services.purchasing import receive_order
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            location = InventoryLocation.objects.create(space=self.space, household=self.household,
                                                       name="Despensa", created_by=self.user)
            entry = InventoryEntry.objects.create(space=self.space, inventory_location=location, food=self.food,
                                                  unit=self.g, amount="1000", created_by=self.user)
            order = PurchaseOrder.objects.create(space=self.space, household=self.household, food=self.food,
                unit=self.kg, quantity="5", state="ordered", created_by=self.user)
            receipt, _ = receive_order(request=self.request(), order=order, entry=entry,
                                       quantity=Decimal("2"), raw_key="worker-test-receipt")
            entry.refresh_from_db()
            before = entry.amount
        report = self.report("receipt_review")
        self.assertEqual(report["items"][0]["receipt_id"], receipt.pk)
        self.assertEqual(report["items"][0]["issues"], [])
        with scopes_disabled():
            entry.refresh_from_db()
            self.assertEqual(entry.amount, before)

    def test_household_scope_hides_other_services_and_orders(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            plan = ServicePlan.objects.create(space=self.space, household=self.other_household, title="Otro hogar",
                covers=3, created_by=self.outsider, service_date=date(2026, 10, 11))
            order = PurchaseOrder.objects.create(space=self.space, household=self.other_household, food=self.food,
                unit=self.kg, quantity="5", state="ordered", created_by=self.outsider)
        self.assertNotIn(plan.pk, [item["service_id"] for item in self.report("service_briefing")["items"]])
        self.assertNotIn(order.pk, [item["order_id"] for item in self.report("purchase_review")["items"]])

    def test_every_report_is_read_only_at_database_level(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            for kind in ("cost_completion", "price_watch", "service_briefing", "requirements_review",
                         "purchase_review", "receipt_review", "menu_candidates", "service_learning"):
                with self.subTest(kind=kind), CaptureQueriesContext(connection) as queries:
                    build_worker_report(self.request(), kind, {})
                    mutations = [query["sql"] for query in queries if query["sql"].lstrip().split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
                    self.assertEqual(mutations, [])

    def test_purchase_default_period_excludes_past_and_future_confirmed_needs(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            for offset, quantity in ((-1, "99"), (0, "4"), (1, "77")):
                ServicePlan.objects.create(space=self.space, household=self.household, title="Turno", covers=20,
                    created_by=self.user, state="confirmed", service_date=timezone.localdate() + timedelta(days=offset),
                    snapshot={"recipe_id": self.recipe.pk, "recipe_graph": {str(self.recipe.pk): []},
                              "needs": [{"food_id": self.food.pk, "unit_id": self.kg.pk, "quantity": quantity}]})
        report = self.report("purchase_review")
        self.assertEqual(Decimal(report["buying_needs"][0]["required"]), Decimal("4"))
        self.assertEqual(len(report["service_ids"]), 1)
        self.assertEqual(report["start"], timezone.localdate().isoformat())
        self.assertEqual(report["end"], timezone.localdate().isoformat())

    def test_effective_single_period_bounds_are_ordered_and_bounded(self):
        with scopes_disabled():
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save()
            today = timezone.localdate()
            for kind in ("purchase_review", "price_watch"):
                for params in ({"start": (today - timedelta(days=400)).isoformat()},
                               {"end": (today + timedelta(days=400)).isoformat()},
                               {"start": (today + timedelta(days=400)).isoformat()},
                               {"end": (today - timedelta(days=400)).isoformat()}):
                    with self.subTest(kind=kind, params=params), self.assertRaises(ValidationError):
                        build_worker_report(self.request(), kind, params)
