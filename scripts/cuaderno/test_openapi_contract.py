"""Consumer-critical contracts in the reproducible OpenAPI/SDK source snapshot."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "tooling/cuaderno/openapi.json").read_text(encoding="utf-8"))
        cls.models = cls.schema["components"]["schemas"]

    def test_create_drafts_do_not_require_generated_ids_but_responses_do(self):
        for name in ("Food", "Unit", "Keyword", "Ingredient", "Step", "Recipe"):
            with self.subTest(model=name):
                self.assertIn("id", self.models[name]["required"])
                self.assertNotIn("id", self.models[name + "Request"].get("required", []))

    def test_checked_concurrency_header_and_readiness_are_public_contracts(self):
        path = self.schema["paths"]["/api/shopping-list-entry/{id}/"]
        for method in ("put", "patch"):
            headers = [parameter for parameter in path[method]["parameters"] if parameter["name"] == "If-Match"]
            self.assertEqual(len(headers), 1)
            self.assertEqual(headers[0]["in"], "header")
            self.assertIn("428", headers[0]["description"])
            self.assertIn("409", headers[0]["description"])
        ready = self.schema["paths"]["/health/ready/"]["get"]["responses"]
        self.assertEqual(set(ready), {"200", "503"})
        self.assertEqual(self.models["Ready"]["properties"]["ready"]["type"], "boolean")

    def test_operations_have_unique_ids_and_production_has_three_named_results(self):
        identifiers = [operation["operationId"] for path in self.schema["paths"].values()
                       for method, operation in path.items() if method in {"get", "post", "put", "patch", "delete"}]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        branches = self.models["CuadernoProductionResponse"]["oneOf"]
        self.assertEqual({row["$ref"].rsplit("/", 1)[-1] for row in branches},
                         {"ManualProductionResultSchema", "ServiceProductionSheetSchema", "ServiceProductionResultSchema"})
        properties = self.models["ComputedPropertySchema"]["properties"]
        self.assertTrue({"food_values", "missing_value", "total_value"}.issubset(properties))
