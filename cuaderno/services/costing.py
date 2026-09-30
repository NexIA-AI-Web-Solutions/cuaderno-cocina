"""Cost a native Recipe from reference package prices. Does not write the recipe."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext

from django.db.models import Q
from django.utils import timezone

from cookbook.models import UnitConversion
from cuaderno.domain.costing import CostResult, line_cost, scale_amount
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.domain.ingredient_yields import ingredient_quantities
from cuaderno.models import PackageFormat, PriceVersion, RecipeYield


def current_price(package: PackageFormat, as_of):
    return (
        PriceVersion.objects.filter(package=package, space_id=package.space_id, valid_from__lte=as_of)
        .order_by("-valid_from", "-id")
        .first()
    )


def reference_package(food):
    return (
        PackageFormat.objects.filter(food=food, space_id=food.space_id, is_reference=True)
        .select_related("unit")
        .first()
    )


@dataclass(frozen=True)
class _CostingContext:
    space_id: int
    recipes: dict
    yields: dict
    packages: dict
    prices: dict
    global_conversions: tuple
    food_conversions: dict


def _load_costing_context(recipe_cache, space_id, as_of) -> _CostingContext:
    food_ids = {
        ingredient.food_id
        for recipe in recipe_cache.values()
        for step in recipe.steps.all()
        for ingredient in step.ingredients.all()
        if ingredient.food_id is not None
    }
    yields = {
        row.recipe_id: row
        for row in RecipeYield.objects.filter(space_id=space_id, recipe_id__in=recipe_cache).select_related("unit")
    }
    packages = {
        row.food_id: row
        for row in PackageFormat.objects.filter(
            space_id=space_id,
            food__space_id=space_id,
            unit__space_id=space_id,
            food_id__in=food_ids,
            is_reference=True,
        ).select_related("unit")
    }
    prices = {
        row.package_id: row
        for row in PriceVersion.objects.filter(
            space_id=space_id,
            package_id__in=[package.pk for package in packages.values()],
            valid_from__lte=as_of,
        )
        .order_by("package_id", "-valid_from", "-id")
        .distinct("package_id")
    }
    conversion_rows = tuple(
        UnitConversion.objects.filter(space_id=space_id, base_unit__space_id=space_id, converted_unit__space_id=space_id)
        .filter(Q(food_id__isnull=True) | Q(food_id__in=food_ids))
        .select_related("base_unit", "converted_unit")
        .order_by("pk")
    )
    food_conversions = defaultdict(list)
    global_conversions = []
    for row in conversion_rows:
        if row.food_id is None:
            global_conversions.append(row)
        else:
            food_conversions[row.food_id].append(row)
    return _CostingContext(
        space_id=space_id,
        recipes=recipe_cache,
        yields=yields,
        packages=packages,
        prices=prices,
        global_conversions=tuple(global_conversions),
        food_conversions={food_id: tuple(rows) for food_id, rows in food_conversions.items()},
    )


def cost_recipe(recipe, servings, as_of=None, user=None) -> dict:
    from cuaderno.services.subrecipes import native_recipe_graph

    roots, recipe_cache, _ = native_recipe_graph([recipe.pk], recipe.space_id, user or recipe.created_by)
    as_of = as_of or timezone.now()
    base_servings = recipe.servings or 1
    if base_servings <= 0:
        raise DomainError("invalid_servings", "Las raciones base deben ser mayores que cero.")
    target = parse_decimal(servings, allow_zero=False)
    factor = scale_amount(1, base_servings, target)
    warnings = []
    context = _load_costing_context(recipe_cache, recipe.space_id, as_of)
    lines = _cost_recipe_lines(roots[0], factor, as_of, warnings, (), context)
    return _sheet(lines, warnings, base_servings, target)


def _cost_recipe_lines(recipe, factor, as_of, warnings, path, context):
    if recipe.pk in path:
        route = " → ".join(str(value) for value in (*path, recipe.pk))
        raise DomainError("recipe_cycle", f"Referencia circular: {route}")
    if len(path) >= 32:
        raise DomainError("recipe_graph_limit", "La receta supera 32 niveles de subelaboraciones.")
    lines = []
    for step in recipe.steps.all():
        if step.step_recipe_id:
            child = context.recipes.get(step.step_recipe_id)
            if child is None:
                raise DomainError("recipe_missing", "Una subreceta no está disponible en este espacio.")
            else:
                lines.extend(_cost_recipe_lines(child, factor, as_of, warnings, (*path, recipe.pk), context))
        for ingredient in step.ingredients.all():
            if not ingredient.is_header and not ingredient.no_amount:
                # Validate before descending into a Food.recipe as well: its
                # declared output must not acquire a second yield adjustment.
                ingredient_quantities(ingredient, factor)
            if ingredient.food_id and ingredient.food.recipe_id and not ingredient.is_header and not ingredient.no_amount:
                child = context.recipes.get(ingredient.food.recipe_id)
                if child is None:
                    raise DomainError("recipe_missing", "Una subreceta no está disponible en este espacio.")
                if child.pk in (*path, recipe.pk):
                    raise DomainError("recipe_cycle", "Referencia circular en las subelaboraciones.")
                declared = context.yields.get(child.pk)
                if declared is None:
                    lines.append(CostResult("incomplete", None, None, None, ("rendimiento_desconocido",)))
                    continue
                if declared.quantity <= 0 or ingredient.amount <= 0:
                    lines.append(CostResult("invalid", None, None, None, ("rendimiento_invalido",)))
                    continue
                try:
                    amount = _convert_native_quantity(
                        ingredient.amount,
                        ingredient.unit,
                        declared.unit,
                        ingredient.food,
                        context,
                    )
                except DomainError as exc:
                    lines.append(CostResult("needs_conversion", None, None, None, (exc.code,)))
                    continue
                lines.extend(
                    _cost_recipe_lines(
                        child,
                        scale_amount(amount, declared.quantity, factor),
                        as_of,
                        warnings,
                        (*path, recipe.pk),
                        context,
                    )
                )
            else:
                lines.append(_cost_ingredient(ingredient, factor, as_of, warnings, context))
    return lines


def _convert_native_quantity(amount, from_unit, to_unit, food, context):
    """Reuse the native conversion algorithm and its total PK edge ordering."""
    from cuaderno.services.subrecipes import convert_native_quantity

    rows = context.global_conversions + context.food_conversions.get(food.pk, ())
    return convert_native_quantity(
        amount, from_unit, to_unit, food, food.space_id,
        conversions=sorted(rows, key=lambda row: row.pk),
    )


def _cost_ingredient(ingredient, factor: Decimal, as_of, warnings: list, context) -> CostResult:
    if ingredient.is_header:
        return CostResult("complete", Decimal("0"), Decimal("0"), Decimal("0"), ("encabezado",))
    if ingredient.no_amount:
        warnings.append("cantidad_excluida")
        return CostResult("complete", Decimal("0"), Decimal("0"), Decimal("0"), ("excluido",))
    if ingredient.food_id is None:
        return CostResult("incomplete", None, None, None, ("alimento_desconocido",))
    if ingredient.space_id != context.space_id or ingredient.food.space_id != context.space_id:
        return CostResult("incomplete", None, None, None, ("alimento_desconocido",))
    if ingredient.unit_id and ingredient.unit.space_id != context.space_id:
        return CostResult("needs_conversion", None, None, None, ("sin_unidad",))
    if ingredient.amount is None:
        return CostResult("incomplete", None, None, None, ("cantidad_desconocida",))
    used, _trace = ingredient_quantities(ingredient, factor)
    if used == 0:
        return CostResult("incomplete", None, None, None, ("cantidad_desconocida",))
    package = context.packages.get(ingredient.food_id)
    if package is None:
        return CostResult("incomplete", None, None, None, ("sin_formato",))
    price = context.prices.get(package.pk)
    if price is None:
        return CostResult("incomplete", None, None, None, ("precio_desconocido",))
    unit_name = ingredient.unit.name if ingredient.unit_id else None
    if unit_name is None:
        return CostResult("needs_conversion", None, None, None, ("sin_unidad",))
    result = line_cost(
        price.amount,
        package.quantity,
        package.unit.name,
        used,
        unit_name,
        explicit_free=price.explicit_free,
    )
    if result.status != "needs_conversion" and result.warnings != ("unknown_unit",):
        return result
    try:
        converted = _convert_native_quantity(used, ingredient.unit, package.unit, ingredient.food, context)
    except DomainError as exc:
        return CostResult("needs_conversion", None, None, None, (exc.code,))
    # Both quantities are now expressed in the actual package unit. The
    # dimensionless ratio reuses price/quantity validation without inventing
    # a universal density or reapplying ingredient yield.
    return line_cost(
        price.amount, package.quantity, "unit", converted, "unit",
        explicit_free=price.explicit_free,
    )


def _sheet(lines: list[CostResult], warnings: list, base_servings: int, target: Decimal) -> dict:
    blocking = [line for line in lines if line.status != "complete"]
    with localcontext() as context:
        context.prec = 64
        known = sum((line.unrounded for line in lines if line.unrounded is not None and line.status == "complete"), Decimal("0"))
    extra = tuple(warnings)
    if blocking:
        status = "needs_conversion" if any(line.status == "needs_conversion" for line in blocking) else "incomplete"
        if any(line.status == "invalid" for line in blocking):
            status = "invalid"
        result = CostResult(status, None, None, known, extra + tuple(w for line in blocking for w in line.warnings))
    else:
        from cuaderno.domain.costing import _complete

        result = _complete(known)
        if extra:
            result = CostResult(result.status, result.unrounded, result.display, result.known_subtotal, extra)
    per_serving = None
    if result.status == "complete" and result.unrounded is not None:
        with localcontext() as context:
            context.prec = 64
            per_serving = format(result.unrounded / target, "f")
    payload = result.as_dict()
    payload["base_servings"] = str(base_servings)
    payload["servings"] = format(target, "f")
    payload["per_serving"] = per_serving
    payload["lines"] = [line.as_dict() for line in lines]
    return payload


def visible_recipes(user, space):
    from cookbook.models import Recipe

    return Recipe.objects.filter(space=space).filter(
        Q(private=False) | Q(private=True, created_by=user) | Q(private=True, shared=user)
    ).distinct()
