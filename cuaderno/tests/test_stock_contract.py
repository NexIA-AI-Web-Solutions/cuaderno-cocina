import json
from decimal import Decimal
from pathlib import Path
import unittest

from cuaderno.domain.errors import DomainError
from cuaderno.domain.stock import consume, packs_to_buy, receive, waste_value

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "tests" / "cuaderno" / "contracts" / "stock-cases.json").read_text(encoding="utf-8")
)


def _case(case_id):
    return next(item for item in CASES["cases"] if item["id"] == case_id)


class StockContractTests(unittest.TestCase):
    def test_s001_retry_receives_once(self):
        case = _case("S001")
        balance = Decimal(case["initial_quantity"])
        movements = []
        fingerprint = case["received"]
        for _ in range(case["retries"] + 1):
            balance, movements = receive(balance, case["received"], movements, key=case["idempotency_key"], fingerprint=fingerprint)
        self.assertEqual(balance, Decimal(case["expected_final_quantity"]))
        self.assertEqual(len(movements), case["expected_new_receipt_movements"])

    def test_s002_second_consume_fails(self):
        case = _case("S002")
        balance = Decimal(case["initial_quantity"])
        successes = 0
        failures = 0
        for quantity in case["concurrent_consumptions"]:
            try:
                balance = consume(balance, quantity, allow_negative=case["negative_stock_allowed"])
                successes += 1
            except DomainError:
                failures += 1
        self.assertEqual(successes, case["expected_successes"])
        self.assertEqual(failures, case["expected_failures"])
        self.assertIn(format(balance, "f"), case["allowed_final_quantities"])

    def test_s003_order_does_not_change_stock(self):
        case = _case("S003")
        self.assertEqual(Decimal(case["initial_quantity"]), Decimal(case["expected_final_quantity"]))
        self.assertNotEqual(Decimal(case["purchase_order_quantity"]), Decimal("0"))

    def test_s004_plan_does_not_consume(self):
        case = _case("S004")
        self.assertFalse(case["confirmed_production"])
        self.assertEqual(Decimal(case["initial_quantity"]), Decimal(case["expected_final_quantity"]))

    def test_s005_packs(self):
        case = _case("S005")
        packs, quantity = packs_to_buy(case["required"], case["usable_stock"], case["pack_size"])
        self.assertEqual(packs, Decimal(case["expected_packs_to_buy"]))
        self.assertEqual(quantity, Decimal(case["expected_quantity_to_buy"]))

    def test_s006_different_payload_conflicts(self):
        case = _case("S006")
        balance, movements = receive("10", case["first_payload_quantity"], [], key="same", fingerprint=case["first_payload_quantity"])
        with self.assertRaises(DomainError) as raised:
            receive(balance, case["retry_payload_quantity"], movements, key="same", fingerprint=case["retry_payload_quantity"])
        self.assertEqual(raised.exception.code, "idempotency_conflict")
        self.assertEqual(len(movements), 1)

    def test_s007_waste(self):
        case = _case("S007")
        balance = consume(case["initial_quantity"], case["waste_quantity"])
        self.assertEqual(balance, Decimal(case["expected_final_quantity"]))
        self.assertEqual(waste_value(case["waste_quantity"], case["unit_valuation"]), Decimal(case["expected_waste_value"]))


if __name__ == "__main__":
    unittest.main()
