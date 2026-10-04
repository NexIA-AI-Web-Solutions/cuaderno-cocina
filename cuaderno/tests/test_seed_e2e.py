import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django_scopes import scopes_disabled

from cookbook.helper.permission_helper import create_space_for_user
from cookbook.models import Household, Recipe
from cuaderno.management.commands.seed_cuaderno_e2e import PREFIX
from cuaderno.models import (
    PackageFormat, PriceVersion, PurchaseOrder, ServicePlan, SpaceProfile, StockMovement,
)


PASSWORD = "fixture-password-only"


class SeedCuadernoE2ETests(TestCase):
    def base_demo(self):
        with scopes_disabled():
            Group.objects.get_or_create(name='admin')
            for edition, _title in SpaceProfile.EDITIONS:
                owner = get_user_model().objects.create_user(username=f"demo-{edition}")
                membership = create_space_for_user(owner)
                membership.household = Household.objects.create(space=membership.space, name="Equipo DEMO")
                membership.save(update_fields=["household"])
                SpaceProfile.objects.create(space=membership.space, edition=edition, currency="EUR")
                Recipe.objects.create(
                    space=membership.space, created_by=owner, name="Salsa DEMO", private=True,
                )

    def run_seed(self):
        with (
            patch.dict(os.environ, {"CUADERNO_ENV": "test", "CUADERNO_DEMO_PASSWORD": PASSWORD}),
            patch.dict(connection.settings_dict, {"NAME": "cuaderno_demo"}),
            patch("cuaderno.management.commands.seed_cuaderno_e2e.call_command"),
        ):
            call_command("seed_cuaderno_e2e")

    def test_guard_rejects_any_non_demo_database_before_bootstrap(self):
        with (
            patch.dict(os.environ, {"CUADERNO_ENV": "test", "CUADERNO_DEMO_PASSWORD": PASSWORD}),
            patch.dict(connection.settings_dict, {"NAME": "customer"}),
            patch("cuaderno.management.commands.seed_cuaderno_e2e.call_command") as bootstrap,
        ):
            with self.assertRaisesMessage(CommandError, "cuaderno_demo"):
                call_command("seed_cuaderno_e2e")
        bootstrap.assert_not_called()

    def test_seed_is_idempotent_and_does_not_rewind_ledger_or_orders(self):
        self.base_demo()
        self.run_seed()
        with scopes_disabled():
            counts = {
                "users": get_user_model().objects.filter(username__startswith="demo-", username__contains="-").count(),
                "packages": PackageFormat.objects.filter(label__startswith=PREFIX).count(),
                "prices": PriceVersion.objects.filter(note__startswith=PREFIX).count(),
                "services": ServicePlan.objects.filter(title__startswith=PREFIX).count(),
                "orders": PurchaseOrder.objects.filter(supplier_name__startswith=PREFIX).count(),
                "movements": StockMovement.objects.filter(idempotency_key__startswith="e2e-seed-stock:").count(),
            }
            self.assertEqual(counts, {
                "users": 12, "packages": 3, "prices": 3, "services": 4, "orders": 6, "movements": 3,
            })
            for plan in ServicePlan.objects.filter(title=f"{PREFIX} servicio confirmado"):
                self.assertIsNotNone(plan.service_date)
                self.assertIsNotNone(plan.meal_plan_id)
                self.assertIn(plan.snapshot["schema_version"], (1, 2))
                self.assertEqual(plan.snapshot["recipe_id"], plan.meal_plan.recipe_id)
                self.assertEqual(plan.snapshot["needs"][0]["quantity"], "5")
                self.assertEqual(plan.snapshot["cost"]["status"], "complete")
            order = PurchaseOrder.objects.get(supplier_name=f"{PREFIX}-cocina-390")
            order.state = PurchaseOrder.PART_RECEIVED
            order.received_quantity = Decimal("1")
            order.save(update_fields=["state", "received_quantity"])
            movement_ids = list(
                StockMovement.objects.order_by("pk").values_list("pk", flat=True)
            )

        self.run_seed()
        with scopes_disabled():
            self.assertEqual(
                {
                    "users": get_user_model().objects.filter(
                        username__startswith="demo-", username__contains="-",
                    ).count(),
                    "packages": PackageFormat.objects.filter(label__startswith=PREFIX).count(),
                    "prices": PriceVersion.objects.filter(note__startswith=PREFIX).count(),
                    "services": ServicePlan.objects.filter(title__startswith=PREFIX).count(),
                    "orders": PurchaseOrder.objects.filter(supplier_name__startswith=PREFIX).count(),
                    "movements": StockMovement.objects.filter(idempotency_key__startswith="e2e-seed-stock:").count(),
                },
                counts,
            )
            order.refresh_from_db()
            self.assertEqual(order.state, PurchaseOrder.PART_RECEIVED)
            self.assertEqual(order.received_quantity, Decimal("1"))
            self.assertEqual(list(StockMovement.objects.order_by("pk").values_list("pk", flat=True)), movement_ids)
