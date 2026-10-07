import unittest

from cuaderno.domain.features import feature_flags, supports_feature


class CommercialFeatureTests(unittest.TestCase):
    def test_higher_editions_preserve_every_lower_edition_workflow(self):
        essential = {key for key, enabled in feature_flags("esencial").items() if enabled}
        professional = {key for key, enabled in feature_flags("profesional").items() if enabled}
        integral = {key for key, enabled in feature_flags("integral").items() if enabled}
        self.assertLess(essential, professional)
        self.assertLess(professional, integral)

    def test_core_recipe_enhancements_do_not_require_professional(self):
        for name in ("recipe_gallery", "recipe_favorites", "recipe_variants", "diet_declarations", "menu_five_weeks"):
            self.assertTrue(supports_feature("esencial", name), name)

    def test_professional_workflows_and_integral_merge_are_distinct(self):
        self.assertFalse(supports_feature("esencial", "menu_templates"))
        self.assertTrue(supports_feature("profesional", "menu_templates"))
        self.assertFalse(supports_feature("profesional", "merged_menu_print"))
        self.assertTrue(supports_feature("integral", "merged_menu_print"))

    def test_unknown_editions_and_features_never_grant_access(self):
        self.assertFalse(any(feature_flags("unknown").values()))
        self.assertFalse(supports_feature("unknown", "merged_menu_print"))
        self.assertFalse(supports_feature("integral", "unknown"))

    def test_callers_cannot_mutate_the_next_requests_feature_flags(self):
        flags = feature_flags("esencial")
        flags["merged_menu_print"] = True
        self.assertFalse(feature_flags("esencial")["merged_menu_print"])
