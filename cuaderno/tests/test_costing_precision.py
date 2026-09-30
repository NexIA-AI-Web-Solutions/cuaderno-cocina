"""Exact Decimal arithmetic contracts for costing, without database access."""

from decimal import Decimal, getcontext, setcontext
import unittest

from cuaderno.domain.costing import line_cost, portion_of_batch, sum_lines


MAX_INPUT = "9999999999999999.9999999999999999"
FINITE_64_DIGIT_RESULT = (
    "99999999999999999.99999999999999800000000000000000000000000000001"
)


class CostingPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.original_context = getcontext().copy()
        getcontext().prec = 28

    def tearDown(self):
        setcontext(self.original_context)

    def test_line_cost_multiplies_before_dividing_for_exact_thirds(self):
        result = line_cost("1", "3", "unit", "3", "unit")

        self.assertEqual(result.unrounded, Decimal("1"))
        self.assertEqual(result.display, Decimal("1.00"))
        self.assertEqual(result.as_dict()["unrounded"], "1")
        self.assertEqual(result.as_dict()["total"], "1")

    def test_line_cost_preserves_a_finite_64_digit_intermediate(self):
        # (10^16 - 10^-16)^2 / 10^15, expanded independently by hand:
        # 10^17 - 2*10^-15 + 10^-47.
        result = line_cost(
            MAX_INPUT,
            "1000000000000000",
            "unit",
            MAX_INPUT,
            "unit",
        )

        self.assertEqual(result.unrounded, Decimal(FINITE_64_DIGIT_RESULT))
        self.assertEqual(result.as_dict()["unrounded"], FINITE_64_DIGIT_RESULT)
        self.assertEqual(result.display, Decimal("100000000000000000.00"))
        self.assertEqual(getcontext().prec, 28)

    def test_net_yield_is_applied_once_and_gross_quantity_is_not_inflated(self):
        net = line_cost(
            "1",
            "3",
            "unit",
            "3",
            "unit",
            yield_ratio="0.8",
            quantity_basis="net_usable",
        )
        gross = line_cost(
            "1",
            "3",
            "unit",
            "3",
            "unit",
            yield_ratio="0.8",
            quantity_basis="gross",
        )

        self.assertEqual(net.unrounded, Decimal("1.25"))
        self.assertEqual(Decimal(net.as_dict()["unrounded"]), Decimal("1.25"))
        self.assertEqual(gross.unrounded, Decimal("1"))
        self.assertEqual(Decimal(gross.as_dict()["unrounded"]), Decimal("1"))

    def test_sum_lines_preserves_a_33_digit_exact_total(self):
        result = sum_lines([MAX_INPUT, MAX_INPUT])

        expected = Decimal("19999999999999999.9999999999999998")
        self.assertEqual(result.unrounded, expected)
        self.assertEqual(result.as_dict()["unrounded"], format(expected, "f"))
        self.assertEqual(result.display, Decimal("20000000000000000.00"))
        self.assertEqual(getcontext().prec, 28)

    def test_large_derived_subrecipe_cost_can_still_be_displayed_in_cents(self):
        # All original operands fit native32/16 fields. Derived batch costs
        # are not persisted price inputs and can exceed64 integer places.
        child = line_cost("1000000000000000", "0.0000000000000001", "g",
                          "1000000000000000", "g")
        parent = portion_of_batch(child.unrounded, "0.0000000000000001", "1000000000000000")
        self.assertEqual(parent.unrounded, Decimal("1e77"))
        self.assertEqual(parent.as_dict()["display"], "1" + "0" * 77 + ".00")
        self.assertEqual(getcontext().prec, 28)

    def test_portion_of_batch_preserves_a_finite_64_digit_intermediate(self):
        result = portion_of_batch(
            MAX_INPUT,
            "1000000000000000",
            MAX_INPUT,
        )

        self.assertEqual(result.unrounded, Decimal(FINITE_64_DIGIT_RESULT))
        self.assertEqual(result.as_dict()["unrounded"], FINITE_64_DIGIT_RESULT)
        self.assertEqual(result.display, Decimal("100000000000000000.00"))
        self.assertEqual(getcontext().prec, 28)

    def test_unknown_and_explicit_free_remain_distinct_without_context_mutation(self):
        unknown = line_cost(None, "3", "unit", "3", "unit")
        free = line_cost(
            "0",
            "3",
            "unit",
            "3",
            "unit",
            explicit_free=True,
        )

        self.assertEqual(unknown.status, "incomplete")
        self.assertIsNone(unknown.unrounded)
        self.assertIsNone(unknown.as_dict()["total"])
        self.assertEqual(free.status, "complete")
        self.assertEqual(free.unrounded, Decimal("0"))
        self.assertEqual(free.display, Decimal("0.00"))
        self.assertEqual(free.as_dict()["unrounded"], "0")
        self.assertEqual(getcontext().prec, 28)


if __name__ == "__main__":
    unittest.main()
