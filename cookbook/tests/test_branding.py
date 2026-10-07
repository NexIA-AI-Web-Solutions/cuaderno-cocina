"""Branding behavior without a database, network or optional Django installation."""
import ast
import datetime
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
BRAND = 'Cuaderno Cocina'


def function(relative, name, namespace):
    tree = ast.parse((ROOT / relative).read_text())
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(ROOT / relative), 'exec'), namespace)
    return namespace[name]


def setting(name, prefix='', environment=None):
    tree = ast.parse((ROOT / 'recipes/settings.py').read_text())
    node = next(item for item in tree.body if isinstance(item, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == name for target in item.targets))
    return eval(compile(ast.Expression(node.value), 'settings-branding', 'eval'), {
        'os': SimpleNamespace(getenv=lambda key, default=None: (environment or {}).get(key, default)),
        'STATIC_URL': prefix + '/static/', 'SCRIPT_NAME': prefix,
    })


def theme(prefix='', space=None):
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False), space=space)
    namespace = {
        'UserPreference': SimpleNamespace(TANDOOR='TANDOOR', TANDOOR_DARK='TANDOOR_DARK'),
        'Space': SimpleNamespace(DARK='DARK', LIGHT='LIGHT'),
        'UNAUTHENTICATED_THEME_FROM_SPACE': 0, 'FORCE_THEME_FROM_SPACE': 0,
        'static': lambda value: prefix + '/static/' + value,
    }
    return function('cookbook/templatetags/theming_tags.py', 'get_theming_values', namespace)(request)


class BrandingTests(unittest.TestCase):
    def test_default_brand_and_new_icon_urls_work_at_root_and_prefix(self):
        for prefix in ['', '/cuaderno-cocina']:
            with self.subTest(prefix=prefix):
                values = theme(prefix)
                self.assertEqual(values['app_name'], BRAND)
                for key, value in values.items():
                    if key.startswith('logo_color_') or key == 'nav_logo':
                        self.assertTrue(value.startswith(prefix + '/static/cuaderno/cuaderno-'), (key, value))
                        relative = value.removeprefix(prefix + '/static/')
                        self.assertTrue((ROOT / 'cookbook/static' / relative).is_file(), relative)

    def test_existing_space_branding_and_native_theme_codes_are_preserved(self):
        upload = SimpleNamespace(file=SimpleNamespace(url='/cuaderno-cocina/media/my-brand.svg'))
        space = SimpleNamespace(logo_color_svg=upload, custom_space_theme=None, space_theme='TANDOOR_DARK',
                                nav_logo=upload, nav_bg_color='#223344', nav_text_color='', app_name='Mi cocina')
        values = theme('/cuaderno-cocina', space)
        self.assertEqual(values['app_name'], 'Mi cocina')
        self.assertEqual(values['logo_color_svg'], upload.file.url)
        self.assertEqual(values['nav_logo'], upload.file.url)
        self.assertEqual(values['nav_bg_color'], '#223344')
        self.assertEqual(values['theme'], '/cuaderno-cocina/static/themes/tandoor_dark.min.css')

    def test_actual_manifest_uses_brand_icons_and_preserves_prefix_navigation(self):
        for prefix in ['', '/cuaderno-cocina']:
            with self.subTest(prefix=prefix):
                namespace = {'get_theming_values': lambda request: theme(prefix), '_': lambda value: value,
                             'static': lambda value: prefix + '/static/' + value,
                             'reverse': lambda name: prefix + '/',
                             'JsonResponse': lambda value, **kwargs: value}
                manifest = function('cookbook/views/views.py', 'web_manifest', namespace)(object())
                self.assertEqual(manifest['name'], BRAND)
                self.assertEqual(manifest['short_name'], BRAND)
                self.assertEqual(manifest['start_url'], './')
                self.assertEqual(manifest['scope'], '.')
                self.assertEqual(manifest['share_target']['action'], prefix + '/recipe/import')
                icons = manifest['icons'] + [icon for shortcut in manifest['shortcuts'] for icon in shortcut['icons']]
                for icon in icons:
                    self.assertTrue(icon['src'].startswith(prefix + '/static/cuaderno/cuaderno-'), icon)

    def test_schema_logo_navigation_and_email_defaults_share_the_brand(self):
        for prefix in ['', '/cuaderno-cocina']:
            with self.subTest(prefix=prefix):
                schema = setting('SPECTACULAR_SETTINGS', prefix)
                self.assertEqual(schema['TITLE'], BRAND)
                self.assertEqual(schema['DESCRIPTION'], BRAND + ' API Docs')
                logo = schema['EXTENSIONS_INFO']['x-logo']
                self.assertEqual(logo['url'], prefix + '/static/cuaderno/cuaderno-logo.svg')
                self.assertEqual(logo['altText'], BRAND + ' logo')
                self.assertEqual(schema['SWAGGER_UI_FAVICON_HREF'], prefix + '/static/cuaderno/cuaderno-mark.svg')
                self.assertEqual(logo['href'], prefix + '/')
        self.assertEqual(setting('ACCOUNT_EMAIL_SUBJECT_PREFIX'), '[' + BRAND + '] ')
        self.assertEqual(setting('ACCOUNT_EMAIL_SUBJECT_PREFIX', environment={'ACCOUNT_EMAIL_SUBJECT_PREFIX': '[Custom] '}), '[Custom] ')

    def test_login_shell_and_vue_document_expose_the_product_brand(self):
        base = (ROOT / 'cookbook/templates/base.html').read_text()
        frontend = (ROOT / 'cookbook/templates/frontend/tandoor.html').read_text()
        system = (ROOT / 'cookbook/templates/system.html').read_text()
        self.assertIn('aria-label="Cuaderno Cocina"', base)
        self.assertIn('alt="Cuaderno Cocina"', base)
        self.assertIn('Cuaderno Cocina</title>', base)
        self.assertIn('<title>Cuaderno Cocina</title>', frontend)
        self.assertNotIn('Tandoor Recipe Manager', frontend)
        self.assertIn('<title>Cuaderno Cocina</title>', system)
        self.assertNotIn('Tandoor Recipes is', system)
        self.assertNotIn('github.com/TandoorRecipes', system)
        self.assertIn('github.com/NexIA-AI-Web-Solutions/cuaderno-cocina', system)

    def test_invite_display_messages_use_product_name_and_fork(self):
        tree = ast.parse((ROOT / 'cookbook/serializer.py').read_text())
        translated = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call) and
                      isinstance(node.func, ast.Name) and node.func.id == '_' and node.args and
                      isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)]
        self.assertFalse(any('Tandoor' in value for value in translated))
        self.assertIn('Invitación a Cuaderno Cocina', translated)
        self.assertIn('https://github.com/NexIA-AI-Web-Solutions/cuaderno-cocina',
                      [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)])

    def test_help_error_and_api_shell_links_present_own_product(self):
        for name in ['markdown_info.html', '404.html', 'rest_framework/api.html', 'system.html']:
            with self.subTest(template=name):
                content = (ROOT / 'cookbook/templates' / name).read_text()
                self.assertNotIn('github.com/vabene1111/recipes', content)
                self.assertNotIn('django-rest-framework.org', content)
                self.assertNotIn('Django REST framework', content)
        legacy_manifest = (ROOT / 'cookbook/templates/manifest.json').read_text()
        self.assertIn('"name": "Cuaderno Cocina"', legacy_manifest)
        self.assertNotIn('"src": "/static/', legacy_manifest)

    def test_png_derivatives_have_real_declared_icon_dimensions(self):
        for size in [32, 128, 144, 180, 192, 512]:
            with self.subTest(size=size):
                data = (ROOT / f'cookbook/static/cuaderno/cuaderno-icon-{size}.png').read_bytes()
                self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('>II', data[16:24]), (size, size))

    def test_calendar_product_label_changes_without_rekeying_subscription_events(self):
        class Calendar:
            def __init__(self):
                self.properties, self.events = {}, []

            def add(self, key, value):
                self.properties[key] = value

            def add_component(self, value):
                self.events.append(value)

            def to_ical(self):
                return json.dumps({'properties': self.properties, 'events': self.events}, default=str)

        class Event(dict):
            def add(self, key, value):
                self[key] = value

        class Response(dict):
            def __init__(self, body, **kwargs):
                super().__init__()
                self.body = body

        plan = SimpleNamespace(id=42, from_date=datetime.datetime(2030, 1, 1), to_date=None,
                               meal_type=SimpleNamespace(name='Almuerzo'), get_label=lambda: 'Plan', note='Nota')
        namespace = {'Calendar': Calendar, 'Event': Event, 'HttpResponse': Response, 'datetime': datetime}
        response = function('cookbook/views/api.py', 'meal_plans_to_ical', namespace)([plan], 'plan.ics')
        data = json.loads(response.body)
        self.assertEqual(data['properties']['prodid'], '-//Cuaderno Cocina//')
        self.assertEqual(data['events'][0]['uid'], 'mealplan-42@tandoor.recipes')


if __name__ == '__main__':
    unittest.main()
