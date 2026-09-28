"""Cost a native Recipe from reference package prices. Does not write the recipe."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from cuaderno.domain.costing import CostResult, line_cost, scale_amount
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.models import PackageFormat, PriceVersion


def current_price(package: PackageFormat, as_of):
    return (
        PriceVersion.objects.filter(package=package, space=package.space, valid_from__lte=as_of)
        .order_by("-valid_from", "-id")
        .first()
    )


def reference_package(food):
    return (
        PackageFormat.objects.filter(food=food, space=food.space, is_reference=True)
        .select_related("unit")
        .first()
    )


def cost_recipe(recipe, servings, as_of=None) -> dict:
    as_of = as_of or timezone.now()
    base_servings = recipe.servings or 1
    if base_servings <= 0:
        raise DomainError("invalid_servings", "Las raciones base deben ser mayores que cero.")
    target = parse_decimal(servings, allow_zero=False)
    factor = scale_amount(1, base_servings, target)
    lines = []
    warnings = []
    for step in recipe.steps.all().prefetch_related("ingredients__food", "ingredients__unit"):
        for ingredient in step.ingredients.all():
            lines.append(_cost_ingredient(ingredient, factor, as_of, warnings))
    return _sheet(lines, warnings, base_servings, target)


def _cost_ingredient(ingredient, factor: Decimal, as_of, warnings: list) -> CostResult:
    if ingredient.is_header:
        return CostResult("complete", Decimal("0"), Decimal("0"), Decimal("0"), ("encabezado",))
    if ingredient.no_amount or ingredient.food_id is None:
        warnings.append("cantidad_excluida")
        return CostResult("complete", Decimal("0"), Decimal("0"), Decimal("0"), ("excluido",))
    if ingredient.amount is None:
        return CostResult("incomplete", None, None, None, ("cantidad_desconocida",))
    used = Decimal(ingredient.amount) * factor
    if used == 0:
        return CostResult("incomplete", None, None, None, ("cantidad_desconocida",))
    package = reference_package(ingredient.food)
    if package is None:
        return CostResult("incomplete", None, None, None, ("sin_formato",))
    price = current_price(package, as_of)
    if price is None:
        return CostResult("incomplete", None, None, None, ("precio_desconocido",))
    unit_name = ingredient.unit.name if ingredient.unit_id else None
    if unit_name is None:
        return CostResult("needs_conversion", None, None, None, ("sin_unidad",))
    return line_cost(
        price.amount,
        package.quantity,
        package.unit.name,
        used,
        unit_name,
        explicit_free=price.explicit_free,
    )


def _sheet(lines: list[CostResult], warnings: list, base_servings: int, target: Decimal) -> dict:
    blocking = [line for line in lines if line.status != "complete"]
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
    )
