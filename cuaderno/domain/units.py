"""Mass, volume and count. Package formats are not universal dimensions."""

from __future__ import annotations

from decimal import Decimal

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal

# factor to the base of the dimension: g, mL, unit
_CANONICAL = {
    "g": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "unit": ("count", Decimal("1")),
}

_ALIASES = {
    "g": "g",
    "gr": "g",
    "gramo": "g",
    "gramos": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "ml": "ml",
    "mililitro": "ml",
    "mililitros": "ml",
    "l": "l",
    "lt": "l",
    "litro": "l",
    "litros": "l",
    "unit": "unit",
    "u": "unit",
    "ud": "unit",
    "unidad": "unit",
    "unidades": "unit",
}


def canonical_unit(name: str) -> str:
    if name is None:
        raise DomainError("unknown_unit", "Falta la unidad.")
    key = str(name).strip().lower().replace("µ", "u")
    if key not in _ALIASES:
        raise DomainError("unknown_unit", f"Unidad no reconocida: {name}")
    return _ALIASES[key]


def to_base(quantity, unit_name: str) -> tuple[str, Decimal]:
    amount = parse_decimal(quantity, allow_zero=True)
    unit = canonical_unit(unit_name)
    dimension, factor = _CANONICAL[unit]
    return dimension, amount * factor


def convert_quantity(quantity, from_unit: str, to_unit: str, *, density_g_per_ml=None) -> Decimal:
    from_dim, from_base = to_base(quantity, from_unit)
    to_dim, to_one = to_base(1, to_unit)
    if from_dim == to_dim:
        return from_base / to_one
    if density_g_per_ml is None:
        raise DomainError("needs_conversion", "Falta densidad o peso unitario para convertir esas unidades.")
    density = parse_decimal(density_g_per_ml, allow_zero=False)
    if from_dim == "mass" and to_dim == "volume":
        ml = from_base / density
        return ml / to_one
    if from_dim == "volume" and to_dim == "mass":
        grams = from_base * density
        return grams / to_one
    raise DomainError("needs_conversion", "Esas dimensiones no se convierten.")
