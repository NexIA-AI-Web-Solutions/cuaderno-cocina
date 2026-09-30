import unittest
from copy import deepcopy
from decimal import Decimal

from scripts.cuaderno.release_http_smoke import SmokeFailure
from scripts.cuaderno import release_waste_smoke as waste


def valuation_payload():
    return {
        "policy": "replacement_estimate",
        "status": "complete",
        "amount": "0.8",
        "currency": "EUR",
        "price_policy": "net",
        "as_of": "2026-09-30T12:00:00+00:00",
        "reason": None,
        "input": {"quantity": "0.125", "unit_id": 11, "unit_name": "L"},
        "package": {"id": 21, "label": waste.PACKAGE_LABEL, "quantity": "5", "unit_id": 11, "unit_name": "L"},
        "price_version": {"id": 31, "amount": "32", "explicit_free": False, "valid_from": "2026-09-29T00:00:00+00:00"},
        "calculation": {
            "quantity_in_package_unit": "0.125", "package_fraction": "0.025",
            "computed_amount": "0.8", "working_precision": 64, "rounding": "HALF_EVEN",
        },
    }


def movement_row(*, movement_id=71, reverses=None):
    return {
        "id": movement_id,
        "kind": "waste" if reverses is None else "receipt",
        "quantity": "0.125",
        "entry": 41,
        "balance": "4.875" if reverses is None else "5",
        "reverses": reverses,
        "created_at": "2026-09-30T12:00:00+00:00",
        "metadata_snapshot": {
            "household_id": 51,
            "origin": {"type": "standalone_waste", "cause": waste.CAUSE},
            "valuation": valuation_payload(),
        },
    }


class RecoverySession:
    def __init__(self, rows):
        self.rows = rows
        self.posts = []

    def json(self, method, path, **kwargs):
        if method == "GET":
            return self.rows
        self.posts.append((path, kwargs["payload"]))
        return {
            "movement_id": 72, "kind": "receipt", "reverses": 71,
            "balance": "5", "current_balance": "5",
            "metadata_snapshot": movement_row()["metadata_snapshot"],
        }


class ReleaseWasteSmokeUnitTests(unittest.TestCase):
    def test_demo_inventory_requires_exact_native_numeric_five_litre_fixture(self):
        self.assertEqual(waste._fixture_stock_token(5), ("int", "5"))
        self.assertEqual(waste._fixture_stock_token(5.0), ("float", "5.0"))
        for value in (4.875, 5.125, "5", True, float("nan")):
            with self.subTest(value=value), self.assertRaises(SmokeFailure):
                waste._fixture_stock_token(value)

    def test_fixed_decimal_and_replacement_valuation_are_exact(self):
        checked = waste._validate_valuation(
            valuation_payload(), package_id=21, unit_id=11, quantity=Decimal("0.125"),
        )
        self.assertEqual(checked, Decimal("0.8"))
        for invalid in ("8e-1", "+0.8", 0.8, "-0", "0.80000000000000000"):
            changed = deepcopy(valuation_payload())
            changed["amount"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(SmokeFailure):
                waste._validate_valuation(changed, package_id=21, unit_id=11, quantity=Decimal("0.125"))
        boolean_id = deepcopy(valuation_payload())
        boolean_id["package"]["id"] = True
        with self.assertRaises(SmokeFailure):
            waste._validate_valuation(boolean_id, package_id=1, unit_id=11, quantity=Decimal("0.125"))

    def test_movement_list_is_bounded_and_identity_is_exact(self):
        checked = waste._owned_movement([movement_row()], movement_id=71, entry_id=41, household_id=51)
        self.assertEqual(checked["id"], 71)
        with self.assertRaises(SmokeFailure):
            waste._movement_rows([movement_row(movement_id=index + 1) for index in range(100)])
        forged = movement_row()
        forged["metadata_snapshot"]["origin"]["cause"] = "Otro"
        with self.assertRaises(SmokeFailure):
            waste._owned_movement([forged], movement_id=71, entry_id=41, household_id=51)

    def test_recovery_compensates_only_the_exact_owned_movement(self):
        session = RecoverySession([movement_row()])
        reversal = waste._compensate_owned(session, movement_id=71, entry_id=41, household_id=51)
        self.assertEqual(reversal["reverses"], 71)
        self.assertEqual(len(session.posts), 1)

        foreign = movement_row()
        foreign["entry"] = 99
        refused = RecoverySession([foreign])
        with self.assertRaises(SmokeFailure):
            waste._compensate_owned(refused, movement_id=71, entry_id=41, household_id=51)
        self.assertEqual(refused.posts, [])

    def test_restored_balance_uses_historical_balance_not_current_rerun_balance(self):
        self.assertEqual(waste._restored_balance("4.875", Decimal("0.125")), Decimal("5"))
        with self.assertRaises(SmokeFailure):
            waste._restored_balance("unknown", Decimal("0.125"))

    def test_reversal_response_must_preserve_snapshot_and_reference_original(self):
        original = movement_row()
        response = {
            "movement_id": 72, "kind": "receipt", "reverses": 71,
            "balance": "5", "current_balance": "5",
            "metadata_snapshot": deepcopy(original["metadata_snapshot"]),
        }
        checked = waste._validate_reversal(response, original=original, expected_balance=Decimal("5"))
        self.assertEqual(checked, 72)
        response["metadata_snapshot"]["valuation"]["amount"] = "0"
        with self.assertRaises(SmokeFailure):
            waste._validate_reversal(response, original=original, expected_balance=Decimal("5"))

    def test_idempotency_snapshot_allows_only_declared_new_rows(self):
        before = [movement_row()]
        reversal = movement_row(movement_id=72, reverses=71)
        waste._assert_added_only(before, [reversal, *before], {72})

        changed = deepcopy(before)
        changed[0]["balance"] = "4"
        with self.assertRaises(SmokeFailure):
            waste._assert_added_only(before, changed, set())
        with self.assertRaises(SmokeFailure):
            waste._assert_added_only(before, [movement_row(movement_id=73), *before], {72})


if __name__ == "__main__":
    unittest.main()
