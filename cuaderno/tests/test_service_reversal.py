"""Atomic, idempotent reversal contracts for produced services."""

from copy import deepcopy
from decimal import Decimal
from threading import Barrier, Lock, Thread

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Household,
    InventoryEntry,
    InventoryLocation,
    InventoryLog,
    SearchFields,
    Space,
    UserSpace,
)
from cuaderno.models import ServicePlan, SpaceProfile, StockMovement
from cuaderno.tests.test_services import ServiceFixtureMixin


MAX_STORED_QUANTITY = Decimal("9999999999999999.9999999999999999")


class ServiceReversalContractMixin(ServiceFixtureMixin):
    def setUp(self):
        self.assertEqual(connections["default"].vendor, "postgresql")
        with scopes_disabled():
            # Prior TransactionTestCase modules flush data-migration rows.
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
        super().setUp()

    def _integral(self):
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])

    def _produce_two_lots(self, *, production_key, actor=None, title=None):
        actor = actor or self.user
        self._integral()
        with scopes_disabled():
            suffix = str(InventoryLocation.objects.filter(space=self.space).count())
            location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name=f"Reversal lots {suffix}",
                created_by=actor,
            )
            entries = [
                InventoryEntry.objects.create(
                    space=self.space,
                    inventory_location=location,
                    food=self.food,
                    unit=self.kg,
                    amount=amount,
                    created_by=actor,
                )
                for amount in (Decimal("2"), Decimal("8"))
            ]
        _, plan = self.create_plan(
            user=actor,
            title=title or f"Reverse {production_key}",
            covers=20,
        )
        confirmed = self.transition(plan, "confirm", user=actor)
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        produced = self.transition(plan, "produce", user=actor, key=production_key)
        self.assertEqual(produced.status_code, 200, produced.data)
        self.assertEqual(len(produced.data["movement_ids"]), 2)
        with scopes_disabled():
            plan.refresh_from_db()
            for entry in entries:
                entry.refresh_from_db()
        self.assertEqual([entry.amount for entry in entries], [Decimal("0"), Decimal("6")])
        return plan, entries, list(produced.data["movement_ids"])

    def _reverse(self, plan, key, *, user=None):
        return self.transition(plan, "reverse", user=user, key=key)

    def _effects(self, plan):
        with scopes_disabled():
            plan.refresh_from_db()
            entries = list(
                InventoryEntry.objects.filter(space=self.space)
                .order_by("pk")
                .values("id", "amount", "inventory_location_id")
            )
            movements = list(
                StockMovement.objects.filter(space=self.space)
                .order_by("pk")
                .values(
                    "id",
                    "entry_id",
                    "kind",
                    "quantity",
                    "balance_after",
                    "reverses_id",
                    "metadata_snapshot",
                    "created_by_id",
                )
            )
            logs = list(
                InventoryLog.objects.filter(space=self.space)
                .order_by("pk")
                .values(
                    "id",
                    "entry_id",
                    "booking_type",
                    "old_amount",
                    "new_amount",
                    "note",
                )
            )
        return {
            "entries": entries,
            "state": plan.state,
            "snapshot": deepcopy(plan.snapshot),
            "produced_at": plan.produced_at,
            "produced_key": plan.produced_key,
            "movements": movements,
            "logs": logs,
        }

    def _set_movement_ids(self, plan, movement_ids):
        with scopes_disabled():
            plan.refresh_from_db()
            snapshot = deepcopy(plan.snapshot)
            snapshot["production"]["movement_ids"] = movement_ids
            plan.snapshot = snapshot
            plan.save(update_fields=["snapshot"])

    def _set_reversal_audit(self, plan, audit):
        with scopes_disabled():
            plan.refresh_from_db()
            snapshot = deepcopy(plan.snapshot)
            snapshot["production"]["reversal"] = audit
            plan.snapshot = snapshot
            plan.save(update_fields=["snapshot"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServiceReversalTests(ServiceReversalContractMixin, TestCase):
    def test_integral_reversal_restores_every_lot_and_only_appends_audit_snapshot(self):
        plan, entries, original_ids = self._produce_two_lots(
            production_key="two-lot-production"
        )
        before = self._effects(plan)
        original_rows = deepcopy(before["movements"])

        response = self._reverse(plan, "two-lot-reversal")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], ServicePlan.CANCELLED)
        reversal_ids = response.data["reversal_movement_ids"]
        self.assertEqual(len(reversal_ids), 2)
        self.assertTrue(set(reversal_ids).isdisjoint(original_ids))
        with scopes_disabled():
            plan.refresh_from_db()
            for entry in entries:
                entry.refresh_from_db()
            originals_after = list(
                StockMovement.objects.filter(pk__in=original_ids)
                .order_by("pk")
                .values(
                    "id",
                    "entry_id",
                    "kind",
                    "quantity",
                    "balance_after",
                    "reverses_id",
                    "metadata_snapshot",
                    "created_by_id",
                )
            )
            reversals = list(
                StockMovement.objects.filter(pk__in=reversal_ids).order_by("pk")
            )
        self.assertEqual([entry.amount for entry in entries], [Decimal("2"), Decimal("8")])
        self.assertEqual(originals_after, original_rows)
        self.assertEqual([row.kind for row in reversals], [StockMovement.RECEIPT] * 2)
        self.assertEqual(
            {row.reverses_id for row in reversals},
            set(original_ids),
        )
        self.assertEqual(plan.produced_at, before["produced_at"])
        self.assertEqual(plan.produced_key, before["produced_key"])

        after_snapshot = deepcopy(plan.snapshot)
        reversal_audit = after_snapshot["production"].pop("reversal")
        self.assertEqual(after_snapshot, before["snapshot"])
        self.assertEqual(
            set(reversal_audit),
            {
                "key_sha256",
                "reversed_at",
                "reversed_by",
                "original_movement_ids",
                "movement_ids",
            },
        )
        self.assertRegex(reversal_audit["key_sha256"], r"^[0-9a-f]{64}$")
        self.assertIsInstance(reversal_audit["reversed_at"], str)
        self.assertEqual(reversal_audit["reversed_by"], self.user.pk)
        self.assertEqual(reversal_audit["original_movement_ids"], original_ids)
        self.assertEqual(reversal_audit["movement_ids"], reversal_ids)

    def test_same_reversal_key_replays_and_a_different_key_conflicts_without_writes(self):
        plan, _, _ = self._produce_two_lots(production_key="idempotent-production")
        first = self._reverse(plan, "idempotent-reversal")
        self.assertEqual(first.status_code, 200, first.data)
        after_first = self._effects(plan)

        replay = self._reverse(plan, "idempotent-reversal")
        conflict = self._reverse(plan, "different-reversal")

        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(
            replay.data["reversal_movement_ids"],
            first.data["reversal_movement_ids"],
        )
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(self._effects(plan), after_first)

    def test_same_reversal_key_cannot_be_reused_by_another_service(self):
        first, _, _ = self._produce_two_lots(production_key="cross-key-production-one")
        reversed_first = self._reverse(first, "space-wide-reversal-key")
        self.assertEqual(reversed_first.status_code, 200, reversed_first.data)
        _, second = self.create_plan(title="Second reversal-key owner", covers=20)
        self.assertEqual(self.transition(second, "confirm").status_code, 200)
        produced_second = self.transition(
            second, "produce", key="cross-key-production-two"
        )
        self.assertEqual(produced_second.status_code, 200, produced_second.data)
        before_second = self._effects(second)

        response = self._reverse(second, "space-wide-reversal-key")

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(self._effects(second), before_second)

    def test_reversed_service_is_terminal_and_later_actions_do_not_touch_stock(self):
        plan, _, _ = self._produce_two_lots(production_key="terminal-production")
        reversed_response = self._reverse(plan, "terminal-reversal")
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        terminal = self._effects(plan)

        confirm = self.transition(plan, "confirm")
        produce = self.transition(plan, "produce", key="produce-after-reversal")
        cancel = self.transition(plan, "cancel")

        self.assertEqual(confirm.status_code, 400, confirm.data)
        self.assertEqual(produce.status_code, 400, produce.data)
        self.assertEqual(cancel.status_code, 200, cancel.data)
        self.assertEqual(cancel.data["state"], ServicePlan.CANCELLED)
        self.assertEqual(self._effects(plan), terminal)

    def test_professional_reversal_has_no_movements_even_after_edition_upgrade(self):
        with scopes_disabled():
            location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Professional unchanged stock",
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
        _, plan = self.create_plan(title="Professional reverse")
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        produced = self.transition(plan, "produce", key="professional-before-upgrade")
        self.assertEqual(produced.status_code, 200, produced.data)
        self.assertEqual(produced.data["movement_ids"], [])
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])

        response = self._reverse(plan, "professional-reversal")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], ServicePlan.CANCELLED)
        self.assertEqual(response.data["reversal_movement_ids"], [])
        self.assertFalse(response.data["stock_changed"])
        with scopes_disabled():
            entry.refresh_from_db()
            plan.refresh_from_db()
            self.assertEqual(StockMovement.objects.filter(space=self.space).count(), 0)
        self.assertEqual(entry.amount, Decimal("10"))
        self.assertEqual(plan.snapshot["production"]["edition"], SpaceProfile.PROFESIONAL)

    def test_reversal_rechecks_household_space_group_and_private_recipe_acl(self):
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.save(update_fields=["private"])
            self.recipe.shared.add(self.helper)
        plan, _, _ = self._produce_two_lots(
            production_key="acl-production",
            actor=self.helper,
        )
        with scopes_disabled():
            self.recipe.shared.remove(self.helper)
            guest = self.make_user("service-reversal-guest", "guest", self.household)
            foreign_space = Space.objects.create(name="Foreign reversal space")
            foreign_household = Household.objects.create(
                space=foreign_space, name="Foreign reversal kitchen"
            )
            foreign_user = get_user_model().objects.create_user(
                username="service-reversal-foreign", password="synthetic-only"
            )
            foreign_membership = UserSpace.objects.create(
                user=foreign_user,
                space=foreign_space,
                household=foreign_household,
                active=True,
            )
            foreign_membership.groups.add(Group.objects.get_or_create(name="user")[0])
            foreign_space.created_by = foreign_user
            foreign_space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(
                space=foreign_space, edition=SpaceProfile.INTEGRAL
            )
        cache.clear()
        before = self._effects(plan)

        attempts = (
            (self.helper, 404),
            (self.outsider, 404),
            (self.admin, 404),
            (guest, 403),
            (foreign_user, 404),
        )
        for index, (user, expected) in enumerate(attempts):
            with self.subTest(user=user.username):
                response = self._reverse(plan, f"acl-reversal-{index}", user=user)
                self.assertEqual(
                    response.status_code,
                    expected,
                    getattr(response, "data", response.content),
                )
                self.assertEqual(self._effects(plan), before)

        # Remove recipe privacy as the reason for denial: the other Household
        # and the other Space must still fail independently.
        with scopes_disabled():
            self.recipe.private = False
            self.recipe.save(update_fields=["private"])
        cache.clear()
        for index, user in enumerate((self.outsider, foreign_user)):
            with self.subTest(boundary=user.username):
                response = self._reverse(
                    plan, f"boundary-reversal-{index}", user=user
                )
                self.assertEqual(
                    response.status_code,
                    404,
                    getattr(response, "data", response.content),
                )
                self.assertEqual(self._effects(plan), before)

    def test_invalid_reversal_keys_are_rejected_without_effects(self):
        plan, _, _ = self._produce_two_lots(production_key="invalid-key-production")
        before = self._effects(plan)

        for key in (None, "", [], "x" * 129):
            with self.subTest(key=key):
                response = self._reverse(plan, key)
                self.assertEqual(
                    response.status_code,
                    400,
                    getattr(response, "data", response.content),
                )
                self.assertEqual(self._effects(plan), before)

    def test_duplicate_original_movement_ids_fail_atomically(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="duplicate-snapshot-production"
        )
        self._set_movement_ids(plan, [*original_ids, original_ids[0]])
        before = self._effects(plan)

        response = self._reverse(plan, "duplicate-snapshot-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_missing_original_movement_fails_atomically(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="missing-snapshot-production"
        )
        self._set_movement_ids(plan, [original_ids[0], 9223372036854775807])
        before = self._effects(plan)

        response = self._reverse(plan, "missing-snapshot-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_movement_from_another_service_fails_atomically(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="foreign-movement-production-one"
        )
        _, other = self.create_plan(title="Foreign movement service", covers=20)
        self.assertEqual(self.transition(other, "confirm").status_code, 200)
        produced_other = self.transition(
            other, "produce", key="foreign-movement-production-two"
        )
        self.assertEqual(produced_other.status_code, 200, produced_other.data)
        other_ids = list(produced_other.data["movement_ids"])
        self.assertTrue(other_ids)
        self.assertNotEqual(plan.pk, other.pk)
        self._set_movement_ids(plan, [original_ids[0], other_ids[0]])
        before = self._effects(plan)

        response = self._reverse(plan, "foreign-movement-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_malformed_original_metadata_fails_atomically(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="metadata-production"
        )
        with scopes_disabled():
            StockMovement.objects.filter(pk=original_ids[1]).update(
                metadata_snapshot=["not", "an", "object"]
            )
        before = self._effects(plan)

        response = self._reverse(plan, "metadata-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_entry_moved_to_another_household_fails_atomically(self):
        plan, entries, _ = self._produce_two_lots(production_key="moved-entry-production")
        with scopes_disabled():
            moved_location = InventoryLocation.objects.create(
                space=self.space,
                household=self.other_household,
                name="Moved after production",
                created_by=self.outsider,
            )
            entries[1].inventory_location = moved_location
            entries[1].save(update_fields=["inventory_location", "updated_at"])
        before = self._effects(plan)

        response = self._reverse(plan, "moved-entry-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_late_storage_overflow_rolls_back_every_compensation(self):
        plan, entries, _ = self._produce_two_lots(production_key="overflow-production")
        with scopes_disabled():
            # The first lot can be restored; the second would overflow. The
            # enclosing service transaction must roll both operations back.
            entries[1].amount = MAX_STORED_QUANTITY
            entries[1].save(update_fields=["amount", "updated_at"])
        before = self._effects(plan)

        response = self._reverse(plan, "overflow-reversal")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_replay_rejects_nonexistent_persisted_reversal_movements(self):
        plan, _, _ = self._produce_two_lots(
            production_key="missing-replay-production"
        )
        reversed_response = self._reverse(plan, "missing-replay-reversal")
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        with scopes_disabled():
            plan.refresh_from_db()
            audit = deepcopy(plan.snapshot["production"]["reversal"])
        audit["movement_ids"] = [9223372036854775806, 9223372036854775807]
        self._set_reversal_audit(plan, audit)
        before = self._effects(plan)

        replay = self._reverse(plan, "missing-replay-reversal")

        self.assertEqual(replay.status_code, 400, replay.data)
        self.assertEqual(self._effects(plan), before)

    def test_replay_rejects_original_ids_that_differ_from_frozen_production(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="changed-originals-production"
        )
        reversed_response = self._reverse(plan, "changed-originals-reversal")
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        with scopes_disabled():
            plan.refresh_from_db()
            audit = deepcopy(plan.snapshot["production"]["reversal"])
        audit["original_movement_ids"] = list(reversed(original_ids))
        self._set_reversal_audit(plan, audit)
        before = self._effects(plan)

        replay = self._reverse(plan, "changed-originals-reversal")

        self.assertEqual(replay.status_code, 400, replay.data)
        self.assertEqual(self._effects(plan), before)

    def test_replay_rejects_original_movements_masquerading_as_reversals(self):
        plan, _, original_ids = self._produce_two_lots(
            production_key="wrong-reversal-production"
        )
        reversed_response = self._reverse(plan, "wrong-reversal-key")
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        with scopes_disabled():
            plan.refresh_from_db()
            audit = deepcopy(plan.snapshot["production"]["reversal"])
        audit["movement_ids"] = list(original_ids)
        self._set_reversal_audit(plan, audit)
        before = self._effects(plan)

        replay = self._reverse(plan, "wrong-reversal-key")

        self.assertEqual(replay.status_code, 400, replay.data)
        self.assertEqual(self._effects(plan), before)

    def test_replay_rejects_reversal_movements_owned_by_another_service(self):
        plan, _, _ = self._produce_two_lots(
            production_key="foreign-replay-production-one"
        )
        first_reversal = self._reverse(plan, "foreign-replay-reversal-one")
        self.assertEqual(first_reversal.status_code, 200, first_reversal.data)

        _, other = self.create_plan(title="Foreign replay owner", covers=20)
        self.assertEqual(self.transition(other, "confirm").status_code, 200)
        produced_other = self.transition(
            other, "produce", key="foreign-replay-production-two"
        )
        self.assertEqual(produced_other.status_code, 200, produced_other.data)
        reversed_other = self._reverse(other, "foreign-replay-reversal-two")
        self.assertEqual(reversed_other.status_code, 200, reversed_other.data)

        with scopes_disabled():
            plan.refresh_from_db()
            audit = deepcopy(plan.snapshot["production"]["reversal"])
        audit["movement_ids"] = list(reversed_other.data["reversal_movement_ids"])
        self._set_reversal_audit(plan, audit)
        before = self._effects(plan)

        replay = self._reverse(plan, "foreign-replay-reversal-one")

        self.assertEqual(replay.status_code, 400, replay.data)
        self.assertEqual(self._effects(plan), before)

    def test_legacy_professional_service_without_household_can_be_reversed(self):
        _, plan = self.create_plan(title="Legacy professional without household")
        self.assertEqual(self.transition(plan, "confirm").status_code, 200)
        produced = self.transition(plan, "produce", key="legacy-professional-production")
        self.assertEqual(produced.status_code, 200, produced.data)
        self.assertEqual(produced.data["movement_ids"], [])
        with scopes_disabled():
            plan.household = None
            plan.save(update_fields=["household"])
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])

        response = self._reverse(plan, "legacy-professional-reversal")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["state"], ServicePlan.CANCELLED)
        self.assertEqual(response.data["reversal_movement_ids"], [])
        self.assertFalse(response.data["stock_changed"])
        with scopes_disabled():
            plan.refresh_from_db()
            self.assertEqual(StockMovement.objects.filter(space=self.space).count(), 0)
        audit = plan.snapshot["production"]["reversal"]
        self.assertEqual(audit["original_movement_ids"], [])
        self.assertEqual(audit["movement_ids"], [])
        self.assertEqual(plan.snapshot["production"]["edition"], SpaceProfile.PROFESIONAL)

    def test_replay_rejects_non_object_reversal_audit_without_writes(self):
        plan, _, _ = self._produce_two_lots(
            production_key="non-object-audit-production"
        )
        reversed_response = self._reverse(plan, "non-object-audit-reversal")
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        with scopes_disabled():
            plan.refresh_from_db()
            valid_snapshot = deepcopy(plan.snapshot)

        for malformed in (["not", "an", "object"], None):
            with self.subTest(malformed=malformed):
                snapshot = deepcopy(valid_snapshot)
                snapshot["production"]["reversal"] = malformed
                with scopes_disabled():
                    plan.snapshot = snapshot
                    plan.save(update_fields=["snapshot"])
                before = self._effects(plan)

                replay = self._reverse(plan, "non-object-audit-reversal")

                self.assertEqual(replay.status_code, 400, replay.data)
                self.assertEqual(self._effects(plan), before)

    def test_entry_unit_changed_after_production_cannot_reinterpret_frozen_quantity(self):
        plan, entries, _ = self._produce_two_lots(production_key="changed-unit-production")
        with scopes_disabled():
            entries[1].unit = self.g
            entries[1].save(update_fields=["unit", "updated_at"])
        before = self._effects(plan)
        response = self._reverse(plan, "changed-unit-reversal")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self._effects(plan), before)

    def test_non_object_request_body_returns_validation_error_without_writes(self):
        plan, _, _ = self._produce_two_lots(production_key="invalid-body-production")
        before = self._effects(plan)
        client = self.client_for(self.user)
        for body in ('[]', 'null'):
            with self.subTest(body=body):
                response = client.generic(
                    "POST", f"/api/cuaderno/services/{plan.pk}/",
                    data=body, content_type="application/json",
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(self._effects(plan), before)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentServiceReversalTests(ServiceReversalContractMixin, TransactionTestCase):
    reset_sequences = True

    def test_concurrent_same_key_creates_one_complete_reversal(self):
        plan, entries, original_ids = self._produce_two_lots(
            production_key="concurrent-reversal-production"
        )
        barrier = Barrier(2)
        guard = Lock()
        outcomes = []

        def worker():
            close_old_connections()
            outcome = None
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                client = APIClient()
                client.force_login(user)
                barrier.wait(timeout=10)
                response = client.post(
                    f"/api/cuaderno/services/{plan.pk}/",
                    {
                        "action": "reverse",
                        "idempotency_key": "concurrent-service-reversal",
                    },
                    format="json",
                )
                outcome = (
                    response.status_code,
                    tuple(response.data.get("reversal_movement_ids", ())),
                )
            except Exception as exc:  # Surface thread failures deterministically.
                outcome = exc
            finally:
                connections.close_all()
            with guard:
                outcomes.append(outcome)

        threads = [Thread(target=worker, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertFalse(any(isinstance(item, Exception) for item in outcomes), outcomes)
        self.assertEqual([item[0] for item in outcomes], [200, 200])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        reversal_ids = outcomes[0][1]
        self.assertEqual(len(reversal_ids), 2)
        with scopes_disabled():
            plan.refresh_from_db()
            for entry in entries:
                entry.refresh_from_db()
            reversal_count = StockMovement.objects.filter(
                space=self.space, reverses_id__in=original_ids
            ).count()
        self.assertEqual(plan.state, ServicePlan.CANCELLED)
        self.assertEqual([entry.amount for entry in entries], [Decimal("2"), Decimal("8")])
        self.assertEqual(reversal_count, 2)
