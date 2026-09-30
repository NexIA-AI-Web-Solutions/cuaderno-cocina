import unittest
from unittest.mock import patch

from scripts.cuaderno.release_http_smoke import SmokeFailure
from scripts.cuaderno.release_preparation_smoke import (
    _assert_previous_services,
    _find_or_create_service,
    _frozen_signature,
    _inventory_amount_rows,
    _non_target_state,
    _native_stock_amount_token,
    _preparation_path,
    _preparation_payload,
    _restore_original,
    _service_detail,
)


REVISION_A = "a" * 64
REVISION_B = "b" * 64
REVISION_C = "c" * 64


def preparation_payload(*, revision=REVISION_A, checked=False, extra=None, **item_changes):
    item = {
        "id": 31,
        "source_step_id": 41,
        "position": 0,
        "recipe_id": 21,
        "name": "Preparar salsa",
        "instruction": "Mezclar y reservar.",
        "checked": checked,
        "checked_at": "2026-09-30T03:00:00+00:00" if checked else None,
        "updated_by": 7 if checked else None,
    }
    item.update(item_changes)
    payload = {
        "service_id": 11,
        "state": "confirmed",
        "can_edit": True,
        "revision": revision,
        "items": [item],
    }
    if extra is not None:
        payload[extra] = True
    return payload


class ReleasePreparationSmokeUnitTests(unittest.TestCase):
    def test_inventory_adapter_preserves_native_numeric_rows_for_read_only_comparison(self):
        rows = {"results": [{"id": 2, "amount": 5.0}, {"id": 1, "amount": 3}]}
        with patch("scripts.cuaderno.release_preparation_smoke._snapshot", return_value=rows):
            self.assertEqual(
                _inventory_amount_rows(object()),
                [(1, ("int", "3")), (2, ("float", "5.0"))],
            )

    def test_native_inventory_amount_token_accepts_only_finite_json_numbers_without_decimal_claims(self):
        self.assertEqual(_native_stock_amount_token(0), ("int", "0"))
        self.assertEqual(_native_stock_amount_token(2.5), ("float", "2.5"))
        self.assertEqual(_native_stock_amount_token(-0.0), ("float", "-0.0"))
        for value in (True, False, "2.5", None, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(SmokeFailure):
                _native_stock_amount_token(value)

    def test_complete_typed_preparation_contract_is_accepted(self):
        revision, items = _preparation_payload(preparation_payload(), 11, checked=False)
        self.assertEqual(revision, REVISION_A)
        self.assertEqual(items[0]["id"], 31)

        checked_revision, checked_items = _preparation_payload(
            preparation_payload(revision=REVISION_B, checked=True), 11, checked=True,
        )
        self.assertEqual(checked_revision, REVISION_B)
        self.assertEqual(checked_items[0]["updated_by"], 7)

    def test_incomplete_coerced_or_unknown_responses_fail_closed(self):
        cases = [
            None,
            preparation_payload(extra="unknown"),
            {**preparation_payload(), "revision": "A" * 64},
            {**preparation_payload(), "revision": "a" * 63},
            {**preparation_payload(), "service_id": "11"},
            {**preparation_payload(), "service_id": True},
            {**preparation_payload(), "state": "draft"},
            {**preparation_payload(), "can_edit": 1},
            preparation_payload(id=True),
            preparation_payload(source_step_id=None),
            preparation_payload(position=True),
            preparation_payload(position=False),
            preparation_payload(recipe_id="21"),
            preparation_payload(checked=1),
            preparation_payload(extra_item="field"),
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _preparation_payload(payload, 11)
        with self.assertRaises(SmokeFailure):
            _preparation_payload(preparation_payload(), True)

    def test_checked_state_requires_aware_time_and_actor_and_unchecked_clears_time(self):
        invalid = [
            preparation_payload(checked=True, checked_at=None),
            preparation_payload(checked=True, checked_at="2026-09-30T03:00:00", updated_by=7),
            preparation_payload(checked=True, updated_by=None),
            preparation_payload(checked=False, checked_at="2026-09-30T03:00:00+00:00"),
            preparation_payload(checked=False, updated_by="7"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _preparation_payload(payload, 11)

    def test_service_scoped_url_accepts_only_positive_integer_identifiers(self):
        self.assertEqual(_preparation_path(11), "/api/cuaderno/services/11/preparation/")
        for value in (True, 0, -1, "11", None):
            with self.subTest(value=value), self.assertRaises(SmokeFailure):
                _preparation_path(value)

    def test_recovery_does_not_write_when_already_unchecked(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("Un estado ya restaurado no necesita PUT.")
                return preparation_payload(revision=REVISION_C)

        session = Session()
        signature = _frozen_signature(preparation_payload()["items"])
        revision = _restore_original(
            session, "/prep/", 11, item_id=31, expected_revision=None,
            expected_signature=signature,
            expected_non_target_state=(),
        )
        self.assertEqual(revision, REVISION_C)
        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_recovery_refuses_checked_state_without_its_exact_checkpoint(self):
        class Session:
            def __init__(self, revision):
                self.revision = revision
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("No debe sobrescribir una revisión ajena.")
                return preparation_payload(revision=inner_self.revision, checked=True)

        for expected, actual in ((None, REVISION_B), (REVISION_B, REVISION_C)):
            session = Session(actual)
            signature = _frozen_signature(preparation_payload()["items"])
            with self.subTest(expected=expected, actual=actual), self.assertRaises(SmokeFailure):
                _restore_original(
                    session, "/prep/", 11, item_id=31, expected_revision=expected,
                    expected_signature=signature,
                    expected_non_target_state=(),
                )
            self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_recovery_uses_known_b_revision_and_validates_restored_response(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method == "GET":
                    return preparation_payload(revision=REVISION_B, checked=True)
                self.assertEqual(kwargs["payload"], {"item": 31, "checked": False, "revision": REVISION_B})
                return preparation_payload(revision=REVISION_C, checked=False, updated_by=7)

        session = Session()
        signature = _frozen_signature(preparation_payload()["items"])
        revision = _restore_original(
            session, "/prep/", 11, item_id=31, expected_revision=REVISION_B,
            expected_signature=signature,
            expected_non_target_state=(),
        )
        self.assertEqual(revision, REVISION_C)
        self.assertEqual([call[0] for call in session.calls], ["GET", "PUT"])

    def test_recovery_checks_all_frozen_fields_and_cardinality_before_put(self):
        original = preparation_payload()
        second = {
            **original["items"][0],
            "id": 32,
            "source_step_id": 42,
            "position": 1,
            "name": "Enfriar",
            "instruction": "Enfriar la salsa.",
        }
        changed_documents = (
            (
                preparation_payload(revision=REVISION_B, checked=True, instruction="Texto cambiado"),
                _frozen_signature(original["items"]),
            ),
            (
                preparation_payload(revision=REVISION_B, checked=True),
                _frozen_signature([*original["items"], second]),
            ),
        )

        class Session:
            def __init__(self, document):
                self.document = document
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("Una firma congelada distinta no puede provocar PUT.")
                return inner_self.document

        for document, expected_signature in changed_documents:
            session = Session(document)
            with self.subTest(document=document), self.assertRaisesRegex(SmokeFailure, "pasos congelados"):
                _restore_original(
                    session, "/prep/", 11, item_id=31, expected_revision=REVISION_B,
                    expected_signature=expected_signature,
                    expected_non_target_state=(),
                )
            self.assertEqual([call[0] for call in session.calls], ["GET"])

        changed_second = {
            **second,
            "checked": True,
            "checked_at": "2026-09-30T03:00:00+00:00",
            "updated_by": 8,
        }
        mutable_document = preparation_payload(revision=REVISION_B, checked=True)
        mutable_document["items"].append(changed_second)
        mutable_session = Session(mutable_document)
        expected_items = [*original["items"], second]
        with self.assertRaisesRegex(SmokeFailure, "Otro paso"):
            _restore_original(
                mutable_session, "/prep/", 11, item_id=31, expected_revision=REVISION_B,
                expected_signature=_frozen_signature(expected_items),
                expected_non_target_state=_non_target_state(expected_items, 31),
            )
        self.assertEqual([call[0] for call in mutable_session.calls], ["GET"])

    def test_service_detail_rejects_boolean_service_or_snapshot_recipe_ids(self):
        valid = {
            "id": 11,
            "title": "Preparación HTTP DEMO",
            "service_date": "2026-10-25",
            "state": "confirmed",
            "covers": "4",
            "snapshot": {"recipe_id": 21},
        }
        self.assertEqual(_service_detail(valid, 11, 21), valid)
        for payload in (
            {**valid, "id": True},
            {**valid, "snapshot": {"recipe_id": True}},
        ):
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _service_detail(payload, 11, 21)

    def test_previous_confirmed_services_must_remain_byte_equivalent(self):
        previous = {1: {"id": 1, "state": "confirmed", "snapshot": {"covers": "4"}}}
        _assert_previous_services(previous, [previous[1], {"id": 2, "state": "confirmed"}])
        with self.assertRaises(SmokeFailure):
            _assert_previous_services(previous, [{"id": 1, "state": "confirmed", "snapshot": {"covers": "5"}}])

    def test_existing_reserved_draft_is_not_confirmed_or_overwritten(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("Un borrador anterior no debe confirmarse.")
                if path == "/api/cuaderno/services/":
                    return [{"id": 11, "title": "Preparación HTTP DEMO", "state": "draft"}]
                if path == "/api/cuaderno/services/11/":
                    return {"id": 11, "title": "Preparación HTTP DEMO", "state": "draft"}
                raise AssertionError(path)

        session = Session()
        with self.assertRaisesRegex(SmokeFailure, "borrador"):
            _find_or_create_service(session, 21)
        self.assertEqual([call[0] for call in session.calls], ["GET", "GET"])


if __name__ == "__main__":
    unittest.main()
