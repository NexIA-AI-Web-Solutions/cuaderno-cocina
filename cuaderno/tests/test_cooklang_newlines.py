from unittest import TestCase

from cookbook.helper.cooklang_parser import Recipe


class CooklangNewlineTests(TestCase):
    def test_frontmatter_and_body_are_equivalent_for_common_newlines(self):
        lines = [
            "---",
            "Title: Bizcocho sintético",
            "serves: 2",
            "---",
            "Mezclar @harina{1%kg}.",
            "",
            "Reposar.",
        ]

        for label, separator in (("lf", "\n"), ("crlf", "\r\n"), ("cr", "\r")):
            with self.subTest(newline=label):
                recipe = Recipe.parse(separator.join(lines))
                self.assertEqual(recipe.metadata, {"Title": "Bizcocho sintético", "serves": "2"})
                self.assertEqual(len(recipe.ingredients), 1)
                self.assertEqual(recipe.ingredients[0].name, "harina")
                self.assertEqual(recipe.ingredients[0].quantity.amount, 1.0)
                self.assertEqual(recipe.ingredients[0].quantity.unit, "kg")
                self.assertEqual(len(recipe.steps), 2)
                self.assertEqual(
                    [(block.type, block.value) for block in recipe.steps[1].blocks],
                    [("text", "Reposar.")],
                )
