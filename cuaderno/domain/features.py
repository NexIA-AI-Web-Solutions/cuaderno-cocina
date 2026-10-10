"""Commercial capabilities for additive Cuaderno workflows.

Native recipe, calendar and shopping permissions remain authoritative.
Diet declarations store a user's assessment; they do not infer suitability.
"""

ESSENTIAL_FEATURES = frozenset({
    "recipe_gallery", "recipe_favorites", "recipe_variants",
    "diet_declarations", "menu_five_weeks",
})
PROFESSIONAL_FEATURES = ESSENTIAL_FEATURES | frozenset({
    "menu_courses", "menu_templates", "menu_diet_filter",
    "calendar_events", "staff_absences", "menu_print", "customer_reservations",
})
INTEGRAL_FEATURES = PROFESSIONAL_FEATURES | frozenset({"merged_menu_print"})
EDITION_FEATURES = {
    "esencial": ESSENTIAL_FEATURES,
    "profesional": PROFESSIONAL_FEATURES,
    "integral": INTEGRAL_FEATURES,
}


def feature_flags(edition):
    enabled = EDITION_FEATURES.get(edition, frozenset())
    return {name: name in enabled for name in sorted(INTEGRAL_FEATURES)}


def supports_feature(edition, name):
    return name in EDITION_FEATURES.get(edition, frozenset())
