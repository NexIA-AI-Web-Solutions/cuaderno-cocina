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
