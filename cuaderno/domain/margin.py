"""Yield is applied once. A target food-cost ratio is not a profit figure."""

from __future__ import annotations

from decimal import Decimal

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def split_yield(gross, yield_ratio) -> tuple[Decimal, Decimal]:
    gross = parse_decimal(gross, allow_zero=True)
    ratio = parse_decimal(yield_ratio, allow_zero=False)
    if ratio > 1:
        raise DomainError("invalid_yield", "El rendimiento no puede pasar de 1.")
    usable = gross * ratio
    return usable, gross - usable


def food_cost_gap(ingredient_cost, selling_price, target_ratio) -> dict:
    """Missing sale price stays incomplete. This never returns a net profit."""
    cost = parse_decimal(ingredient_cost, allow_zero=True)
    if selling_price is None or selling_price == "":
        return {"status": "incomplete", "ratio": None, "above_target": None, "net_profit": None}
    price = parse_decimal(selling_price, allow_zero=False)
    ratio = (cost / price).quantize(Decimal("0.0001"))
    target = parse_decimal(target_ratio, allow_zero=False) if target_ratio not in (None, "") else None
    return {
        "status": "complete",
        "ratio": format(ratio, "f"),
        "above_target": None if target is None else ratio > target,
        "net_profit": None,
    }
