"""Walk native Step.step_recipe and Food.recipe. Does not create a second recipe tree."""

from __future__ import annotations

from decimal import Decimal, localcontext

from django.db.models import Prefetch, Q

from cookbook.models import Ingredient, Recipe, Step, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.domain.production import assert_no_cycle
from cuaderno.domain.units import convert_quantity, to_base
from cuaderno.domain.ingredient_yields import compose_scale_ratio, ingredient_quantities, validate_scale_ratio
from cuaderno.models import RecipeYield


MAX_NATIVE_GRAPH_RECIPES = 1001


def _scale_native_quantity(quantity, numerator, denominator):
    # Match ingredient yield's working precision. Two persisted Decimal(32,16)
    # operands can require64 digits before division; recurring results remain
    # working-precision decimals, not a claim of infinite rational precision.
    with localcontext() as context:
        context.prec = 64
        return quantity * numerator / denominator


def convert_native_quantity(amount, from_unit, to_unit, food, space, *, conversions=None):
    if from_unit is None or to_unit is None:
        raise DomainError("yield_unit_missing", "La subreceta y su uso necesitan unidad.")
    space_id = getattr(space, "pk", space)
    if (from_unit.space_id != space_id or to_unit.space_id != space_id
            or food is None or food.space_id != space_id):
        raise DomainError("yield_conversion_missing", "No hay conversión disponible en este espacio.")
    if from_unit.pk == to_unit.pk:
        return Decimal(amount)
    try:
        with localcontext() as context:
            context.prec = 64
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
        conversions = UnitConversion.objects.filter(
            space_id=space_id, base_unit__space_id=space_id, converted_unit__space_id=space_id,
        ).filter(Q(food__isnull=True) | Q(food=food)).select_related("base_unit", "converted_unit").order_by("pk")
    graph = {}
    for row in conversions:
        if (row.space_id != space_id or row.base_unit.space_id != space_id
                or row.converted_unit.space_id != space_id or row.food_id not in (None, food.pk)):
            continue
        if (row.base_amount.is_finite() and row.converted_amount.is_finite()
                and row.base_amount > 0 and row.converted_amount > 0):
            specific = row.food_id is not None
            if not specific:
                try:
                    same_dimension = to_base(1, row.base_unit.base_unit or row.base_unit.name)[0] == to_base(1, row.converted_unit.base_unit or row.converted_unit.name)[0]
                except DomainError:
                    same_dimension = False
                if not same_dimension:
                    continue
            # Multiply before dividing: pre-rounding an inverse ratio such as
            # 1000/920 makes an exact 368g -> 400mL become 400.000...0001.
            graph.setdefault(row.base_unit_id, []).append((row.converted_unit_id, row.converted_amount, row.base_amount, specific))
            graph.setdefault(row.converted_unit_id, []).append((row.base_unit_id, row.base_amount, row.converted_amount, specific))
    queue = [(from_unit.pk, Decimal(amount), False)]
    visited = set()
    for unit_id, quantity, specific in queue:
        if unit_id == to_unit.pk and (not cross_dimension or specific):
            return quantity
        if (unit_id, specific) in visited:
            continue
        visited.add((unit_id, specific))
        queue.extend((target, _scale_native_quantity(quantity, numerator, denominator), specific or edge_specific)
                     for target, numerator, denominator, edge_specific in graph.get(unit_id, []) if (target, specific or edge_specific) not in visited)
    raise DomainError("yield_conversion_missing", f"No hay conversión de {from_unit.name} a {to_unit.name}.")


def native_recipe_graph(recipe_ids, space, user=None, *, strict_leaf_scope=True):
    from cuaderno.services.costing import visible_recipes

    allowed = visible_recipes(user, space) if user else Recipe.objects.filter(space=space)
    cache = {}
    edges: dict[str, list[str]] = {}

    def load(recipe_id, depth=0):
        if depth > 32 or len(cache) >= MAX_NATIVE_GRAPH_RECIPES:
            raise DomainError("recipe_graph_limit", "La ficha supera el límite de subrecetas.")
        if recipe_id in cache:
            return cache[recipe_id]
        recipe = allowed.filter(pk=recipe_id).prefetch_related(Prefetch(
            "steps", queryset=Step._base_manager.prefetch_related(Prefetch(
                "ingredients", queryset=Ingredient._base_manager.select_related("food", "unit"),
            )),
        )).first()
        if recipe is None:
            raise DomainError("recipe_missing", "Una receta no está disponible en este espacio.")
        cache[recipe_id] = recipe
        links = []
        for step in recipe.steps.all():
            space_id = getattr(space, "pk", space)
            if step.space_id != space_id:
                raise DomainError("recipe_missing", "Una receta no está disponible en este espacio.")
            if step.step_recipe_id:
                links.append(step.step_recipe_id)
            for ingredient in step.ingredients.all():
                foreign_leaf = (
                    ingredient.space_id != space_id
                    or (ingredient.food_id and ingredient.food.space_id != space_id)
                    or (ingredient.unit_id and ingredient.unit.space_id != space_id)
                )
                if strict_leaf_scope and foreign_leaf:
                    raise DomainError("recipe_missing", "Una receta no está disponible en este espacio.")
                # Costing degrades corrupt leaves to unknown, never follows a
                # foreign Food's graph. Production must reject every FK.
                if (ingredient.space_id == space_id and ingredient.food_id
                        and ingredient.food.space_id == space_id and ingredient.food.recipe_id):
                    links.append(ingredient.food.recipe_id)
        edges[str(recipe.pk)] = [str(value) for value in links]
        for link in links:
            load(link, depth + 1)
        return recipe

    roots = [load(int(value)) for value in recipe_ids]
    for recipe in roots:
        assert_no_cycle(str(recipe.pk), edges)
    return roots, cache, edges


def sheet_from_recipes(recipe_ids, space, user=None, factors=None, *, factor_ratios=None) -> dict:
    if factors is not None and factor_ratios is not None:
        raise DomainError("invalid_scale", "Indica factores o ratios de producción, no ambos.")
    roots, cache, edges = native_recipe_graph(recipe_ids, space, user)
    yields = {row.recipe_id: row for row in RecipeYield.objects.filter(space=space, recipe_id__in=cache).select_related("unit")}
    totals, warnings, yield_details = {}, [], []
    units = {}

    def walk(recipe, factor_ratio):
        for step in recipe.steps.all():
            if step.step_recipe_id:
                walk(cache[step.step_recipe_id], factor_ratio)
            for ingredient in step.ingredients.all():
                space_id = getattr(space, "pk", space)
                if (ingredient.space_id != space_id
                        or (ingredient.food_id and ingredient.food.space_id != space_id)
                        or (ingredient.unit_id and ingredient.unit.space_id != space_id)):
                    raise DomainError("ingredient_scope", "Un ingrediente no está disponible en este espacio.")
                if ingredient.is_header or ingredient.no_amount:
                    continue
                if not ingredient.food_id or ingredient.amount <= 0:
                    warnings.append({"code": "ingredient_incomplete", "ingredient": ingredient.pk})
                    continue
                amount, yield_detail = ingredient_quantities(ingredient, factor_ratio=factor_ratio)
                if ingredient.yield_ratio is not None or ingredient.quantity_basis != "gross":
                    yield_detail.update({
                        "food_id": ingredient.food_id,
                        "food_name": ingredient.food.name if ingredient.food_id else None,
                        "unit_id": ingredient.unit_id,
                        "unit_name": ingredient.unit.name if ingredient.unit_id else None,
                    })
                    yield_details.append(yield_detail)
                child_id = ingredient.food.recipe_id
                if child_id:
                    declared = yields.get(child_id)
                    if declared is None:
                        warnings.append({"code": "yield_missing", "recipe": child_id, "food": ingredient.food.name})
                    else:
                        if declared.quantity <= 0:
                            raise DomainError("invalid_yield", "El rendimiento de la subreceta debe ser positivo.")
                        # Convert the native amount, not its pre-divided scale.
                        # The child ingredient can cancel the output denominator.
                        needed = convert_native_quantity(
                            ingredient.amount, ingredient.unit, declared.unit, ingredient.food, space,
                        )
                        walk(cache[child_id], compose_scale_ratio(factor_ratio, needed, declared.quantity))
                        continue
                key = ingredient.food.name
                if key in units and units[key] != ingredient.unit:
                    amount = convert_native_quantity(amount, ingredient.unit, units[key], ingredient.food, space)
                else:
                    units[key] = ingredient.unit
                with localcontext() as context:
                    context.prec = 64
                    totals[key] = totals.get(key, Decimal("0")) + amount

    for recipe in roots:
        factor_ratio = (
            (factor_ratios or {}).get(recipe.pk, (1, 1)) if factor_ratios is not None
            else ((factors or {}).get(recipe.pk, "1"), 1)
        )
        walk(recipe, validate_scale_ratio(factor_ratio))
    return {"needs": {key: format(value, "f") for key, value in totals.items()}, "edges": edges,
            "warnings": warnings, "units": {key: unit.name if unit else None for key, unit in units.items()},
            "ingredient_yields": yield_details}
