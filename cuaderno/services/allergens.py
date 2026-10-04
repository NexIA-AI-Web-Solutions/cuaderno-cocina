"""Declared/unknown information; lack of a declaration never proves absence."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound

from cuaderno.models import AllergenDeclaration
from cuaderno.services.subrecipes import native_recipe_graph
from cuaderno.services.visibility import visible_foods


def _assessment(scope, foods, space, *, unknown_ingredients=False):
    latest = {}
    identifiers = {food.pk for food in foods}
    declarations = AllergenDeclaration.objects.filter(
        space=space, food_id__in=identifiers,
    ).order_by("-pk").values("id", "food_id", "name", "state", "created_by_id", "created_at")
    for row in declarations:
        latest.setdefault((row["food_id"], row["name"].strip().casefold()), {
            "id": row["id"], "name": row["name"],
            "created_by": row["created_by_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "state": (row["state"] if row["state"] in (
                AllergenDeclaration.DECLARED, AllergenDeclaration.UNKNOWN,
            ) else AllergenDeclaration.UNKNOWN),
        })
    rows = []
    declared = False
    by_food = {}
    for (food_id, _), declaration in latest.items():
        by_food.setdefault(food_id, []).append(declaration)
        declared |= declaration["state"] == AllergenDeclaration.DECLARED
    for food in sorted(foods, key=lambda food: (food.name.casefold(), food.name, food.pk)):
        rows.append({
            "id": food.pk, "name": food.name,
            "declarations": sorted(by_food.get(food.pk, []), key=lambda row: (row["name"], row["id"])),
        })
    return {
        "scope": scope,
        "assessment": AllergenDeclaration.DECLARED if declared else AllergenDeclaration.UNKNOWN,
        "undeclared_means_absent": False,
        "unknown_ingredients": unknown_ingredients,
        "foods": rows,
    }


def food_allergens(*, user, space, food_id):
    food = get_object_or_404(visible_foods(user, space), pk=food_id)
    return _assessment({"type": "food", "id": food.pk, "name": food.name}, [food], space)


def recipe_allergens(*, user, space, recipe_id):
    roots, recipes, _ = native_recipe_graph([recipe_id], space, user)
    foods = {}
    unknown = False
    space_id = getattr(space, "pk", space)
    for recipe in recipes.values():
        for step in recipe.steps.all():
            if step.space_id != space_id:
                raise NotFound("La receta no está disponible.")
            for ingredient in step.ingredients.all():
                if ingredient.space_id != space_id:
                    raise NotFound("La receta no está disponible.")
                if ingredient.is_header:
                    continue
                if ingredient.food_id is None:
                    unknown = True
                else:
                    foods[ingredient.food_id] = ingredient.food
    if visible_foods(user, space).filter(pk__in=foods).count() != len(foods):
        raise NotFound("La receta no está disponible.")
    root = roots[0]
    return _assessment(
        {"type": "recipe", "id": root.pk, "name": root.name}, list(foods.values()), space,
        unknown_ingredients=unknown,
    )
