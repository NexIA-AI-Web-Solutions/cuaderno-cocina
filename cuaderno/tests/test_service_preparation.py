import json
import re
from datetime import datetime
from decimal import Decimal
from threading import Barrier, Lock, Thread
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection, connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from cookbook.models import Food, Household, Ingredient, InventoryEntry, Recipe, SearchFields, Space, Step, UserSpace
from cuaderno.models import ServicePlan, ServicePreparationItem, SpaceProfile
from cuaderno.tests.test_services import ServiceFixtureMixin


REVISION = re.compile(r"^[0-9a-f]{64}$")
ITEM_KEYS = {
    "id",
    "source_step_id",
    "position",
    "recipe_id",
    "name",
    "instruction",
    "checked",
    "checked_at",
    "updated_by",
}


class ServicePreparationGraphTests(SimpleTestCase):
    def test_falsey_non_object_graphs_are_rejected_not_treated_as_empty(self):
        from cuaderno.services.preparation import _ordered_recipe_ids
        for graph in ([], "", 0, False, None):
            with self.subTest(graph=graph), self.assertRaises(ValidationError):
                _ordered_recipe_ids({"recipe_id": 1, "recipe_graph": graph})

    def test_preparation_does_not_introduce_a_lower_limit_than_native_graph(self):
        from cuaderno.services.preparation import _ordered_recipe_ids
        for count in (500, 501, 1001):
            with self.subTest(count=count):
                children = list(range(2, count + 1))
                result = _ordered_recipe_ids({"recipe_id": 1, "recipe_graph": {"1": children}})
                self.assertEqual(result, list(range(1, count + 1)))
        with self.assertRaises(ValidationError):
            _ordered_recipe_ids({"recipe_id": 1, "recipe_graph": {"1": list(range(2, 1003))}})


class PreparationFixtureMixin(ServiceFixtureMixin):
    def setUp(self):
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
        super().setUp()
        with scopes_disabled():
            self.root_step = self.recipe.steps.get()
            self.root_step.name = "Preparar arroz"
            self.root_step.instruction = "Lavar el arroz y disponer la marmita."
            self.root_step.order = 20
            self.root_step.save(update_fields=["name", "instruction", "order"])

    def preparation_url(self, plan):
        return f"/api/cuaderno/services/{plan.pk}/preparation/"

    def assert_json_response(self, response):
        self.assertEqual(
            response.get("Content-Type", "").split(";", 1)[0],
            "application/json",
            response.content[:500],
        )
        return response

    def preparation(self, plan, *, user=None):
        return self.assert_json_response(
            self.client_for(user or self.user).get(self.preparation_url(plan))
        )

    def update_preparation(self, plan, item, checked, revision, *, user=None):
        return self.assert_json_response(
            self.client_for(user or self.user).put(
                self.preparation_url(plan),
                {"item": item, "checked": checked, "revision": revision},
                format="json",
            )
        )

    def confirm(self, *, user=None, **kwargs):
        _, plan = self.create_plan(user=user, **kwargs)
        response = self.transition(plan, "confirm", user=user)
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        plan.refresh_from_db()
        return plan

    def assert_preparation_envelope(self, payload, plan, can_edit=True):
        self.assertEqual(set(payload), {"service_id", "state", "can_edit", "revision", "items"})
        self.assertEqual(payload["service_id"], plan.pk)
        self.assertEqual(payload["state"], plan.state)
        self.assertIs(payload["can_edit"], can_edit)
        self.assertRegex(payload["revision"], REVISION)
        for position, item in enumerate(payload["items"]):
            self.assertEqual(set(item), ITEM_KEYS)
            self.assertEqual(item["position"], position)

    def add_nested_recipe(self):
        with scopes_disabled():
            child = Recipe.objects.create(
                space=self.space,
                name="Salsa del servicio",
                servings=Decimal("10"),
                created_by=self.user,
            )
            child_step = Step.objects.create(
                space=self.space,
                name="Preparar salsa",
                instruction="Triturar y reservar la salsa.",
                order=5,
            )
            child.steps.add(child_step)
            child_food = Food.objects.create(space=self.space, name="Salsa preparada", recipe=child)
            self.root_step.ingredients.add(Ingredient.objects.create(
                space=self.space,
                food=child_food,
                unit=self.kg,
                amount=Decimal("1"),
            ))
        return child, child_step


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServicePreparationTests(PreparationFixtureMixin, TestCase):
    def test_legacy_confirmed_service_is_read_only_without_backfill_or_get_writes(self):
        _, plan = self.create_plan()
        plan.state = ServicePlan.CONFIRMED
        plan.confirmed_at = timezone.now()
        plan.snapshot = {"recipe_id": self.recipe.pk, "recipe_graph": {str(self.recipe.pk): []}}
        plan.save(update_fields=["state", "confirmed_at", "snapshot"])

        first = self.preparation(plan)
        self.assertEqual(first.status_code, 200, first.data)
        self.assert_preparation_envelope(first.data, plan, can_edit=False)
        self.assertEqual(first.data["items"], [])
        self.assertEqual(self.preparation(plan).data, first.data)
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        self.assertEqual(self.preparation(plan).data, first.data)
        self.assertEqual(ServicePreparationItem.objects.filter(service=plan).count(), 0)

    def test_failed_seed_after_persisting_items_rolls_back_entire_confirmation(self):
        from cuaderno.services.preparation import seed_preparation
        from cuaderno.services.service_plans import confirm_service_plan

        _, plan = self.create_plan()
        original_snapshot = json.dumps(plan.snapshot, sort_keys=True)

        def partial_seed_then_fail(fresh_plan, user):
            created = seed_preparation(fresh_plan, user)
            self.assertEqual(len(created), 1)
            self.assertEqual(ServicePreparationItem.objects.filter(service=plan).count(), 1)
            raise RuntimeError("synthetic failure after real SQL insert")

        with scopes_disabled(), patch("cuaderno.services.preparation.seed_preparation", partial_seed_then_fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                confirm_service_plan(plan, self.user)
        plan.refresh_from_db()
        self.assertEqual(plan.state, ServicePlan.DRAFT)
        self.assertIsNone(plan.confirmed_at)
        self.assertEqual(json.dumps(plan.snapshot, sort_keys=True), original_snapshot)
        self.assertEqual(ServicePreparationItem.objects.filter(service=plan).count(), 0)

    def test_draft_is_explicitly_read_only_and_has_no_generated_items(self):
        _, plan = self.create_plan()

        response = self.preparation(plan)

        self.assertEqual(response.status_code, 200, response.data)
        self.assert_preparation_envelope(response.data, plan, can_edit=False)
        self.assertEqual(response.data["items"], [])
        rejected = self.update_preparation(plan, 1, True, response.data["revision"])
        self.assertEqual(rejected.status_code, 400)

    def test_confirmation_freezes_root_and_nested_steps_in_deterministic_order_with_bounded_get(self):
        child, child_step = self.add_nested_recipe()
        with scopes_disabled():
            extra_steps = [Step.objects.create(
                space=self.space,
                name=f"Paso {index:02d}",
                instruction=f"Instrucción persistida {index:02d}.",
                order=30 + index,
            ) for index in range(18)]
            self.recipe.steps.add(*extra_steps)
        plan = self.confirm()

        client = self.client_for(self.user)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(self.preparation_url(plan))

        self.assert_json_response(response)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertLessEqual(len(captured), 14, [query["sql"] for query in captured])
        self.assert_preparation_envelope(response.data, plan)
        expected = [
            (self.recipe.pk, self.root_step.pk, "Preparar arroz", "Lavar el arroz y disponer la marmita."),
            *[(self.recipe.pk, step.pk, step.name, step.instruction) for step in extra_steps],
            (child.pk, child_step.pk, "Preparar salsa", "Triturar y reservar la salsa."),
        ]
        actual = [
            (item["recipe_id"], item["source_step_id"], item["name"], item["instruction"])
            for item in response.data["items"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(self.preparation(plan).data["items"], response.data["items"])

    def test_frozen_copy_survives_native_step_edit_and_delete(self):
        plan = self.confirm()
        with scopes_disabled():
            self.root_step.name = "Texto cambiado después"
            self.root_step.instruction = "No debe sustituir el texto congelado."
            self.root_step.save(update_fields=["name", "instruction"])

        item = self.preparation(plan).data["items"][0]
        self.assertEqual(item["name"], "Preparar arroz")
        self.assertEqual(item["instruction"], "Lavar el arroz y disponer la marmita.")
        self.assertEqual(item["source_step_id"], self.root_step.pk)

        edited = self.preparation(plan).data["items"][0]
        self.assertEqual(edited["name"], "Preparar arroz")
        self.assertEqual(edited["instruction"], "Lavar el arroz y disponer la marmita.")
        self.assertEqual(edited["source_step_id"], self.root_step.pk)

        with scopes_disabled():
            self.root_step.delete()
        deleted = self.preparation(plan).data["items"][0]
        self.assertEqual(deleted["name"], item["name"])
        self.assertEqual(deleted["instruction"], item["instruction"])
        self.assertIsNone(deleted["source_step_id"])

    def test_check_and_uncheck_persist_author_and_timestamp_across_reload(self):
        plan = self.confirm()
        initial = self.preparation(plan).data
        item_id = initial["items"][0]["id"]

        checked = self.update_preparation(plan, item_id, True, initial["revision"])

        self.assertEqual(checked.status_code, 200, checked.data)
        checked_item = checked.data["items"][0]
        self.assertIs(checked_item["checked"], True)
        self.assertEqual(checked_item["updated_by"], self.user.pk)
        self.assertIsNotNone(checked_item["checked_at"])
        checked_at = datetime.fromisoformat(checked_item["checked_at"])
        self.assertIsNotNone(checked_at.utcoffset())
        self.assertNotEqual(checked.data["revision"], initial["revision"])
        self.assertEqual(self.preparation(plan).data, checked.data)

        unchecked = self.update_preparation(plan, item_id, False, checked.data["revision"], user=self.helper)
        self.assertEqual(unchecked.status_code, 200, unchecked.data)
        unchecked_item = unchecked.data["items"][0]
        self.assertIs(unchecked_item["checked"], False)
        self.assertIsNone(unchecked_item["checked_at"])
        self.assertEqual(unchecked_item["updated_by"], self.helper.pk)
        self.assertNotEqual(unchecked.data["revision"], initial["revision"])
        self.assertNotEqual(unchecked.data["revision"], checked.data["revision"])

    def test_put_requires_strict_item_boolean_and_lowercase_revision(self):
        plan = self.confirm()
        current = self.preparation(plan).data
        item_id = current["items"][0]["id"]
        client = self.client_for(self.user)
        missing = client.put(self.preparation_url(plan), {"item": item_id, "checked": True}, format="json")
        self.assert_json_response(missing)
        self.assertEqual(missing.status_code, 428)

        malformed = [
            {"checked": True, "revision": current["revision"]},
            {"item": item_id, "revision": current["revision"]},
            {"item": True, "checked": True, "revision": current["revision"]},
            {"item": item_id, "checked": 1, "revision": current["revision"]},
            {"item": item_id, "checked": "true", "revision": current["revision"]},
            {"item": item_id, "checked": True, "revision": current["revision"].upper()},
            {"item": item_id, "checked": True, "revision": "0" * 63},
            {"item": item_id, "checked": True, "revision": None},
        ]
        for payload in malformed:
            with self.subTest(payload=payload):
                response = client.put(self.preparation_url(plan), payload, format="json")
                self.assert_json_response(response)
                self.assertEqual(response.status_code, 400)
        for payload in (None, [], [{}], "body"):
            with self.subTest(non_object=payload):
                response = client.generic(
                    "PUT",
                    self.preparation_url(plan),
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assert_json_response(response)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.preparation(plan).data, current)

    def test_reconfirm_is_idempotent_without_duplicate_items_or_revision_change(self):
        plan = self.confirm()
        initial = self.preparation(plan).data

        confirmed_again = self.transition(plan, "confirm")

        self.assertEqual(confirmed_again.status_code, 200, confirmed_again.data)
        after = self.preparation(plan).data
        self.assertEqual(after, initial)
        self.assertEqual(
            [(item["id"], item["position"]) for item in after["items"]],
            [(item["id"], item["position"]) for item in initial["items"]],
        )

    def test_stale_revision_conflicts_and_current_noop_has_no_metadata_or_revision_change(self):
        plan = self.confirm()
        initial = self.preparation(plan).data
        item = initial["items"][0]

        noop = self.update_preparation(plan, item["id"], False, initial["revision"])
        self.assertEqual(noop.status_code, 200, noop.data)
        self.assertEqual(noop.data, initial)

        changed = self.update_preparation(plan, item["id"], True, initial["revision"])
        self.assertEqual(changed.status_code, 200, changed.data)
        stale = self.update_preparation(plan, item["id"], False, initial["revision"])
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.preparation(plan).data, changed.data)

    def test_checklist_updates_leave_service_snapshot_and_stock_byte_identical(self):
        plan = self.confirm()
        before = self.preparation(plan).data
        plan.refresh_from_db()
        snapshot = json.dumps(plan.snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with scopes_disabled():
            stock = list(InventoryEntry.objects.filter(space=self.space).order_by("pk").values_list("pk", "amount"))

        response = self.update_preparation(plan, before["items"][0]["id"], True, before["revision"])

        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        self.assertEqual(json.dumps(plan.snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")), snapshot)
        with scopes_disabled():
            self.assertEqual(
                list(InventoryEntry.objects.filter(space=self.space).order_by("pk").values_list("pk", "amount")),
                stock,
            )

    def test_two_services_from_the_same_native_step_have_independent_state(self):
        first = self.confirm(title="Primer servicio")
        second = self.confirm(title="Segundo servicio")
        first_payload = self.preparation(first).data
        second_payload = self.preparation(second).data
        self.assertNotEqual(first_payload["items"][0]["id"], second_payload["items"][0]["id"])
        cross_service = self.update_preparation(
            first,
            second_payload["items"][0]["id"],
            True,
            first_payload["revision"],
        )
        self.assertEqual(cross_service.status_code, 404)

        changed = self.update_preparation(
            first,
            first_payload["items"][0]["id"],
            True,
            first_payload["revision"],
        )

        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertIs(self.preparation(first).data["items"][0]["checked"], True)
        self.assertIs(self.preparation(second).data["items"][0]["checked"], False)

    def test_produced_and_cancelled_checklists_are_read_only(self):
        produced = self.confirm(title="Producido")
        cancelled = self.confirm(title="Cancelado")
        self.assertEqual(self.transition(produced, "produce", key="prep-produced").status_code, 200)
        self.assertEqual(self.transition(cancelled, "cancel").status_code, 200)
        for plan in (produced, cancelled):
            plan.refresh_from_db()
            payload = self.preparation(plan)
            self.assertEqual(payload.status_code, 200, payload.data)
            self.assert_preparation_envelope(payload.data, plan, can_edit=False)
            rejected = self.update_preparation(
                plan,
                payload.data["items"][0]["id"],
                True,
                payload.data["revision"],
            )
            self.assertEqual(rejected.status_code, 400)

    def test_permissions_enforce_edition_household_space_and_guest_boundaries(self):
        plan = self.confirm()
        helper = self.preparation(plan, user=self.helper)
        outsider = self.preparation(plan, user=self.outsider)
        self.assertEqual(helper.status_code, 200, helper.data)
        self.assertIs(helper.data["can_edit"], True)
        self.assertEqual(outsider.status_code, 404)
        owner_state = self.preparation(plan).data
        item_id = owner_state["items"][0]["id"]
        revision = owner_state["revision"]
        self.assertEqual(self.update_preparation(plan, item_id, True, revision, user=self.outsider).status_code, 404)

        guest = self.make_user("service-guest", "guest", self.household)
        self.assertEqual(self.preparation(plan, user=guest).status_code, 403)
        self.assertEqual(self.update_preparation(plan, item_id, True, revision, user=guest).status_code, 403)

        with scopes_disabled():
            other_space = Space.objects.create(name="Otro espacio")
            other_household = Household.objects.create(space=other_space, name="Otro hogar")
            other_user = get_user_model().objects.create_user(username="other-space-prep", password="local-test-only")
            membership = UserSpace.objects.create(
                user=other_user,
                space=other_space,
                household=other_household,
                active=True,
            )
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            other_space.created_by = other_user
            other_space.save(update_fields=["created_by"])
        self.assertEqual(self.preparation(plan, user=other_user).status_code, 404)
        self.assertEqual(self.update_preparation(plan, item_id, True, revision, user=other_user).status_code, 404)

        self.profile.edition = SpaceProfile.ESENCIAL
        self.profile.save(update_fields=["edition"])
        self.assertEqual(self.preparation(plan).status_code, 403)
        self.assertEqual(self.update_preparation(plan, item_id, True, revision).status_code, 403)
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        self.assertEqual(self.preparation(plan).status_code, 200)
        self.assertEqual(self.preparation(plan).data, owner_state)

    def test_private_recipe_graph_is_rechecked_after_confirmation(self):
        child, _ = self.add_nested_recipe()
        plan = self.confirm()
        self.assertEqual(self.preparation(plan, user=self.helper).status_code, 200)
        self.assertEqual(self.preparation(plan, user=self.admin).status_code, 200)

        child.private = True
        child.save(update_fields=["private"])

        owner_state = self.preparation(plan).data
        item_id = owner_state["items"][0]["id"]
        revision = owner_state["revision"]
        self.assertEqual(self.preparation(plan, user=self.helper).status_code, 404)
        self.assertEqual(self.preparation(plan, user=self.admin).status_code, 404)
        self.assertEqual(self.preparation(plan, user=self.outsider).status_code, 404)
        self.assertEqual(self.update_preparation(plan, item_id, True, revision, user=self.helper).status_code, 404)
        self.assertEqual(self.update_preparation(plan, item_id, True, revision, user=self.admin).status_code, 404)
        self.assertEqual(self.preparation(plan).data, owner_state)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentServicePreparationTests(PreparationFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def test_two_writers_with_one_revision_yield_one_success_and_one_conflict(self):
        plan = self.confirm()
        initial = self.preparation(plan).data
        item_id = initial["items"][0]["id"]
        barrier = Barrier(2)
        guard = Lock()
        statuses = []

        def worker():
            close_old_connections()
            status = None
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                client = APIClient()
                client.force_login(user)
                barrier.wait(timeout=10)
                response = client.put(
                    self.preparation_url(plan),
                    {"item": item_id, "checked": True, "revision": initial["revision"]},
                    format="json",
                )
                status = response.status_code
            finally:
                connections.close_all()
            with guard:
                statuses.append(status)

        threads = [Thread(target=worker), Thread(target=worker)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "La carrera no terminó")
        self.assertEqual(len(statuses), 2)
        self.assertNotIn(None, statuses)
        self.assertEqual(sorted(statuses), [200, 409])
        final = self.preparation(plan).data
        self.assertIs(final["items"][0]["checked"], True)
        self.assertNotEqual(final["revision"], initial["revision"])
