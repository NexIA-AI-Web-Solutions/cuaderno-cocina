import unittest
from decimal import Decimal
from unittest.mock import patch

from scripts.cuaderno.release_http_smoke import SmokeFailure
from scripts.cuaderno import release_reserves_smoke as reserves
from scripts.cuaderno.release_reserves_smoke import _demo_package, _expected_packages, _one, _positive_id


class _GuardSession:
    def __init__(self, *, minimum_unit=11, orders=None, explicit_free=False):
        self.minimum_unit = minimum_unit
        self.orders = [] if orders is None else orders
        self.explicit_free = explicit_free
        self.calls = []

    def login(self, username, password):
        self.calls.append(("LOGIN", username))

    def json(self, method, path, **kwargs):
        self.calls.append((method, path))
        if method != "GET":
            raise AssertionError(f"Mutación inesperada antes de completar preflight: {method} {path}")
        if path == "/health/ready/":
            return {"ready": True}
        if path == "/api/cuaderno/edition/":
            return {"edition": "integral"}
        if path == "/api/user-space/all_personal/":
            return [{"active": True, "space": 1}]
        if path == "/api/space/1/":
            return {"id": 1, "name": reserves.DEMO_SPACE}
        if path == "/api/cuaderno/packages/":
            return [{
                "id": 21, "food": 31, "food_name": reserves.FOOD_NAME,
                "unit": 11, "unit_name": reserves.UNIT_NAME,
                "label": reserves.PACKAGE_LABEL, "quantity": "5",
                "current_price": {"amount": "32", "explicit_free": self.explicit_free},
            }]
        if path.startswith("/api/inventory-entry/"):
            return {"count": 1, "next": None, "previous": None, "results": [{"id": 41}]}
        if path == "/api/cuaderno/purchase-orders/":
            return self.orders
        if path == "/api/cuaderno/stock-minimums/":
            return {
                "edition": "integral", "household": {"id": 51, "name": "Equipo DEMO"},
                "items": [{
                    "id": 61, "household": 51, "food": 31, "unit": self.minimum_unit,
                    "quantity": "6", "location": None, "updated_at": "2026-09-30T12:00:00Z",
                }],
            }
        raise AssertionError(f"GET no previsto: {path}")


class _SnapshotSession:
    def __init__(self, payload):
        self.payload = payload

    def json(self, method, path, **kwargs):
        return self.payload


class ReleaseReservesSmokeUnitTests(unittest.TestCase):
    def test_package_rounding_uses_exact_decimal_ceiling(self):
        cases = (("0", "0"), ("0.1", "1"), ("5", "1"), ("5.0001", "2"), ("12", "3"))
        for missing, expected in cases:
            with self.subTest(missing=missing):
                self.assertEqual(_expected_packages(Decimal(missing)), Decimal(expected))

    def test_invalid_identifiers_and_ambiguous_demo_rows_fail_closed(self):
        for value in (True, 0, -1, "1", None):
            with self.subTest(value=value), self.assertRaises(SmokeFailure):
                _positive_id(value, "fixture")
        with self.assertRaises(SmokeFailure):
            _one([{"name": "demo"}, {"name": "demo"}], lambda row: row["name"] == "demo", "fixture")

    def test_rounding_rejects_negative_missing_and_nonpositive_package(self):
        for missing, quantity in ((Decimal("-0.1"), Decimal("5")), (Decimal("1"), Decimal("0"))):
            with self.subTest(missing=missing, quantity=quantity), self.assertRaises(SmokeFailure):
                _expected_packages(missing, quantity)

    def test_wrong_minimum_unit_aborts_preflight_without_put(self):
        session = _GuardSession(minimum_unit=99)
        with patch.object(reserves, "HttpSession", return_value=session), \
                patch.object(reserves, "_guard_environment", return_value="demo-password-123"):
            with self.assertRaises(SmokeFailure):
                reserves.run()
        self.assertNotIn("PUT", [method for method, _ in session.calls])

    def test_one_hundred_orders_are_ambiguous_and_abort_without_put(self):
        session = _GuardSession(orders=[{"id": index + 1} for index in range(100)])
        with patch.object(reserves, "HttpSession", return_value=session), \
                patch.object(reserves, "_guard_environment", return_value="demo-password-123"):
            with self.assertRaises(SmokeFailure):
                reserves.run()
        self.assertNotIn("PUT", [method for method, _ in session.calls])

    def test_demo_reference_price_must_not_be_marked_free(self):
        session = _GuardSession(explicit_free=True)
        with self.assertRaises(SmokeFailure):
            _demo_package(session)

    def test_existing_minimum_document_must_belong_to_envelope_and_be_auditable(self):
        row = {
            "id": 61, "household": 51, "food": 31, "unit": 11,
            "quantity": "6", "location": None, "updated_at": "2026-09-30T12:00:00Z",
        }
        for change in ({"id": 0}, {"household": 52}, {"updated_at": None}):
            with self.subTest(change=change), self.assertRaises(SmokeFailure):
                reserves._oil_minimum([{**row, **change}], 31, 11, 51)

    def test_inventory_snapshot_ignores_only_paginated_transport_timestamp(self):
        base = {
            "count": 1, "next": None, "previous": None,
            "timestamp": "2026-09-30T12:00:00Z",
            "results": [{"id": 41, "amount": 5.0, "updated_at": "2026-09-29T08:00:00Z"}],
        }
        later = {**base, "timestamp": "2026-09-30T12:00:01Z"}
        changed = {**later, "results": [{**later["results"][0], "amount": 4.0}]}
        first = reserves._snapshot(_SnapshotSession(base), "/api/inventory-entry/")
        self.assertEqual(first, reserves._snapshot(_SnapshotSession(later), "/api/inventory-entry/"))
        self.assertNotEqual(first, reserves._snapshot(_SnapshotSession(changed), "/api/inventory-entry/"))
        self.assertEqual(first["results"][0]["updated_at"], "2026-09-29T08:00:00Z")

    def test_paginated_snapshot_requires_complete_consistent_wrapper(self):
        base = {"count": 1, "next": None, "previous": None, "timestamp": "now", "results": [{"id": 1}]}
        for change in (
            {"count": 2}, {"next": "/api/inventory-entry/?page=2"},
            {"previous": "/api/inventory-entry/?page=1"}, {"timestamp": None},
        ):
            with self.subTest(change=change), self.assertRaises(SmokeFailure):
                reserves._snapshot(_SnapshotSession({**base, **change}), "/api/inventory-entry/")


if __name__ == "__main__":
    unittest.main()
