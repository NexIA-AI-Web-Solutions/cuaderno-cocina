from decimal import Decimal
import unittest

from cuaderno.domain.errors import DomainError
from cuaderno.domain.margin import food_cost_gap, split_yield


class MarginTests(unittest.TestCase):
    def test_yield_is_applied_once(self):
        usable, waste = split_yield("1000", "0.8")
        self.assertEqual(usable, Decimal("800"))
        self.assertEqual(waste, Decimal("200"))
        self.assertEqual(usable + waste, Decimal("1000"))

    def test_yield_above_one_rejected(self):
        with self.assertRaises(DomainError):
            split_yield("10", "1.2")

    def test_unknown_sale_price_is_not_profit(self):
        gap = food_cost_gap("12.50", None, "0.30")
        self.assertEqual(gap["status"], "incomplete")
        self.assertIsNone(gap["net_profit"])

    def test_known_price_reports_ratio_without_profit(self):
        gap = food_cost_gap("30", "100", "0.25")
        self.assertEqual(gap["ratio"], "0.3000")
        self.assertTrue(gap["above_target"])
        self.assertIsNone(gap["net_profit"])
