import json
from decimal import Decimal
from pathlib import Path
import unittest

from cuaderno.domain.costing import line_cost, portion_of_batch, scale_amount, sum_lines
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "tests" / "cuaderno" / "contracts" / "costing-cases.json").read_text(
        encoding="utf-8"
    )
)


def _case(case_id):
    return next(item for item in CASES["cases"] if item["id"] == case_id)


class CostingContractTests(unittest.TestCase):
    def test_c001_oil(self):
        case = _case("C001")
        result = line_cost("32.00", "5", "L", "400", "mL")
        self.assertEqual(result.unrounded, Decimal(case["expected_cost_unrounded"]))
        self.assertEqual(result.display, Decimal(case["expected_cost_display"]))
        self.assertEqual(result.status, "complete")

    def test_c002_rice(self):
        case = _case("C002")
        result = line_cost(case["package_price"], case["package_quantity"], case["package_unit"], case["used_quantity"], case["used_unit"])
        self.assertEqual(result.unrounded, Decimal(case["expected_cost_unrounded"]))
        self.assertEqual(result.display, Decimal(case["expected_cost_display"]))

    def test_c003_eggs(self):
        case = _case("C003")
        result = line_cost(case["package_price"], case["package_quantity"], case["package_unit"], case["used_quantity"], case["used_unit"])
        self.assertEqual(result.display, Decimal(case["expected_cost_display"]))

    def test_c004_yield(self):
        case = _case("C004")
        result = line_cost(
            case["package_price"],
            case["package_quantity"],
            case["package_unit"],
            case["used_quantity"],
            case["used_unit"],
            yield_ratio=case["yield_ratio"],
            quantity_basis=case["quantity_basis"],
        )
        self.assertEqual(result.unrounded, Decimal(case["expected_cost_unrounded"]))

    def test_c005_unknown_is_not_zero(self):
        case = _case("C005")
        result = line_cost(None, case["package_quantity"], case["package_unit"], case["used_quantity"], case["used_unit"])
        self.assertEqual(result.status, "incomplete")
        self.assertIsNone(result.unrounded)
        self.assertNotEqual(result.unrounded, Decimal("0"))

    def test_c006_incompatible(self):
        case = _case("C006")
        result = line_cost(
            case["package_price"],
            case["package_quantity"],
            case["package_unit"],
            case["used_quantity"],
            case["used_unit"],
            density=case["density"],
        )
        self.assertEqual(result.status, "needs_conversion")
        self.assertIsNone(result.unrounded)

    def test_c007_scale_does_not_mutate_base(self):
        case = _case("C007")
        base = case["base_ingredient_amount"]
        scaled = scale_amount(base, case["base_servings"], case["requested_servings"])
        self.assertEqual(scaled, Decimal(case["expected_scaled_amount"]))
        self.assertEqual(base, case["expected_base_unchanged"])

    def test_c008_round_at_end(self):
        case = _case("C008")
        result = sum_lines(case["line_costs"])
        self.assertEqual(result.unrounded, Decimal(case["expected_cost_unrounded"]))
        self.assertEqual(result.display, Decimal(case["expected_cost_display"]))

    def test_c009_subrecipe(self):
        case = _case("C009")
        result = portion_of_batch(case["batch_cost"], case["batch_yield_g"], case["used_g"])
        self.assertEqual(result.display, Decimal(case["expected_cost_display"]))

    def test_c010_snapshot_is_not_rewritten(self):
        case = _case("C010")
        snapshot = line_cost(case["old_price"], case["package_quantity"], "L", case["used_quantity_L"], "L")
        current = line_cost(case["new_price"], case["package_quantity"], "L", case["used_quantity_L"], "L")
        self.assertEqual(snapshot.display, Decimal(case["expected_snapshot_cost"]))
        self.assertEqual(current.display, Decimal(case["expected_current_cost"]))

    def test_spanish_comma_and_mixed_separators(self):
        self.assertEqual(parse_decimal("1,25"), Decimal("1.25"))
        with self.assertRaises(DomainError):
            parse_decimal("1.234,56")

    def test_price_change_recalculates(self):
        first = line_cost("32.00", "5", "L", "400", "mL")
        second = line_cost("35.00", "5", "L", "400", "mL")
        self.assertEqual(first.display, Decimal("2.56"))
        self.assertEqual(second.display, Decimal("2.80"))


if __name__ == "__main__":
    unittest.main()
