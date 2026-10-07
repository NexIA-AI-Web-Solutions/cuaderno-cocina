"""Small, dependency-free behavior tests; database/API coverage is separate."""
import unittest

from cuaderno.services.planning_inputs import InputError, date_range, diet_rows, template_input


class FunctionalInputTests(unittest.TestCase):
    def entry(self, **overrides):
        return dict(day_index=34, meal_type=1, course=None, recipe=2,
                    title="", source_url="", servings="12.50", **overrides)

    def test_five_week_template_preserves_decimal_quantities(self):
        data = template_input({"name": "Cinco semanas", "weeks": 5, "entries": [self.entry()]})
        self.assertEqual(str(data["entries"][0]["servings"]), "12.50")
        self.assertEqual(data["entries"][0]["day_index"], 34)

    def test_outside_template_period_and_duplicate_slot_are_rejected(self):
        for data in ({"name": "Corto", "weeks": 4, "entries": [self.entry()]},
                     {"name": "Duplicado", "weeks": 5, "entries": [self.entry(), self.entry()]}):
            with self.assertRaises(InputError):
                template_input(data)

    def test_invalid_quantity_and_active_reference_are_not_normalized(self):
        for field, values in (("servings", [True, "NaN", "Infinity", "0", "-1", "1e100", "1.23456"]),
                              ("source_url", ["javascript:alert(1)", "data:text/html,x", "https://user:pass@example.com/"])):
            for value in values:
                row = self.entry(); row[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(InputError):
                    template_input({"name": "Prueba", "weeks": 5, "entries": [row]})

    def test_diet_status_is_manual_and_unknown_is_not_suitable(self):
        rows = diet_rows([{"slug": "celiacos", "status": "unknown", "note": "Sin valoración"}])
        self.assertEqual(rows[0]["status"], "unknown")
        for rows in ([{"slug": "celiacos", "status": "safe"}],
                     [{"slug": "inventada", "status": "suitable"}],
                     [{"slug": "diabetes", "status": "unknown"}] * 2):
            with self.assertRaises(InputError):
                diet_rows(rows)

    def test_dates_are_real_and_range_is_bounded(self):
        self.assertEqual((date_range("2026-01-01", "2026-02-04")[1]
                          - date_range("2026-01-01", "2026-02-04")[0]).days, 34)
        for start, end in (("2026-02-30", "2026-03-01"), ("2026-02-01", "2026-01-01"),
                           ("2026-01-01", "2026-02-05")):
            with self.assertRaises(InputError):
                date_range(start, end)


if __name__ == "__main__":
    unittest.main()
