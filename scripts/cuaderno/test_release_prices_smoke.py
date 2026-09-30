import unittest
from copy import deepcopy
from decimal import Decimal

from scripts.cuaderno.release_http_smoke import SmokeFailure
from scripts.cuaderno.release_prices_smoke import (
    _assert_invalid_queries,
    _validate_history,
    _validate_impact,
)


class FakeSession:
    def __init__(self, statuses):
        self.statuses = iter(statuses)

    def request(self, _method, _path, *, csrf, expected):
        status = next(self.statuses)
        if status not in expected:
            raise SmokeFailure(f"HTTP sintético inesperado: {status}")
        return status, "application/json", b"{}"


def history_payload(*, previous=True):
    items = [
        {
            "id": 32,
            "amount": "99",
            "explicit_free": False,
            "valid_from": "2999-01-01T00:00:00+00:00",
            "created_at": "2026-09-30T00:00:00+00:00",
            "created_by": 7,
            "note": "futuro sintético",
            "is_current": False,
        },
        {
            "id": 31,
            "amount": "32",
            "explicit_free": False,
            "valid_from": "2026-09-29T00:00:00+00:00",
            "created_at": "2026-09-29T00:00:00+00:00",
            "created_by": 7,
            "note": "actual sintético",
            "is_current": True,
        },
    ]
    if previous:
        items.append({
            "id": 30,
            "amount": "30",
            "explicit_free": False,
            "valid_from": "2026-09-28T00:00:00+00:00",
            "created_at": "2026-09-28T00:00:00+00:00",
            "created_by": 7,
            "note": "anterior sintético",
            "is_current": False,
        })
    return {
        "package": 21,
        "currency": "EUR",
        "as_of": "2026-09-30T12:00:00+00:00",
        "current_price_id": 31,
        "count": len(items),
        "next_offset": None,
        "items": items,
    }


def cost_sheet(status, total):
    return {
        "status": status,
        "unrounded": total,
        "display": total,
        "known_subtotal": "0" if total is None else total,
        "total": total,
        "warnings": [] if total is not None else ["precio_desconocido"],
        "base_servings": "4",
        "servings": "4",
        "per_serving": None if total is None else str(Decimal(total) / Decimal("4")),
        "lines": [],
    }


def impact_payload(*, previous=True):
    return {
        "recipe_id": 11,
        "package": 21,
        "as_of": "2026-09-30T12:00:00+00:00",
        "current_price_id": 31,
        "previous_price_id": 30 if previous else None,
        "affected": True,
        "before": cost_sheet("complete", "2.4") if previous else cost_sheet("incomplete", None),
        "after": cost_sheet("complete", "2.56"),
        "difference": "0.16" if previous else None,
        "difference_per_serving": "0.04" if previous else None,
        "currency": "EUR",
        "price_policy": "net",
    }


class ReleasePricesSmokeUnitTests(unittest.TestCase):
    def test_invalid_query_guard_accepts_414_only_for_oversized_uris(self):
        statuses = _assert_invalid_queries(
            FakeSession([400, 400, 414, 414]), "/api/cuaderno/packages/21/prices/",
        )
        self.assertEqual(statuses, {
            "limit_blank": 400,
            "offset_blank": 400,
            "limit_oversized": 414,
            "offset_oversized": 414,
        })
        with self.assertRaises(SmokeFailure):
            _assert_invalid_queries(
                FakeSession([414, 400, 414, 414]), "/api/cuaderno/packages/21/prices/",
            )

    def test_history_accepts_exact_current_price_and_marks_future_noncurrent(self):
        checked = _validate_history(history_payload(), package_id=21)
        self.assertEqual(checked["current_price_id"], 31)
        self.assertEqual(checked["versions"][30], Decimal("30"))

    def test_accepts_fixed_ascii_decimals_with_database_scale(self):
        history_data = history_payload()
        history_data["items"][1]["amount"] = "32.0000000000000000"
        history = _validate_history(history_data, package_id=21)
        self.assertEqual(history["versions"][31], Decimal("32.0000000000000000"))

        impact_data = impact_payload()
        impact_data["after"].update({
            "unrounded": "2.5600000000000000",
            "known_subtotal": "2.5600000000000000",
            "total": "2.5600000000000000",
            "per_serving": "0.6400000000000000",
        })
        checked = _validate_impact(
            impact_data, recipe_id=11, package_id=21, history=history,
        )
        self.assertEqual(checked["after"], Decimal("2.5600000000000000"))

    def test_history_rejects_invalid_envelopes_money_and_current_markers(self):
        base = history_payload()
        invalid = []
        changed = deepcopy(base)
        changed["items"][1]["amount"] = 32.0
        invalid.append(changed)
        changed = deepcopy(base)
        changed["items"][0]["is_current"] = True
        invalid.append(changed)
        changed = deepcopy(base)
        changed["currency"] = "USD"
        invalid.append(changed)
        changed = deepcopy(base)
        changed["count"] = 1
        invalid.append(changed)
        changed = deepcopy(base)
        changed["items"][1]["explicit_free"] = True
        invalid.append(changed)
        for amount in ("3.2e1", "+32"):
            changed = deepcopy(base)
            changed["items"][1]["amount"] = amount
            invalid.append(changed)
        changed = deepcopy(base)
        changed["items"][2]["amount"] = "-0"
        changed["items"][2]["explicit_free"] = True
        invalid.append(changed)
        changed = deepcopy(base)
        newer_effective = {
            **changed["items"][1],
            "id": 33,
            "amount": "31",
            "valid_from": "2026-09-29T12:00:00+00:00",
            "is_current": False,
        }
        changed["items"].insert(1, newer_effective)
        changed["count"] = 4
        invalid.append(changed)
        changed = deepcopy(base)
        changed["items"] = [changed["items"][1]]
        changed["count"] = 2
        changed["next_offset"] = True
        invalid.append(changed)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _validate_history(payload, package_id=21)

        boolean_package = deepcopy(base)
        boolean_package["package"] = True
        with self.assertRaises(SmokeFailure):
            _validate_history(boolean_package, package_id=1)

    def test_impact_derives_previous_cost_from_declared_history(self):
        history = _validate_history(history_payload(), package_id=21)
        checked = _validate_impact(
            impact_payload(), recipe_id=11, package_id=21, history=history,
        )
        self.assertEqual(checked["after"], Decimal("2.56"))
        self.assertEqual(checked["before"], Decimal("2.4"))
        self.assertEqual(checked["difference"], Decimal("0.16"))

    def test_impact_keeps_unknown_previous_unknown(self):
        history = _validate_history(history_payload(previous=False), package_id=21)
        checked = _validate_impact(
            impact_payload(previous=False), recipe_id=11, package_id=21, history=history,
        )
        self.assertIsNone(checked["before"])
        self.assertIsNone(checked["difference"])

    def test_impact_rejects_float_money_wrong_identity_and_inconsistent_delta(self):
        history = _validate_history(history_payload(), package_id=21)
        invalid = []
        changed = deepcopy(impact_payload())
        changed["difference"] = 0.16
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["recipe_id"] = 12
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["difference"] = "0.15"
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["after"]["total"] = "2.55"
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["after"]["total"] = "2.56e0"
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["after"]["known_subtotal"] = "+2.56"
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["after"]["servings"] = "4e0"
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        del changed["after"]["warnings"]
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["price_policy"] = ""
        invalid.append(changed)
        changed = deepcopy(impact_payload())
        changed["previous_price_id"] = changed["current_price_id"]
        changed["before"] = deepcopy(changed["after"])
        changed["difference"] = "0"
        changed["difference_per_serving"] = "0"
        invalid.append(changed)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _validate_impact(payload, recipe_id=11, package_id=21, history=history)

        boolean_recipe = deepcopy(impact_payload())
        boolean_recipe["recipe_id"] = True
        with self.assertRaises(SmokeFailure):
            _validate_impact(boolean_recipe, recipe_id=1, package_id=21, history=history)
        boolean_package = deepcopy(impact_payload())
        boolean_package["package"] = True
        with self.assertRaises(SmokeFailure):
            _validate_impact(boolean_package, recipe_id=11, package_id=1, history=history)


if __name__ == "__main__":
    unittest.main()
