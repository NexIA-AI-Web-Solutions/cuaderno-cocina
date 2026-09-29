"""One gross/useful adjustment on each native ingredient, not on its Food."""
from decimal import Decimal, localcontext
import re

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def parse_yield_ratio(value):
    if not isinstance(value, str):
        raise DomainError("invalid_yield", "El rendimiento debe ser un decimal textual exacto.")
    text = value.strip().replace(",", ".")
    if not re.fullmatch(r"(?:0\.\d{1,16}|1(?:\.0{1,16})?)", text):
        raise DomainError("invalid_yield", "Indica un rendimiento entre 0 y 1, con hasta 16 decimales y sin exponentes.")
    ratio = Decimal(text)
    validate_yield_policy("net_usable", ratio)
    return ratio


def validate_yield_policy(quantity_basis, yield_ratio, *, is_subrecipe=False):
    if quantity_basis not in {"gross", "net_usable"}:
        raise DomainError("invalid_yield", "Elige cantidad bruta o neta útil.")
    ratio = None if yield_ratio is None else parse_decimal(yield_ratio, allow_zero=False)
    if ratio is not None and ratio > 1:
        raise DomainError("invalid_yield", "El rendimiento útil debe estar entre 0 y 1, excluido cero.")
    if quantity_basis == "net_usable" and ratio is None:
        raise DomainError("invalid_yield", "La cantidad neta útil necesita un rendimiento declarado.")
    if is_subrecipe and (quantity_basis != "gross" or ratio is not None):
        raise DomainError("double_yield", "La subelaboración ya tiene rendimiento propio; no apliques otra merma en su uso.")
    return ratio


def ingredient_quantities(ingredient, factor=Decimal("1")):
    ratio = validate_yield_policy(
        ingredient.quantity_basis, ingredient.yield_ratio,
        is_subrecipe=bool(ingredient.food_id and ingredient.food.recipe_id),
    )
    with localcontext() as context:
        context.prec = 64
        amount = Decimal(ingredient.amount) * Decimal(factor)
        purchased = amount / ratio if ingredient.quantity_basis == "net_usable" else amount
        useful = amount if ingredient.quantity_basis == "net_usable" else None if ratio is None else amount * ratio
        waste = None if useful is None else purchased - useful
    trace = {
        "ingredient_id": ingredient.pk, "quantity_basis": ingredient.quantity_basis,
        "yield_ratio": None if ratio is None else format(ratio, "f"),
        "useful_quantity": None if useful is None else format(useful, "f"),
        "purchased_quantity": format(purchased, "f"),
        "waste_quantity": None if waste is None else format(waste, "f"),
    }
    return purchased, trace
