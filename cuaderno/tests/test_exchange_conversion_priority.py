from dataclasses import dataclass
from decimal import Decimal
from unittest import TestCase

from cuaderno.domain.errors import DomainError
from cuaderno.domain.exchange_conversions import (
    validate_conversion_precedence,
    validate_destination_conversion_graph,
)


@dataclass(frozen=True)
class NativeConversion:
    pk: int


@dataclass(frozen=True)
class NativeObject:
    pk: int


def conversion(food, base, converted, base_amount="1", converted_amount="1"):
    return {
        "food_ref": food,
        "base_unit_ref": base,
        "converted_unit_ref": converted,
        "base_amount": Decimal(base_amount),
        "converted_amount": Decimal(converted_amount),
    }


class ExchangeConversionPriorityTests(TestCase):
    def test_new_edge_before_older_mapped_inverse_is_rejected(self):
        catalog = {
            "conversion:a": conversion("food:a", "unit:g", "unit:ml", "920", "1000"),
            "conversion:b": conversion("food:a", "unit:ml", "unit:g", "1000", "1840"),
        }
        with self.assertRaises(DomainError) as raised:
            validate_conversion_precedence(
                catalog,
                {"conversion:a": None, "conversion:b": NativeConversion(7)},
            )
        self.assertEqual(raised.exception.code, "conversion_precedence")
        self.assertIn("prioridad", raised.exception.message.lower())

    def test_mapped_ambiguous_edges_require_strictly_increasing_pks(self):
        catalog = {
            "conversion:a": conversion(None, "unit:g", "unit:ml"),
            "conversion:b": conversion(None, "unit:ml", "unit:g"),
        }
        validate_conversion_precedence(
            catalog,
            {"conversion:a": NativeConversion(4), "conversion:b": NativeConversion(9)},
        )
        with self.assertRaises(DomainError) as raised:
            validate_conversion_precedence(
                catalog,
                {"conversion:a": NativeConversion(9), "conversion:b": NativeConversion(4)},
            )
        self.assertEqual(raised.exception.code, "conversion_precedence")

    def test_all_new_ambiguous_edges_preserve_document_creation_order(self):
        catalog = {
            "conversion:a": conversion("food:a", "unit:g", "unit:ml", "920", "1000"),
            "conversion:b": conversion("food:a", "unit:ml", "unit:g", "1000", "1840"),
            "conversion:c": conversion("food:a", "unit:g", "unit:g", "1", "1"),
        }
        self.assertIsNone(validate_conversion_precedence(catalog, {ref: None for ref in catalog}))

    def test_mapped_edge_before_new_ambiguous_edge_is_safe(self):
        catalog = {
            "conversion:mapped": conversion(None, "unit:g", "unit:ml"),
            "conversion:new": conversion(None, "unit:ml", "unit:g"),
        }
        self.assertIsNone(
            validate_conversion_precedence(
                catalog,
                {"conversion:mapped": NativeConversion(50), "conversion:new": None},
            )
        )

    def test_unique_path_tree_allows_new_specific_before_mapped_global(self):
        catalog = {
            "conversion:specific": conversion("food:a", "unit:g", "unit:ml", "920", "1000"),
            "conversion:global": conversion(None, "unit:ml", "unit:l", "1000", "1"),
        }
        self.assertIsNone(
            validate_conversion_precedence(
                catalog,
                {"conversion:specific": None, "conversion:global": NativeConversion(3)},
            )
        )

    def test_food_specific_edges_for_different_foods_do_not_compete(self):
        catalog = {
            "conversion:a": conversion("food:a", "unit:g", "unit:ml"),
            "conversion:b": conversion("food:b", "unit:ml", "unit:g"),
        }
        self.assertIsNone(
            validate_conversion_precedence(
                catalog,
                {"conversion:a": None, "conversion:b": NativeConversion(1)},
            )
        )

    def test_global_and_specific_parallel_edges_compete_for_that_food(self):
        catalog = {
            "conversion:specific": conversion("food:a", "unit:g", "unit:ml", "920", "1000"),
            "conversion:global": conversion(None, "unit:g", "unit:ml", "1", "1"),
        }
        with self.assertRaises(DomainError):
            validate_conversion_precedence(
                catalog,
                {"conversion:specific": None, "conversion:global": NativeConversion(2)},
            )

    def test_cyclic_diamond_checks_the_whole_ambiguous_component(self):
        catalog = {
            "conversion:ab": conversion("food:a", "unit:a", "unit:b"),
            "conversion:ac": conversion("food:a", "unit:a", "unit:c"),
            "conversion:bd": conversion("food:a", "unit:b", "unit:d"),
            "conversion:cd": conversion("food:a", "unit:c", "unit:d"),
            "conversion:de": conversion("food:a", "unit:d", "unit:e"),
        }
        validate_conversion_precedence(
            catalog,
            {ref: NativeConversion(index) for index, ref in enumerate(catalog, start=10)},
        )
        resolved = {
            "conversion:ab": NativeConversion(10),
            "conversion:ac": NativeConversion(11),
            "conversion:bd": NativeConversion(12),
            "conversion:cd": NativeConversion(13),
            "conversion:de": NativeConversion(2),
        }
        with self.assertRaises(DomainError):
            validate_conversion_precedence(catalog, resolved)

    def test_self_edges_are_harmless_and_decimal_values_are_not_coerced(self):
        catalog = {
            "conversion:self": conversion(None, "unit:g", "unit:g", "1.000", "1.000"),
            "conversion:tree": conversion(None, "unit:g", "unit:kg", "1000", "1"),
        }
        original = {ref: dict(item) for ref, item in catalog.items()}
        validate_conversion_precedence(
            catalog,
            {"conversion:self": None, "conversion:tree": NativeConversion(1)},
        )
        self.assertEqual(catalog, original)
        self.assertTrue(all(isinstance(item["base_amount"], Decimal) for item in catalog.values()))


class DestinationConversionGraphTests(TestCase):
    def setUp(self):
        self.catalog = {
            "conversion:a": conversion("food:a", "unit:g", "unit:bridge", "920", "1000"),
            "conversion:b": conversion("food:a", "unit:bridge", "unit:ml", "1000", "1000"),
        }
        self.resolved_conversions = {ref: None for ref in self.catalog}
        self.resolved_units = {
            "unit:g": NativeObject(10),
            "unit:bridge": NativeObject(20),
            "unit:ml": NativeObject(30),
        }
        self.resolved_foods = {"food:a": NativeObject(40)}

    def validate(self, rows):
        return validate_destination_conversion_graph(
            self.catalog,
            self.resolved_conversions,
            self.resolved_units,
            self.resolved_foods,
            rows,
        )

    def test_extra_direct_edge_that_closes_source_tree_is_rejected(self):
        rows = [{"id": 5, "food_id": 40, "base_unit_id": 10, "converted_unit_id": 30}]
        with self.assertRaises(DomainError) as raised:
            self.validate(rows)
        self.assertEqual(raised.exception.code, "conversion_precedence")

    def test_extra_leaf_extension_is_allowed(self):
        rows = [{"id": 5, "food_id": 40, "base_unit_id": 30, "converted_unit_id": 50}]
        self.assertIsNone(self.validate(rows))

    def test_disconnected_extra_cycle_and_other_food_are_allowed(self):
        rows = [
            {"id": 5, "food_id": 40, "base_unit_id": 50, "converted_unit_id": 60},
            {"id": 6, "food_id": 40, "base_unit_id": 60, "converted_unit_id": 50},
            {"id": 7, "food_id": 99, "base_unit_id": 10, "converted_unit_id": 30},
        ]
        self.assertIsNone(self.validate(rows))

    def test_global_extra_edge_competes_with_mapped_food_specific_source(self):
        rows = [{"id": 5, "food_id": None, "base_unit_id": 10, "converted_unit_id": 30}]
        with self.assertRaises(DomainError):
            self.validate(rows)

    def test_specific_extra_competes_with_global_source_for_mapped_catalog_food(self):
        catalog = {
            ref: {**item, "food_ref": None}
            for ref, item in self.catalog.items()
        }
        rows = [{"id": 5, "food_id": 40, "base_unit_id": 10, "converted_unit_id": 30}]
        with self.assertRaises(DomainError):
            validate_destination_conversion_graph(
                catalog,
                self.resolved_conversions,
                self.resolved_units,
                self.resolved_foods,
                rows,
            )

    def test_self_edge_is_harmless(self):
        rows = [{"id": 5, "food_id": 40, "base_unit_id": 10, "converted_unit_id": 10}]
        self.assertIsNone(self.validate(rows))

    def test_mapped_conversion_row_already_represented_by_catalog_is_omitted(self):
        resolved = {
            "conversion:a": NativeConversion(5),
            "conversion:b": NativeConversion(6),
        }
        rows = [
            {"id": 5, "food_id": 40, "base_unit_id": 10, "converted_unit_id": 20},
            {"id": 6, "food_id": 40, "base_unit_id": 20, "converted_unit_id": 30},
        ]
        self.assertIsNone(
            validate_destination_conversion_graph(
                self.catalog,
                resolved,
                self.resolved_units,
                self.resolved_foods,
                rows,
            )
        )

    def test_new_source_refs_cannot_collide_with_numeric_native_ids(self):
        catalog = {
            "conversion:new": conversion("food:new", "7", "8"),
        }
        rows = [
            {"id": 5, "food_id": None, "base_unit_id": 7, "converted_unit_id": 8},
            {"id": 6, "food_id": None, "base_unit_id": 8, "converted_unit_id": 7},
        ]
        self.assertIsNone(
            validate_destination_conversion_graph(
                catalog,
                {"conversion:new": None},
                {"7": None, "8": None},
                {"food:new": None},
                rows,
            )
        )

    def test_absent_conversion_catalog_skips_destination_guarantee(self):
        self.assertIsNone(
            validate_destination_conversion_graph({}, {}, {}, {}, "legacy document has no conversion graph")
        )

    def test_inputs_and_decimal_metadata_are_not_mutated(self):
        rows = [{"id": 5, "food_id": 40, "base_unit_id": 30, "converted_unit_id": 50}]
        original_catalog = {ref: dict(item) for ref, item in self.catalog.items()}
        original_rows = [dict(row) for row in rows]
        self.validate(rows)
        self.assertEqual(self.catalog, original_catalog)
        self.assertEqual(rows, original_rows)
        self.assertTrue(all(isinstance(item["base_amount"], Decimal) for item in self.catalog.values()))


if __name__ == "__main__":
    import unittest

    unittest.main()
