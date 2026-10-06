from datetime import date
from decimal import Decimal
from threading import Barrier, Lock, Thread
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    Household,
    Ingredient,
    InventoryEntry,
    InventoryLocation,
    Recipe,
    Space,
    Step,
    Unit,
    UserSpace,
)
from cuaderno.models import PackageFormat, PriceVersion, ServicePlan, SpaceProfile, StockMovement


class ServiceFixtureMixin:
    def make_user(self, username, group_name, household):
        user = get_user_model().objects.create_user(username=username, password="local-test-only")
        membership = UserSpace.objects.create(
            user=user,
            space=self.space,
            household=household,
            active=True,
        )
        membership.groups.add(Group.objects.get_or_create(name=group_name)[0])
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Servicios")
            self.household = Household.objects.create(space=self.space, name="Cocina")
            self.other_household = Household.objects.create(space=self.space, name="Otra cocina")
            self.admin = self.make_user("service-admin", "admin", self.household)
            self.user = self.make_user("service-user", "user", self.household)
            self.helper = self.make_user("service-helper", "user", self.household)
            self.outsider = self.make_user("service-outsider", "user", self.other_household)
            self.space.created_by = self.admin
            self.space.save(update_fields=["created_by"])
            self.profile = SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.PROFESIONAL)

            self.kg = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.g = Unit.objects.create(space=self.space, name="g", base_unit="g")
            self.food = Food.objects.create(space=self.space, name="Arroz")
            self.recipe = Recipe.objects.create(
                space=self.space,
                name="Arroz para servicio",
                servings=10,
                created_by=self.user,
            )
            step = Step.objects.create(space=self.space, name="Preparar")
            step.ingredients.add(
                Ingredient.objects.create(
                    space=self.space,
                    food=self.food,
                    unit=self.kg,
                    amount=Decimal("2"),
                )
            )
            self.recipe.steps.add(step)
            package = PackageFormat.objects.create(
                space=self.space,
                food=self.food,
                unit=self.kg,
                label="Saco 5 kg",
                quantity=Decimal("5"),
            )
            PriceVersion.objects.create(
                space=self.space,
                package=package,
                amount=Decimal("10"),
                valid_from="2026-01-01T00:00:00Z",
                created_by=self.admin,
            )
            self.package = package

    def create_plan(self, *, user=None, title="Comida", covers=20, service_date="2026-10-25"):
        response = self.client_for(user or self.user).post(
            "/api/cuaderno/services/",
            {
                "title": title,
                "covers": covers,
                "service_date": service_date,
                "recipe": self.recipe.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response, ServicePlan.objects.get(pk=response.data["id"])

    def transition(self, plan, action, *, user=None, key=None):
        payload = {"action": action}
        if key is not None:
            payload["idempotency_key"] = key
        return self.client_for(user or self.user).post(
            f"/api/cuaderno/services/{plan.pk}/",
            payload,
            format="json",
        )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServiceWorkflowTests(ServiceFixtureMixin, TestCase):
    @override_settings(TIME_ZONE="America/New_York")
    def test_create_uses_configured_timezone_across_both_dst_boundaries(self):
        local_zone = ZoneInfo("America/New_York")
        for service_date, offset in (("2026-03-08", -18000), ("2026-11-01", -14400)):
            with self.subTest(service_date=service_date):
                response, plan = self.create_plan(service_date=service_date, covers=2)
                local_start = timezone.localtime(plan.meal_plan.from_date, local_zone)
                self.assertEqual(response.data["timezone"], "America/New_York")
                self.assertEqual(local_start.date(), date.fromisoformat(service_date))
                self.assertEqual(local_start.hour, 0)
                self.assertEqual(local_start.utcoffset().total_seconds(), offset)

    def test_list_is_bounded_and_detail_can_access_an_older_service(self):
        plans = ServicePlan.objects.bulk_create([
            ServicePlan(space=self.space, household=self.household, title=f"Turno {index}", covers=1, created_by=self.user)
            for index in range(102)
        ])
        client = self.client_for(self.user)
        listing = client.get("/api/cuaderno/services/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 100)
        self.assertNotIn(plans[0].pk, {row["id"] for row in listing.data})
        detail = client.get(f"/api/cuaderno/services/{plans[0].pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["id"], plans[0].pk)

    @override_settings(TIME_ZONE="Europe/Madrid")
    def test_create_uses_local_service_date_and_requires_positive_integer_covers(self):
        response, plan = self.create_plan(service_date="2026-10-25", covers=45)

        self.assertEqual(plan.service_date, date(2026, 10, 25))
        self.assertEqual(plan.covers, Decimal("45"))
        self.assertEqual(plan.state, ServicePlan.DRAFT)
        madrid = ZoneInfo("Europe/Madrid")
        self.assertTrue(timezone.is_aware(plan.meal_plan.from_date))
        local_start = timezone.localtime(plan.meal_plan.from_date, madrid)
        self.assertEqual(local_start.date(), plan.service_date)
        self.assertEqual(local_start.hour, 0)
        self.assertEqual(local_start.utcoffset().total_seconds(), 7200)
        self.assertEqual(response.data["timezone"], "Europe/Madrid")

        _, spring_plan = self.create_plan(title="Cambio de primavera", covers=2, service_date="2026-03-29")
        spring_start = timezone.localtime(spring_plan.meal_plan.from_date, madrid)
        self.assertEqual(spring_start.date(), spring_plan.service_date)
        self.assertEqual(spring_start.hour, 0)
        self.assertEqual(spring_start.utcoffset().total_seconds(), 3600)

        fractional = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"covers": "2.5", "service_date": "2026-10-25", "recipe": self.recipe.pk},
            format="json",
        )
        malformed_date = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"covers": "2", "service_date": "25/10/2026", "recipe": self.recipe.pk},
            format="json",
        )
        too_many = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"covers": "10000", "service_date": "2026-10-25", "recipe": self.recipe.pk},
            format="json",
        )
        non_text_title = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"title": ["no"], "covers": "2", "service_date": "2026-10-25", "recipe": self.recipe.pk},
            format="json",
        )
        long_title = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"title": "x" * 129, "covers": "2", "service_date": "2026-10-25", "recipe": self.recipe.pk},
            format="json",
        )
        self.assertEqual(fractional.status_code, 400)
        self.assertEqual(malformed_date.status_code, 400)
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(non_text_title.status_code, 400)
        self.assertEqual(long_title.status_code, 400)

    def test_private_recipe_is_not_disclosed_when_creating_service(self):
        with scopes_disabled():
            private = Recipe.objects.create(
                space=self.space,
                name="Privada",
                servings=1,
                created_by=self.outsider,
                private=True,
            )
        response = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"covers": 2, "service_date": "2026-10-25", "recipe": private.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_household_helper_can_operate_plan_but_outsider_cannot_and_admin_can_review(self):
        _, plan = self.create_plan()
        self.assertEqual(self.transition(plan, "confirm", user=self.helper).status_code, 200)
        self.assertEqual(self.transition(plan, "cancel", user=self.outsider).status_code, 404)
        visible_to_outsider = self.client_for(self.outsider).get("/api/cuaderno/services/")
        visible_to_admin = self.client_for(self.admin).get("/api/cuaderno/services/")
        self.assertEqual(visible_to_outsider.status_code, 200)
        self.assertEqual(visible_to_outsider.data, [])
        self.assertEqual([row["id"] for row in visible_to_admin.data], [plan.pk])

    def test_confirmed_private_recipe_snapshot_remains_private_from_helper_and_admin(self):
        _, plan = self.create_plan()
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        self.recipe.private = True
        self.recipe.save(update_fields=["private"])

        self.assertEqual(self.client_for(self.user).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 200)
        self.assertEqual(self.client_for(self.helper).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.admin).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.outsider).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.helper).get("/api/cuaderno/services/").data, [])
        self.assertEqual(self.client_for(self.admin).get("/api/cuaderno/services/").data, [])
        self.assertEqual(self.transition(plan, "cancel", user=self.helper).status_code, 404)

    def test_private_child_recipe_also_protects_confirmed_snapshot(self):
        with scopes_disabled():
            child = Recipe.objects.create(
                space=self.space,
                name="Salsa privada",
                servings=1,
                created_by=self.user,
                private=False,
            )
            child_food = Food.objects.create(space=self.space, name="Salsa reservada", recipe=child)
            step = self.recipe.steps.get()
            step.ingredients.add(
                Ingredient.objects.create(
                    space=self.space,
                    food=child_food,
                    unit=self.kg,
                    amount=Decimal("1"),
                )
            )
        _, plan = self.create_plan()
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        child.private = True
        child.save(update_fields=["private"])

        self.assertEqual(self.client_for(self.user).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 200)
        self.assertEqual(self.client_for(self.helper).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.admin).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.transition(plan, "cancel", user=self.helper).status_code, 404)

    def test_membership_move_does_not_transfer_existing_plan_or_its_stock_scope(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        own = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Hogar congelado", created_by=self.user
        )
        moved = InventoryLocation.objects.create(
            space=self.space, household=self.other_household, name="Hogar nuevo", created_by=self.outsider
        )
        original_entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=own, food=self.food, unit=self.kg,
            amount=Decimal("10"), created_by=self.user,
        )
        new_household_entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=moved, food=self.food, unit=self.kg,
            amount=Decimal("10"), created_by=self.outsider,
        )
        _, plan = self.create_plan(covers=20)
        membership = UserSpace.objects.get(user=self.user, space=self.space)
        membership.household = self.other_household
        membership.save(update_fields=["household"])
        cache.clear()

        self.assertEqual(self.client_for(self.user).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.outsider).get(f"/api/cuaderno/services/{plan.pk}/").status_code, 404)
        self.assertEqual(self.transition(plan, "confirm", user=self.helper).status_code, 200)
        produced = self.transition(plan, "produce", user=self.helper, key="membership-move")

        self.assertEqual(produced.status_code, 200, produced.data)
        original_entry.refresh_from_db()
        new_household_entry.refresh_from_db()
        self.assertEqual(original_entry.amount, Decimal("6"))
        self.assertEqual(new_household_entry.amount, Decimal("10"))

    def test_confirm_freezes_scaled_needs_and_cost_without_changing_stock(self):
        _, plan = self.create_plan(covers=20)
        with scopes_disabled():
            before = list(InventoryEntry.objects.values_list("pk", "amount"))

        response = self.transition(plan, "confirm")

        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        self.assertEqual(plan.state, ServicePlan.CONFIRMED)
        self.assertIsNotNone(plan.confirmed_at)
        self.assertEqual(plan.snapshot["schema_version"], 1)
        self.assertEqual(plan.snapshot["covers"], "20")
        self.assertEqual(plan.snapshot["needs"][0]["food_id"], self.food.pk)
        self.assertEqual(plan.snapshot["needs"][0]["unit_id"], self.kg.pk)
        self.assertEqual(plan.snapshot["needs"][0]["quantity"], "4")
        self.assertEqual(Decimal(plan.snapshot["cost"]["total"]), Decimal("8"))
        self.assertEqual(plan.snapshot["cost"]["display"], "8.00")
        with scopes_disabled():
            self.assertEqual(list(InventoryEntry.objects.values_list("pk", "amount")), before)

        PriceVersion.objects.create(
            space=self.space,
            package=self.package,
            amount=Decimal("15"),
            valid_from="2026-09-01T00:00:00Z",
            created_by=self.admin,
        )
        plan.refresh_from_db()
        self.assertEqual(Decimal(plan.snapshot["cost"]["total"]), Decimal("8"))
        self.assertEqual(plan.snapshot["cost"]["display"], "8.00")

    def test_cancel_draft_or_confirmed_never_changes_stock(self):
        location = InventoryLocation.objects.create(
            space=self.space,
            household=self.household,
            name="Despensa",
            created_by=self.user,
        )
        entry = InventoryEntry.objects.create(
            space=self.space,
            inventory_location=location,
            food=self.food,
            unit=self.kg,
            amount=Decimal("9"),
            created_by=self.user,
        )
        _, draft = self.create_plan(title="Borrador")
        _, confirmed = self.create_plan(title="Confirmado")
        self.assertEqual(self.transition(confirmed, "confirm").status_code, 200)

        self.assertEqual(self.transition(draft, "cancel").status_code, 200)
        self.assertEqual(self.transition(confirmed, "cancel").status_code, 200)

        entry.refresh_from_db()
        draft.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("9"))
        self.assertEqual(draft.state, ServicePlan.CANCELLED)
        self.assertEqual(confirmed.state, ServicePlan.CANCELLED)

    def test_professional_production_is_explicit_state_only(self):
        location = InventoryLocation.objects.create(
            space=self.space,
            household=self.household,
            name="Seco",
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
        _, plan = self.create_plan()
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)

        response = self.transition(plan, "produce", key="professional-production")

        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(plan.state, ServicePlan.PRODUCED)
        self.assertIsNotNone(plan.produced_at)
        self.assertEqual(entry.amount, Decimal("10"))
        self.assertEqual(response.data["stock_changed"], False)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_service_without_recipe_can_be_planned_but_not_produced(self):
        created = self.client_for(self.user).post(
            "/api/cuaderno/services/",
            {"title": "Reserva pendiente", "covers": 8, "service_date": "2026-10-25"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        plan = ServicePlan.objects.get(pk=created.data["id"])
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)

        produced = self.transition(plan, "produce", key="no-recipe")

        self.assertEqual(produced.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.state, ServicePlan.CONFIRMED)

    def test_integral_production_consumes_fefo_with_conversion_and_skips_unusable_stock(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        own = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Propio", created_by=self.user
        )
        other = InventoryLocation.objects.create(
            space=self.space, household=self.other_household, name="Ajeno", created_by=self.outsider
        )
        expired = InventoryEntry.objects.create(
            space=self.space, inventory_location=own, food=self.food, unit=self.kg,
            amount=9, expires=date(2026, 10, 24), created_by=self.user,
        )
        first = InventoryEntry.objects.create(
            space=self.space, inventory_location=own, food=self.food, unit=self.g,
            amount=1500, expires=date(2026, 10, 25), created_by=self.user,
        )
        second = InventoryEntry.objects.create(
            space=self.space, inventory_location=own, food=self.food, unit=self.kg,
            amount=5, expires=None, created_by=self.user,
        )
        foreign = InventoryEntry.objects.create(
            space=self.space, inventory_location=other, food=self.food, unit=self.kg,
            amount=20, expires=date(2026, 10, 25), created_by=self.outsider,
        )
        _, plan = self.create_plan(covers=20)
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)

        response = self.transition(plan, "produce", key="integral-fefo")

        self.assertEqual(response.status_code, 200, response.data)
        for entry in (expired, first, second, foreign):
            entry.refresh_from_db()
        self.assertEqual(expired.amount, Decimal("9"))
        self.assertEqual(first.amount, Decimal("0"))
        self.assertEqual(second.amount, Decimal("2.5"))
        self.assertEqual(foreign.amount, Decimal("20"))
        self.assertEqual(StockMovement.objects.filter(kind=StockMovement.CONSUME).count(), 2)
        for movement in StockMovement.objects.filter(kind=StockMovement.CONSUME):
            self.assertEqual(
                movement.metadata_snapshot["origin"],
                {
                    "type": "service_plan",
                    "id": plan.pk,
                    "service_date": "2026-10-25",
                },
            )

    def test_incomplete_recipe_warning_blocks_production_without_consumption(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        with scopes_disabled():
            step = self.recipe.steps.get()
            step.ingredients.add(
                Ingredient.objects.create(
                    space=self.space,
                    food=None,
                    unit=self.kg,
                    amount=Decimal("1"),
                )
            )
        location = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Ficha incompleta", created_by=self.user
        )
        entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("10"), created_by=self.user,
        )
        _, plan = self.create_plan(covers=20)
        confirmed = self.transition(plan, "confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        plan.refresh_from_db()
        self.assertIn("ingredient_incomplete", [warning["code"] for warning in plan.snapshot["warnings"]])

        produced = self.transition(plan, "produce", key="incomplete-sheet")

        self.assertEqual(produced.status_code, 400)
        entry.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("10"))
        self.assertEqual(plan.state, ServicePlan.CONFIRMED)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_insufficient_integral_stock_rolls_back_without_partial_consumption(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        location = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Escaso", created_by=self.user
        )
        entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("1"), created_by=self.user,
        )
        _, plan = self.create_plan(covers=20)
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)

        response = self.transition(plan, "produce", key="insufficient")

        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("1"))
        self.assertEqual(plan.state, ServicePlan.CONFIRMED)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_late_production_does_not_consume_stock_expired_after_service_date(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        location = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Producción tardía", created_by=self.user
        )
        now_expired = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("10"), expires=date(2026, 9, 15), created_by=self.user,
        )
        usable = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("5"), expires=None, created_by=self.user,
        )
        _, plan = self.create_plan(covers=20, service_date="2026-09-01")
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)

        response = self.transition(plan, "produce", key="late-production")

        self.assertEqual(response.status_code, 200, response.data)
        now_expired.refresh_from_db()
        usable.refresh_from_db()
        self.assertEqual(now_expired.amount, Decimal("10"))
        self.assertEqual(usable.amount, Decimal("1"))

    def test_production_replay_is_stable_and_same_key_for_another_plan_conflicts(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        location = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Idempotencia", created_by=self.user
        )
        entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("20"), created_by=self.user,
        )
        _, first = self.create_plan(title="Primero")
        _, second = self.create_plan(title="Segundo")
        self.assertEqual(self.transition(first, "confirm").status_code, 200)
        self.assertEqual(self.transition(second, "confirm").status_code, 200)

        initial = self.transition(first, "produce", key="same-production-key")
        replay = self.transition(first, "produce", key="same-production-key")
        conflict = self.transition(second, "produce", key="same-production-key")

        self.assertEqual(initial.status_code, 200, initial.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["movement_ids"], initial.data["movement_ids"])
        self.assertEqual(conflict.status_code, 409)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("16"))


    def test_guest_service_reads_enforce_household_private_graph_and_revocation(self):
        _, visible = self.create_plan()
        with scopes_disabled():
            guest = self.make_user("service-safe-read-guest", "guest", self.household)
            private = Recipe.objects.create(
                space=self.space, name="Private graph marker", servings=1,
                created_by=self.outsider, private=True,
            )
            denied = ServicePlan.objects.create(
                space=self.space, household=self.household, meal_plan=visible.meal_plan,
                title="Denied graph marker", covers=1, created_by=self.user,
                snapshot={"recipe_graph": {str(self.recipe.pk): [private.pk]}},
            )
            other_household = ServicePlan.objects.create(
                space=self.space, household=self.other_household, meal_plan=visible.meal_plan,
                title="Other household marker", covers=1, created_by=self.outsider,
            )
        client = self.client_for(guest)

        def ids():
            response = client.get("/api/cuaderno/services/")
            self.assertEqual(response.status_code, 200, response.data)
            rendered = str(response.data)
            self.assertNotIn(other_household.title, rendered)
            self.assertNotIn(private.name, rendered)
            return {row["id"] for row in response.data}

        self.assertEqual(ids(), {visible.pk})
        self.assertEqual(client.get(f"/api/cuaderno/services/{denied.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/cuaderno/services/{other_household.pk}/").status_code, 404)
        with scopes_disabled():
            private.shared.add(guest)
        self.assertEqual(ids(), {visible.pk, denied.pk})
        self.assertEqual(client.get(f"/api/cuaderno/services/{denied.pk}/").status_code, 200)
        with scopes_disabled():
            private.shared.remove(guest)
        self.assertEqual(ids(), {visible.pk})
        self.assertEqual(client.get(f"/api/cuaderno/services/{denied.pk}/").status_code, 404)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentServiceProductionTests(ServiceFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def test_concurrent_same_key_produces_once(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        location = InventoryLocation.objects.create(
            space=self.space, household=self.household, name="Concurrencia", created_by=self.user
        )
        entry = InventoryEntry.objects.create(
            space=self.space, inventory_location=location, food=self.food, unit=self.kg,
            amount=Decimal("10"), created_by=self.user,
        )
        _, plan = self.create_plan(covers=20)
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        barrier = Barrier(2)
        guard = Lock()
        statuses = []

        def worker():
            close_old_connections()
            result = None
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                client = APIClient()
                client.force_login(user)
                barrier.wait(timeout=10)
                response = client.post(
                    f"/api/cuaderno/services/{plan.pk}/",
                    {"action": "produce", "idempotency_key": "concurrent-service"},
                    format="json",
                )
                result = response.status_code
            finally:
                connections.close_all()
            with guard:
                statuses.append(result)

        threads = [Thread(target=worker), Thread(target=worker)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "La carrera no terminó")
        self.assertEqual(statuses, [200, 200])
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("6"))
        self.assertEqual(StockMovement.objects.count(), 1)
