"""Native login themes must keep font requests inside their static deployment."""
from pathlib import Path
import re
import unittest
from urllib.parse import urljoin, urlsplit


STATIC = Path(__file__).resolve().parents[2] / "cookbook" / "static"


class ThemeAssetTests(unittest.TestCase):
    def assert_theme_fonts(self, theme):
        css = (STATIC / "themes" / theme).read_text(encoding="utf-8")
        faces = re.findall(r"@font-face\s*\{([^}]+)\}", css)
        self.assertEqual(len(faces), 9, "All three Poppins subsets and weights must remain available.")
        fonts = []
        for face in faces:
            self.assertRegex(face, r"font-family:\s*'Poppins'")
            source = re.search(r"src:\s*url\(([^)]+)\)\s*format\('woff2'\)", face)
            self.assertIsNotNone(source, "Every font face must reference its local WOFF2 file.")
            fonts.append(source.group(1).strip("\"'"))
        self.assertEqual(
            {Path(source).name for source in fonts},
            {f"poppins_{subset}_{weight}.woff2" for subset in ("devanagari", "latin_ext", "latin") for weight in (400, 500, 700)},
        )
        for prefix in ("/", "/cuaderno-cocina/", "/another-kitchen/"):
            stylesheet = f"https://cocina.example{prefix}static/themes/{theme}"
            for source in fonts:
                with self.subTest(theme=theme, prefix=prefix, font=Path(source).name):
                    resolved = urlsplit(urljoin(stylesheet, source))
                    self.assertEqual(resolved.scheme, "https")
                    self.assertEqual(resolved.netloc, "cocina.example")
                    self.assertEqual(resolved.path, prefix + "static/webfonts/" + Path(source).name)
                    self.assertEqual(resolved.query, "")
                    self.assertEqual(resolved.fragment, "")
                    font = STATIC / "webfonts" / Path(source).name
                    self.assertEqual(font.read_bytes()[:4], b"wOF2", "Resolved assets must be real WOFF2 fonts.")

    def test_light_theme_font_requests_follow_the_stylesheet_prefix(self):
        self.assert_theme_fonts("tandoor.min.css")

    def test_dark_theme_font_requests_follow_the_stylesheet_prefix(self):
        self.assert_theme_fonts("tandoor_dark.min.css")


if __name__ == "__main__":
    unittest.main()
