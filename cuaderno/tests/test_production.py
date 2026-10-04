from decimal import Decimal
import unittest

from cuaderno.domain.errors import DomainError
from cuaderno.domain.exchange import parse_recipe_document
from cuaderno.domain.production import assert_no_cycle, consolidate, scale_covers


class ProductionTests(unittest.TestCase):
    def test_shared_sauce_is_summed_once(self):
        totals = consolidate([("salsa", "200"), ("salsa", "100"), ("arroz", "750")])
        self.assertEqual(totals["salsa"], Decimal("300"))
        self.assertEqual(len(totals), 2)

    def test_cycle_is_rejected_with_route(self):
        with self.assertRaises(DomainError) as raised:
            assert_no_cycle("A", {"A": ["B"], "B": ["A"]})
        self.assertEqual(raised.exception.code, "recipe_cycle")
        self.assertIn("A", raised.exception.message)

    def test_covers_adjust_without_payment(self):
        self.assertEqual(scale_covers("20", "5", "2"), Decimal("23"))

    def test_consolidation_preserves_full_input_precision_and_order(self):
        quantity = "1234567890123456.1234567890123456"
        self.assertEqual(consolidate([("oil", quantity)])["oil"], Decimal(quantity))
        lines = [("oil", quantity), ("oil", "0.0000000000000001"), ("oil", "1")]
        expected = Decimal("1234567890123457.1234567890123457")
        self.assertEqual(consolidate(lines)["oil"], expected)
        self.assertEqual(consolidate(list(reversed(lines)))["oil"], expected)

    def test_graph_rejects_malformed_and_excessive_input_as_domain_errors(self):
        for graph in [[], {"A": "B"}, {"A": [None]}, {"A": ["x"] * 10001}]:
            with self.subTest(graph_type=type(graph).__name__):
                with self.assertRaises(DomainError):
                    assert_no_cycle("A", graph)
        with self.assertRaises(DomainError):
            assert_no_cycle("0", {str(i): [str(i + 1)] for i in range(1100)})

    def test_import_rejects_missing_name_and_does_not_invent_price(self):
        parsed = parse_recipe_document({"recipes": [{"name": "Caldo", "servings": "4", "ingredients": [{"food": "Aceite", "quantity": "400", "unit": "mL"}]}]})
        self.assertEqual(parsed[0]["name"], "Caldo")
        self.assertNotIn("price", parsed[0])
        with self.assertRaises(DomainError):
            parse_recipe_document({"recipes": [{"servings": "1"}]})
        with self.assertRaises(DomainError):
            parse_recipe_document({"url": "http://127.0.0.1/secret", "recipes": []})
        with self.assertRaises(DomainError):
            parse_recipe_document({"url": "http://169.254.169.254/latest/meta-data"})
        with self.assertRaises(DomainError):
            parse_recipe_document({"recipes": [{"name": "Raciones truncadas", "servings": "1.5"}]})


if __name__ == "__main__":
    unittest.main()
