from __future__ import annotations

import hashlib
import unittest
from copy import deepcopy
from decimal import Decimal
from unittest.mock import Mock, patch

if __package__:
    from . import release_service_reversal as subject
else:
    import release_service_reversal as subject


REVERSAL_KEY = "known-reversal-v1"


def waste_classification():
    return {
        "schema_version": 1,
        "policy": "declared_yield_estimate",
        "classification_only": True,
        "included_in_gross_needs": True,
        "additional_stock_movement": False,
        "coverage": "declared_yields_only",
        "status": "declared",
        "recorded_by": 7,
        "recorded_at": "2026-10-25T12:00:00+02:00",
        "lines": [
            {
                "ingredient_id": 21,
                "food_id": 22,
                "food_name": "Aceite DEMO",
                "unit_id": 23,
                "unit_name": "L",
                "quantity_basis": "net_usable",
                "yield_ratio": "0.8",
                "purchased_quantity": "0.5",
                "useful_quantity": "0.4",
                "waste_quantity": "0.1",
                "cause": "declared_yield",
            },
            {
                "ingredient_id": 21,
                "food_id": 22,
                "food_name": "Aceite DEMO",
                "unit_id": 23,
                "unit_name": "L",
                "quantity_basis": "net_usable",
                "yield_ratio": "0.8",
                "purchased_quantity": "1",
                "useful_quantity": "0.8",
                "waste_quantity": "0.2",
                "cause": "declared_yield",
            },
        ],
    }


def service_payload(edition="integral", state="cancelled", *, version=1):
    original = [31] if edition == "integral" else []
    reversed_ids = [32] if edition == "integral" else []
    production = {
        "produced_at": "2026-10-25T12:00:00+02:00",
        "edition": edition,
        "movement_ids": original,
        "stock_changed": edition == "integral",
    }
    if version == 2:
        production["schema_version"] = 2
        production["waste_classification"] = waste_classification()
    if state == "cancelled":
        production["reversal"] = {
            "key_sha256": hashlib.sha256(REVERSAL_KEY.encode("utf-8")).hexdigest(),
            "reversed_at": "2026-10-25T12:01:00+02:00",
            "reversed_by": 7,
            "original_movement_ids": original,
            "movement_ids": reversed_ids,
        }
    return {
        "id": 11,
        "title": subject.SERVICE_TITLE,
        "covers": "4",
        "service_date": subject.SERVICE_DATE,
        "state": state,
        "meal_plan": 4,
        "household": 5,
        "snapshot": {"recipe_id": 13, "needs": [], "production": production},
        "confirmed_at": "2026-10-25T11:00:00+02:00",
        "produced_at": "2026-10-25T12:00:00+02:00",
        "created_by": 7,
        "reversal_movement_ids": reversed_ids,
        "stock_changed": edition == "integral",
    }


class RecordingSession:
    def __init__(self, statuses=(404, 404), bodies=(b"{}", b"{}")):
        self.statuses = iter(statuses)
        self.bodies = iter(bodies)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return next(self.statuses), "application/json", next(self.bodies)


class RecoverySession:
    def __init__(self, produced, reversed_payload):
        self.produced = deepcopy(produced)
        self.reversed_payload = deepcopy(reversed_payload)
        self.stock = Decimal("4.6")
        self.calls = []

    def json(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "GET":
            return deepcopy(self.produced)
        action = kwargs.get("payload", {}).get("action")
        if action == "produce":
            replay = deepcopy(self.produced)
            replay.update(movement_ids=[31], stock_changed=True)
            return replay
        if action == "reverse":
            self.stock = Decimal("5")
            return deepcopy(self.reversed_payload)
        raise AssertionError(f"Unexpected recovery call: {method} {path} {kwargs}")


class MalformedProductionSession(RecoverySession):
    def __init__(self, produced, reversed_payload, first_response):
        super().__init__(produced, reversed_payload)
        self.first_response = deepcopy(first_response)
        self.production_posts = 0

    def json(self, method, path, **kwargs):
        action = kwargs.get("payload", {}).get("action")
        if method == "POST" and action == "produce":
            self.calls.append((method, path, kwargs))
            self.production_posts += 1
            if self.production_posts == 1:
                return deepcopy(self.first_response)
            replay = deepcopy(self.produced)
            replay.update(movement_ids=[31], stock_changed=True)
            return replay
        return super().json(method, path, **kwargs)


class MalformedReversalSession(RecoverySession):
    def __init__(self, produced, reversed_payload, first_response, *, applied):
        super().__init__(produced, reversed_payload)
        self.first_response = deepcopy(first_response)
        self.applied = applied
        self.reversal_posts = 0

    def json(self, method, path, **kwargs):
        action = kwargs.get("payload", {}).get("action")
        if method == "POST" and action == "reverse":
            self.calls.append((method, path, kwargs))
            self.reversal_posts += 1
            if self.reversal_posts == 1:
                if self.applied:
                    self.produced = subject._persisted_service(self.reversed_payload)
                    self.stock = Decimal("5")
                return deepcopy(self.first_response)
            self.stock = Decimal("5")
            self.produced = subject._persisted_service(self.reversed_payload)
            return deepcopy(self.reversed_payload)
        return super().json(method, path, **kwargs)


class ReleaseServiceReversalUnitTests(unittest.TestCase):
    def test_malformed_reversal_response_recovers_unapplied_or_already_applied_transition(self):
        produced = subject._persisted_service(service_payload(state="produced", version=2))
        produced_snapshot = deepcopy(produced["snapshot"])
        for malformed, applied in (({}, False), (produced, False), ({}, True)):
            session = MalformedReversalSession(
                produced, service_payload(version=2), malformed, applied=applied,
            )

            def verify_recovered():
                if session.stock != Decimal("5"):
                    raise subject.SmokeFailure("stock final no restaurado")

            with self.subTest(applied=applied, malformed=malformed):
                with self.assertRaises(subject.SmokeFailure) as raised:
                    subject._reverse_owned_service(
                        session, service_id=11, recipe_id=13, edition="integral",
                        reversal_key=REVERSAL_KEY, produced_snapshot=produced_snapshot,
                        verify_recovered=verify_recovered,
                        recovery=lambda: subject._recover_owned_production(
                            session, service_id=11, recipe_id=13, edition="integral",
                            production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
                            verify_recovered=verify_recovered,
                        ),
                    )
                self.assertNotIn("CHECKPOINT", str(raised.exception))
                self.assertEqual(session.stock, Decimal("5"))
                actions = [call[2].get("payload", {}).get("action") for call in session.calls]
                if applied:
                    self.assertEqual(actions, ["reverse", None])
                else:
                    self.assertEqual(actions, ["reverse", None, "produce", "reverse"])

    def test_malformed_or_unexpected_production_response_is_compensated_before_original_error(self):
        produced = subject._persisted_service(service_payload(state="produced", version=2))
        unexpected = service_payload(state="confirmed", version=2)
        unexpected["snapshot"].pop("production")
        for first_response in ({}, unexpected):
            session = MalformedProductionSession(produced, service_payload(version=2), first_response)
            checked = []

            def verify_recovered():
                checked.append(session.stock)
                if session.stock != Decimal("5"):
                    raise subject.SmokeFailure("stock no restaurado")

            with self.subTest(response=first_response):
                with self.assertRaises(subject.SmokeFailure) as raised:
                    subject._produce_owned_service(
                        session, service_id=11, recipe_id=13, edition="integral",
                        production_key=subject.PRODUCTION_KEYS["integral"],
                        recovery=lambda: subject._recover_owned_production(
                            session, service_id=11, recipe_id=13, edition="integral",
                            production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
                            verify_recovered=verify_recovered,
                        ),
                    )
                self.assertNotIn("CHECKPOINT", str(raised.exception))
            self.assertEqual(session.stock, Decimal("5"))
            self.assertEqual(checked, [Decimal("5")])
            self.assertEqual(
                [call[2].get("payload", {}).get("action") for call in session.calls],
                ["produce", None, "produce", "reverse"],
            )

    def test_failure_after_owned_production_uses_idempotent_replay_then_restores_stock(self):
        produced = subject._persisted_service(service_payload(state="produced", version=2))
        reversed_payload = service_payload(version=2)
        session = RecoverySession(produced, reversed_payload)
        recovered = subject._recover_owned_production(
            session, service_id=11, recipe_id=13, edition="integral",
            production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
            verify_recovered=lambda: self.assertEqual(session.stock, Decimal("5")),
        )
        self.assertEqual(recovered["state"], "cancelled")
        self.assertEqual(session.stock, Decimal("5"))
        self.assertEqual(
            [call[2].get("payload", {}).get("action") for call in session.calls],
            [None, "produce", "reverse"],
        )

    def test_post_production_guard_compensates_then_preserves_the_original_failure(self):
        produced = subject._persisted_service(service_payload(state="produced", version=2))
        session = RecoverySession(produced, service_payload(version=2))
        with self.assertRaisesRegex(subject.SmokeFailure, "fallo sintético posterior"):
            with subject._production_recovery_guard(
                True,
                lambda: subject._recover_owned_production(
                    session, service_id=11, recipe_id=13, edition="integral",
                    production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
                    verify_recovered=lambda: self.assertEqual(session.stock, Decimal("5")),
                ),
            ):
                raise subject.SmokeFailure("fallo sintético posterior a producir")
        self.assertEqual(session.stock, Decimal("5"))
        self.assertEqual(
            [call[2].get("payload", {}).get("action") for call in session.calls],
            [None, "produce", "reverse"],
        )

    def test_recovery_never_posts_for_an_unverifiable_or_foreign_service(self):
        foreign = subject._persisted_service(service_payload(state="produced", version=2))
        foreign["title"] = "Servicio ajeno"
        session = RecoverySession(foreign, service_payload(version=2))
        with self.assertRaises(subject.SmokeFailure):
            subject._recover_owned_production(
                session, service_id=11, recipe_id=13, edition="integral",
                production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
                verify_recovered=lambda: None,
            )
        self.assertEqual([call[0] for call in session.calls], ["GET"])
        self.assertEqual(session.stock, Decimal("4.6"))

    def test_recovery_requires_own_production_key_before_reverse_and_emits_checkpoint(self):
        produced = subject._persisted_service(service_payload(state="produced", version=2))
        session = RecoverySession(produced, service_payload(version=2))
        original_json = session.json

        def reject_replay(method, path, **kwargs):
            if method == "POST" and kwargs.get("payload", {}).get("action") == "produce":
                session.calls.append((method, path, kwargs))
                raise subject.SmokeFailure("conflicto de clave")
            return original_json(method, path, **kwargs)

        session.json = reject_replay
        with self.assertRaisesRegex(subject.SmokeFailure, "CHECKPOINT"):
            with subject._production_recovery_guard(
                True,
                lambda: subject._recover_owned_production(
                    session, service_id=11, recipe_id=13, edition="integral",
                    production_key="clave-no-propia", reversal_key=REVERSAL_KEY,
                    verify_recovered=lambda: None,
                ),
            ):
                raise subject.SmokeFailure("fallo posterior")
        self.assertEqual(session.stock, Decimal("4.6"))
        self.assertEqual(
            [call[2].get("payload", {}).get("action") for call in session.calls],
            [None, "produce"],
        )

    def test_cancelled_and_newly_reversed_recovery_both_require_final_stock_verification(self):
        cancelled = RecoverySession(
            subject._persisted_service(service_payload(version=2)), service_payload(version=2),
        )
        for session in (
            cancelled,
            RecoverySession(
                subject._persisted_service(service_payload(state="produced", version=2)),
                service_payload(version=2),
            ),
        ):
            with self.subTest(state=session.produced["state"]), self.assertRaisesRegex(
                subject.SmokeFailure, "inventario final no verificado",
            ):
                subject._recover_owned_production(
                    session, service_id=11, recipe_id=13, edition="integral",
                    production_key=subject.PRODUCTION_KEYS["integral"], reversal_key=REVERSAL_KEY,
                    verify_recovered=lambda: (_ for _ in ()).throw(
                        subject.SmokeFailure("inventario final no verificado"),
                    ),
                )

    def test_v2_production_accepts_and_preserves_the_strict_waste_classification(self):
        payload = service_payload(version=2)
        frozen = deepcopy(payload["snapshot"]["production"]["waste_classification"])
        document, movement_ids = subject._production_document(payload, 11, "integral")
        self.assertEqual(movement_ids, [31])
        self.assertEqual(document["waste_classification"], frozen)
        self.assertEqual([row["ingredient_id"] for row in frozen["lines"]], [21, 21])
        produced = deepcopy(payload["snapshot"])
        produced["production"].pop("reversal")
        self.assertEqual(subject._validate_reversal(
            payload, service_id=11, recipe_id=13, edition="integral",
            produced_snapshot=produced, reversal_key=REVERSAL_KEY,
        ), [32])
        self.assertEqual(payload["snapshot"]["production"]["waste_classification"], frozen)

    def test_v2_production_rejects_malformed_classification_and_unknown_fields(self):
        base = service_payload(version=2)
        mutations = []
        for path, value in (
            (("classification_only",), False),
            (("additional_stock_movement",), True),
            (("coverage",), "all_waste"),
            (("status",), "safe"),
            (("recorded_by",), True),
            (("recorded_at",), "2026-10-25T12:00:01+02:00"),
            (("lines", 0, "ingredient_id"), 0),
            (("lines", 0, "yield_ratio"), "1.1"),
            (("lines", 0, "waste_quantity"), "0.2"),
            (("lines", 0, "food_name"), "Aceite\x00oculto"),
        ):
            changed = deepcopy(base)
            target = changed["snapshot"]["production"]["waste_classification"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            mutations.append(changed)
        unknown = deepcopy(base)
        unknown["snapshot"]["production"]["waste_classification"]["unexpected"] = True
        mutations.append(unknown)
        production_unknown = deepcopy(base)
        production_unknown["snapshot"]["production"]["unexpected"] = True
        mutations.append(production_unknown)
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(subject.SmokeFailure):
                subject._production_document(payload, 11, "integral")

    def test_v2_production_rejects_non_text_quantity_basis_as_controlled_smoke_failure(self):
        for invalid in ([], {}, ["gross"], {"gross": True}):
            payload = service_payload(version=2)
            payload["snapshot"]["production"]["waste_classification"]["lines"][0]["quantity_basis"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(subject.SmokeFailure):
                subject._production_document(payload, 11, "integral")

    def test_legacy_production_remains_accepted_but_cannot_carry_v2_fields(self):
        legacy = service_payload()
        self.assertEqual(subject._production_document(legacy, 11, "integral")[1], [31])
        hybrid = deepcopy(legacy)
        hybrid["snapshot"]["production"]["waste_classification"] = waste_classification()
        with self.assertRaises(subject.SmokeFailure):
            subject._production_document(hybrid, 11, "integral")

    def test_wrong_initial_stock_aborts_before_any_post(self):
        session = Mock()
        session.json.return_value = []
        with patch.object(subject, "HttpSession", return_value=session), \
                patch.object(subject, "_active_space"), \
                patch.object(subject, "_demo_recipe", return_value=13), \
                patch.object(subject, "_demo_package", return_value={}), \
                patch.object(subject, "_inventory_amount", return_value=({}, Decimal("4.9"))):
            with self.assertRaises(subject.SmokeFailure):
                subject._exercise_account("integral", "synthetic-only-password")
        self.assertFalse(any(call.args[0] == "POST" for call in session.json.call_args_list))
        self.assertFalse(any(call.args[0] == "POST" for call in session.request.call_args_list))

    def test_preexisting_draft_aborts_before_confirming_unverifiable_recipe(self):
        session = Mock()
        draft = service_payload(state="draft")
        draft["snapshot"] = {}
        draft["covers"] = "999"
        session.json.side_effect = [[draft], draft, draft]
        with self.assertRaises(subject.SmokeFailure):
            subject._find_or_create_service(session, 13, edition="integral", stock_initial=Decimal("5"))
        self.assertFalse(any(call.args[0] == "POST" for call in session.json.call_args_list))

    def test_action_projection_strips_only_ephemeral_fields_without_mutating_source(self):
        payload = service_payload(state="produced")
        payload["movement_ids"] = [31]
        before = deepcopy(payload)
        expected = {key: value for key, value in payload.items()
                    if key not in {"movement_ids", "reversal_movement_ids", "stock_changed"}}
        self.assertEqual(subject._persisted_service(payload), expected)
        self.assertEqual(payload, before)

    def test_native_stock_number_accepts_finite_json_number_but_not_bool(self):
        self.assertEqual(subject._native_decimal(4.6, "stock"), Decimal("4.6"))
        self.assertEqual(subject._native_decimal(5, "stock"), Decimal("5"))
        for invalid in (True, "5", float("inf"), float("nan"), None):
            with self.subTest(invalid=invalid), self.assertRaises(subject.SmokeFailure):
                subject._native_decimal(invalid, "stock")

    def test_integral_reversal_requires_exact_audit_and_preserves_produced_snapshot(self):
        payload = service_payload()
        produced = deepcopy(payload["snapshot"])
        produced["production"].pop("reversal")
        self.assertEqual(
            subject._validate_reversal(
                payload, service_id=11, recipe_id=13, edition="integral", produced_snapshot=produced,
                reversal_key=REVERSAL_KEY,
            ),
            [32],
        )

    def test_professional_reversal_has_no_stock_ids(self):
        payload = service_payload("profesional")
        produced = deepcopy(payload["snapshot"])
        produced["production"].pop("reversal")
        self.assertEqual(
            subject._validate_reversal(
                payload, service_id=11, recipe_id=13, edition="profesional", produced_snapshot=produced,
                reversal_key=REVERSAL_KEY,
            ),
            [],
        )

    def test_reversal_rejects_malformed_or_mismatched_success(self):
        mutations = []
        base = service_payload()
        malformed = deepcopy(base)
        malformed["snapshot"]["production"]["reversal"]["unexpected"] = True
        mutations.append(malformed)
        wrong_actor = deepcopy(base)
        wrong_actor["snapshot"]["production"]["reversal"]["reversed_by"] = 99
        mutations.append(wrong_actor)
        wrong_top = deepcopy(base)
        wrong_top["reversal_movement_ids"] = [999]
        mutations.append(wrong_top)
        missing_stock_flag = deepcopy(base)
        del missing_stock_flag["stock_changed"]
        mutations.append(missing_stock_flag)
        changed_frozen = deepcopy(base)
        changed_frozen["snapshot"]["needs"] = [{"food": "cambiado"}]
        mutations.append(changed_frozen)
        produced = deepcopy(base["snapshot"])
        produced["production"].pop("reversal")
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(subject.SmokeFailure):
                subject._validate_reversal(
                    payload, service_id=11, recipe_id=13, edition="integral", produced_snapshot=produced,
                    reversal_key=REVERSAL_KEY,
                )

    def test_ledger_requires_exact_point_four_consume_and_receipt(self):
        origin = {"type": "service_plan", "id": 11, "service_date": subject.SERVICE_DATE}
        rows = [
            {"id": 31, "kind": "consume", "quantity": "0.4", "reverses": None, "metadata_snapshot": {"origin": origin}},
            {"id": 32, "kind": "receipt", "quantity": "0.4", "reverses": 31, "metadata_snapshot": {"origin": origin}},
        ]
        subject._validate_integral_movements(rows, service_id=11, original_ids=[31], reversal_ids=[32])
        rows[0]["quantity"] = "0.4001"
        with self.assertRaises(subject.SmokeFailure):
            subject._validate_integral_movements(rows, service_id=11, original_ids=[31], reversal_ids=[32])

    def test_foreign_guard_uses_direct_detail_and_reverse_without_leaking_title(self):
        session = RecordingSession()
        subject._assert_denied(session, 11, "cross-space-v1")
        self.assertEqual(session.calls[0][:2], ("GET", "/api/cuaderno/services/11/"))
        self.assertEqual(session.calls[1][:2], ("POST", "/api/cuaderno/services/11/"))
        self.assertEqual(
            session.calls[1][2]["payload"],
            {"action": "reverse", "idempotency_key": "cross-space-v1"},
        )

    def test_foreign_guard_fails_if_denied_body_discloses_reserved_title(self):
        session = RecordingSession(bodies=(subject.SERVICE_TITLE.encode("utf-8"), b"{}"))
        with self.assertRaises(subject.SmokeFailure):
            subject._assert_denied(session, 11, "cross-space-v1")
        self.assertEqual(len(session.calls), 1)

    def test_transition_builds_stable_action_and_key(self):
        class JsonSession:
            def __init__(self):
                self.call = None

            def json(self, method, path, **kwargs):
                self.call = method, path, kwargs
                return {"ok": True}

        session = JsonSession()
        self.assertEqual(subject._post_transition(session, 11, "reverse", "stable-v1"), {"ok": True})
        self.assertEqual(
            session.call,
            ("POST", "/api/cuaderno/services/11/", {"payload": {"action": "reverse", "idempotency_key": "stable-v1"}}),
        )

    def test_constants_keep_tool_on_known_demo_contract(self):
        self.assertEqual(set(subject.PRODUCTION_KEYS), {"profesional", "integral"})
        self.assertEqual(set(subject.REVERSAL_KEYS), {"profesional", "integral"})
        subject._guard_base_url("http://127.0.0.1:18081")
        with self.assertRaises(subject.SmokeFailure):
            subject._guard_base_url("http://localhost:18081")


if __name__ == "__main__":
    unittest.main()
