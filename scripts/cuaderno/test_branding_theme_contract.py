"""Brand theme labels without changing persisted identifiers or database schema."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def theme_choices(name, field="THEMES"):
    module = ast.parse((ROOT / "cookbook/models.py").read_text())
    definition = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name)
    constants = {}
    for node in definition.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant):
                constants[node.targets[0].id] = node.value.value
            if node.targets[0].id == field:
                return [(constants[pair.elts[0].id], ast.literal_eval(pair.elts[1])) for pair in node.value.elts]
    raise AssertionError("Theme choices absent")


class ThemeBrandingContract(unittest.TestCase):
    def test_space_labels_keep_existing_theme_identifiers(self):
        self.assertEqual(theme_choices("Space"), [
            ("BLANK", "-------"), ("TANDOOR", "Cuaderno Cocina"),
            ("BOOTSTRAP", "Cuaderno clásico claro"), ("DARKLY", "Cuaderno clásico oscuro"),
            ("FLATLY", "Cuaderno plano"), ("SUPERHERO", "Cuaderno contraste"),
            ("TANDOOR_DARK", "Cuaderno Cocina oscuro (incompleto)"),
        ])

    def test_user_labels_keep_existing_theme_identifiers(self):
        self.assertEqual(theme_choices("UserPreference"), [
            ("TANDOOR", "Cuaderno Cocina"), ("BOOTSTRAP", "Cuaderno clásico claro"),
            ("DARKLY", "Cuaderno clásico oscuro"), ("FLATLY", "Cuaderno plano"),
            ("SUPERHERO", "Cuaderno contraste"),
            ("TANDOOR_DARK", "Cuaderno Cocina oscuro (incompleto)"),
        ])

    def test_storage_labels_keep_connector_identifiers(self):
        self.assertEqual(theme_choices("Storage", "STORAGE_TYPES"), [
            ("DB", "Archivos remotos · token"),
            ("NEXTCLOUD", "Archivos remotos · usuario y contraseña"),
            ("LOCAL", "Archivos locales"),
        ])

    def test_presentation_migration_has_no_database_operations(self):
        module = ast.parse((ROOT / "cookbook/migrations/0245_cuaderno_theme_labels.py").read_text())
        migration = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Migration")
        operations = next(node.value for node in migration.body if isinstance(node, ast.Assign) and node.targets[0].id == "operations")
        self.assertEqual(len(operations.elts), 1)
        operation = operations.elts[0]
        self.assertEqual(operation.func.attr, "SeparateDatabaseAndState")
        keywords = {node.arg: node.value for node in operation.keywords}
        self.assertEqual(ast.literal_eval(keywords["database_operations"]), [])
        state = keywords["state_operations"].elts
        self.assertEqual(len(state), 3)
        self.assertTrue(all(node.func.attr == "AlterField" for node in state))
        self.assertEqual({tuple((key.arg, ast.literal_eval(key.value)) for key in node.keywords if key.arg in {"model_name", "name"}) for node in state}, {
            (("model_name", "space"), ("name", "space_theme")),
            (("model_name", "userpreference"), ("name", "theme")),
            (("model_name", "storage"), ("name", "method")),
        })


if __name__ == "__main__":
    unittest.main()
