"""Stock decisions. The balance lives in one quantity; orders and plans do not change it."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def receive(balance, quantity, movements: list[dict], *, key: str, fingerprint: str) -> tuple[Decimal, list[dict]]:
    balance = parse_decimal(balance, allow_zero=True)
    quantity = parse_decimal(quantity, allow_zero=True)
    prior = [item for item in movements if item["key"] == key]
    if prior:
        if prior[0]["fingerprint"] != fingerprint:
            raise DomainError("idempotency_conflict", "La misma clave llega con otra cantidad.")
        return balance, movements
    movements = list(movements)
    movements.append({"key": key, "fingerprint": fingerprint, "quantity": quantity, "kind": "receipt"})
    return balance + quantity, movements


def consume(balance, quantity, *, allow_negative: bool = False) -> Decimal:
    balance = parse_decimal(balance, allow_zero=True)
    quantity = parse_decimal(quantity, allow_zero=False)
    updated = balance - quantity
    if updated < 0 and not allow_negative:
        raise DomainError("insufficient_stock", "El consumo dejaría el saldo en negativo.")
    return updated


def packs_to_buy(required, usable_stock, pack_size) -> tuple[Decimal, Decimal]:
    required = parse_decimal(required, allow_zero=True)
    usable = parse_decimal(usable_stock, allow_zero=True)
    pack = parse_decimal(pack_size, allow_zero=False)
    missing = required - usable
    if missing <= 0:
        return Decimal("0"), Decimal("0")
    packs = (missing / pack).to_integral_value(rounding=ROUND_CEILING)
    return packs, packs * pack


def waste_value(quantity, unit_valuation) -> Decimal:
    return parse_decimal(quantity, allow_zero=True) * parse_decimal(unit_valuation, allow_zero=True)
