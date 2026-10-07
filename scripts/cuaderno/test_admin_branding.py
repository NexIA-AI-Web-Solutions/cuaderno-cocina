"""Exercise admin presentation assignments from the actual URL configuration."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]

class AdminBranding(unittest.TestCase):
    def configure(self, prefix):
        module = ast.parse((ROOT / 'recipes/urls.py').read_text())
        assignments = [node for node in module.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute) and isinstance(target.value.value, ast.Name) and target.value.value.id == 'admin' for target in node.targets)]
        site = SimpleNamespace(site_header='Django administration', site_title='Django site admin', index_title='Site administration', site_url='/')
        exec(compile(ast.fix_missing_locations(ast.Module(body=assignments, type_ignores=[])), 'actual-admin-configuration', 'exec'), {'admin': SimpleNamespace(site=site), 'settings': SimpleNamespace(SCRIPT_NAME=prefix)})
        return site

    def test_native_admin_displays_own_product(self):
        site = self.configure('/cuaderno-cocina')
        self.assertEqual(site.site_header, 'Cuaderno Cocina')
        self.assertEqual(site.site_title, 'Cuaderno Cocina')
        self.assertEqual(site.index_title, 'Administración de Cuaderno Cocina')

    def test_return_link_keeps_app_prefix(self):
        for prefix, expected in [('', '/'), ('/cuaderno-cocina', '/cuaderno-cocina/'), ('/cuaderno-cocina/', '/cuaderno-cocina/')]:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.configure(prefix).site_url, expected)

if __name__ == '__main__': unittest.main()
