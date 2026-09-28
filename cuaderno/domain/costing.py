"""Deterministic recipe costing. Unknown prices stay unknown."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import money_display, parse_decimal
from cuaderno.domain.units import convert_quantity


@dataclass(frozen=True)
class CostResult:
    status: str
    unrounded: Decimal | None
    display: Decimal | None
    known_subtotal: Decimal | None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "unrounded": None if self.unrounded is None else format(self.unrounded, "f"),
            "display": None if self.display is None else format(self.display, "f"),
            "known_subtotal": None if self.known_subtotal is None else format(self.known_subtotal, "f"),
            "total": None if self.status != "complete" else format(self.unrounded, "f"),
            "warnings": list(self.warnings),
        }


def scale_amount(base_amount, base_servings, requested_servings) -> Decimal:
    base = parse_decimal(base_amount, allow_zero=True)
    origin = parse_decimal(base_servings, allow_zero=False)
    target = parse_decimal(requested_servings, allow_zero=False)
    return base * target / origin


def portion_of_batch(batch_cost, batch_yield, used) -> CostResult:
    cost = parse_decimal(batch_cost, allow_zero=True)
    yield_amount = parse_decimal(batch_yield, allow_zero=False)
    used_amount = parse_decimal(used, allow_zero=True)
    unrounded = cost * used_amount / yield_amount
    return _complete(unrounded)


def line_cost(
    package_price,
    package_quantity,
    package_unit,
    used_quantity,
    used_unit,
    *,
    yield_ratio=None,
    quantity_basis="gross",
    density=None,
    explicit_free: bool = False,
) -> CostResult:
    if package_price is None:
        return CostResult("incomplete", None, None, None, ("precio_desconocido",))
    try:
        price = parse_decimal(package_price, allow_zero=explicit_free)
    except DomainError as exc:
        if package_price in ("", None):
            return CostResult("incomplete", None, None, None, ("precio_desconocido",))
        return CostResult("invalid", None, None, None, (exc.code,))
    if price == 0 and not explicit_free:
        return CostResult("invalid", None, None, None, ("cero_no_explicito",))
    try:
        package_base = parse_decimal(package_quantity, allow_zero=False)
        used = parse_decimal(used_quantity, allow_zero=True)
        if yield_ratio is not None:
            ratio = parse_decimal(yield_ratio, allow_zero=False)
            if ratio > 1:
                raise DomainError("invalid_yield", "La merma debe estar en (0, 1].")
            if quantity_basis == "net_usable":
                used = used / ratio
        used_in_package_unit = convert_quantity(used, used_unit, package_unit, density_g_per_ml=density)
    except DomainError as exc:
        status = "needs_conversion" if exc.code == "needs_conversion" else "invalid"
        return CostResult(status, None, None, None, (exc.code,))
    unrounded = price / package_base * used_in_package_unit
    return _complete(unrounded)


def sum_lines(line_costs: list) -> CostResult:
    """Sum exact line costs and round only the displayed total."""
    total = Decimal("0")
    for item in line_costs:
        total += parse_decimal(item, allow_zero=True)
    return _complete(total)


def _complete(unrounded: Decimal) -> CostResult:
    return CostResult(
        "complete",
        unrounded,
        money_display(unrounded),
        unrounded,
    )
