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


def service_payload(edition="integral", state="cancelled"):
    original = [31] if edition == "integral" else []
    reversed_ids = [32] if edition == "integral" else []
    production = {
        "produced_at": "2026-10-25T12:00:00+02:00",
        "edition": edition,
        "movement_ids": original,
        "stock_changed": edition == "integral",
    }
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


class ReleaseServiceReversalUnitTests(unittest.TestCase):
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
