"""Walk native Step.step_recipe and Food.recipe. Does not create a second recipe tree."""

from __future__ import annotations

from cookbook.models import Food, Recipe
from cuaderno.domain.production import assert_no_cycle, consolidate


def sheet_from_recipes(recipe_ids, space) -> dict:
    recipes = list(Recipe.objects.filter(space=space, pk__in=recipe_ids).prefetch_related("steps__ingredients__food", "steps__step_recipe"))
    edges: dict[str, list[str]] = {}
    usages: list[tuple[str, str]] = []
    for recipe in recipes:
        parent = str(recipe.id)
        for step in recipe.steps.all():
            if step.step_recipe_id:
                edges.setdefault(parent, []).append(str(step.step_recipe_id))
            for ingredient in step.ingredients.all():
                if ingredient.is_header or ingredient.no_amount or not ingredient.food_id:
                    continue
                usages.append((ingredient.food.name, format(ingredient.amount, "f")))
                linked = ingredient.food.recipe_id
                if linked:
                    edges.setdefault(parent, []).append(str(linked))
    for recipe in recipes:
        assert_no_cycle(str(recipe.id), edges)
    foods = Food.objects.filter(space=space, recipe_id__isnull=False).only("id", "recipe_id")
    for food in foods:
        edges.setdefault(f"food-{food.id}", []).append(str(food.recipe_id))
    totals = consolidate(usages)
    return {"needs": {key: format(value, "f") for key, value in totals.items()}, "edges": edges}
