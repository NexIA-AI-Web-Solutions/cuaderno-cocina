"""Walk native Step.step_recipe and Food.recipe. Does not create a second recipe tree."""

from __future__ import annotations

from decimal import Decimal

from cookbook.models import Recipe, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.domain.production import assert_no_cycle
from cuaderno.domain.units import convert_quantity, to_base
from cuaderno.domain.ingredient_yields import ingredient_quantities
from cuaderno.models import RecipeYield


MAX_NATIVE_GRAPH_RECIPES = 1001


def convert_native_quantity(amount, from_unit, to_unit, food, space, *, conversions=None):
    if from_unit is None or to_unit is None:
        raise DomainError("yield_unit_missing", "La subreceta y su uso necesitan unidad.")
    if from_unit.pk == to_unit.pk:
        return Decimal(amount)
    try:
        return convert_quantity(amount, from_unit.base_unit or from_unit.name, to_unit.base_unit or to_unit.name)
    except DomainError:
        pass
    try:
        cross_dimension = to_base(1, from_unit.base_unit or from_unit.name)[0] != to_base(1, to_unit.base_unit or to_unit.name)[0]
    except DomainError:
        # Unknown formats have no proven dimension/content: require a food-specific conversion.
        cross_dimension = True
    # Preserve native food-specific conversions, with Decimal arithmetic.
    if conversions is None:
        conversions = UnitConversion.objects.filter(space=space).filter(food__isnull=True) | UnitConversion.objects.filter(space=space, food=food)
    graph = {}
    for row in conversions:
        if row.base_amount > 0 and row.converted_amount > 0:
            specific = row.food_id is not None
            if not specific:
                try:
                    same_dimension = to_base(1, row.base_unit.base_unit or row.base_unit.name)[0] == to_base(1, row.converted_unit.base_unit or row.converted_unit.name)[0]
                except DomainError:
                    same_dimension = False
                if not same_dimension:
                    continue
            graph.setdefault(row.base_unit_id, []).append((row.converted_unit_id, row.converted_amount / row.base_amount, specific))
            graph.setdefault(row.converted_unit_id, []).append((row.base_unit_id, row.base_amount / row.converted_amount, specific))
    queue = [(from_unit.pk, Decimal(amount), False)]
    visited = set()
    for unit_id, quantity, specific in queue:
        if unit_id == to_unit.pk and (not cross_dimension or specific):
            return quantity
        if (unit_id, specific) in visited:
            continue
        visited.add((unit_id, specific))
        queue.extend((target, quantity * ratio, specific or edge_specific)
                     for target, ratio, edge_specific in graph.get(unit_id, []) if (target, specific or edge_specific) not in visited)
    raise DomainError("yield_conversion_missing", f"No hay conversión de {from_unit.name} a {to_unit.name}.")


def native_recipe_graph(recipe_ids, space, user=None):
    from cuaderno.services.costing import visible_recipes

    allowed = visible_recipes(user, space) if user else Recipe.objects.filter(space=space)
    cache = {}
    edges: dict[str, list[str]] = {}

    def load(recipe_id, depth=0):
        if depth > 32 or len(cache) >= MAX_NATIVE_GRAPH_RECIPES:
            raise DomainError("recipe_graph_limit", "La ficha supera el límite de subrecetas.")
        if recipe_id in cache:
            return cache[recipe_id]
        recipe = allowed.filter(pk=recipe_id).prefetch_related("steps__ingredients__food", "steps__ingredients__unit").first()
        if recipe is None:
            raise DomainError("recipe_missing", "Una receta no está disponible en este espacio.")
        cache[recipe_id] = recipe
        links = []
        for step in recipe.steps.all():
            if step.step_recipe_id:
                links.append(step.step_recipe_id)
            for ingredient in step.ingredients.all():
                if ingredient.food_id and ingredient.food.recipe_id:
                    links.append(ingredient.food.recipe_id)
        edges[str(recipe.pk)] = [str(value) for value in links]
        for link in links:
            load(link, depth + 1)
        return recipe

    roots = [load(int(value)) for value in recipe_ids]
    for recipe in roots:
        assert_no_cycle(str(recipe.pk), edges)
    return roots, cache, edges


def sheet_from_recipes(recipe_ids, space, user=None, factors=None) -> dict:
    roots, cache, edges = native_recipe_graph(recipe_ids, space, user)
    yields = {row.recipe_id: row for row in RecipeYield.objects.filter(space=space, recipe_id__in=cache).select_related("unit")}
    totals, warnings, yield_details = {}, [], []
    units = {}

    def walk(recipe, factor):
        for step in recipe.steps.all():
            if step.step_recipe_id:
                walk(cache[step.step_recipe_id], factor)
            for ingredient in step.ingredients.all():
                if ingredient.is_header or ingredient.no_amount:
                    continue
                if not ingredient.food_id or ingredient.amount <= 0:
                    warnings.append({"code": "ingredient_incomplete", "ingredient": ingredient.pk})
                    continue
                amount, yield_detail = ingredient_quantities(ingredient, factor)
                if ingredient.yield_ratio is not None or ingredient.quantity_basis != "gross":
                    yield_details.append(yield_detail)
                child_id = ingredient.food.recipe_id
                if child_id:
                    declared = yields.get(child_id)
                    if declared is None:
                        warnings.append({"code": "yield_missing", "recipe": child_id, "food": ingredient.food.name})
                    else:
                        if declared.quantity <= 0:
                            raise DomainError("invalid_yield", "El rendimiento de la subreceta debe ser positivo.")
                        needed = convert_native_quantity(amount, ingredient.unit, declared.unit, ingredient.food, space)
                        walk(cache[child_id], needed / declared.quantity)
                        continue
                key = ingredient.food.name
                if key in units and units[key] != ingredient.unit:
                    amount = convert_native_quantity(amount, ingredient.unit, units[key], ingredient.food, space)
                else:
                    units[key] = ingredient.unit
                totals[key] = totals.get(key, Decimal("0")) + amount

    for recipe in roots:
        factor = Decimal(str((factors or {}).get(recipe.pk, "1")))
        if not factor.is_finite() or factor <= 0:
            raise DomainError("invalid_scale", "El factor de producción debe ser positivo.")
        walk(recipe, factor)
    return {"needs": {key: format(value, "f") for key, value in totals.items()}, "edges": edges,
            "warnings": warnings, "units": {key: unit.name if unit else None for key, unit in units.items()},
            "ingredient_yields": yield_details}
