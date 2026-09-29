"""Decimal money. Floats and unknown prices are rejected, never coerced to zero."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from cuaderno.domain.errors import DomainError

CENTS = Decimal("0.01")
_GROUPING = re.compile(r"^\d{1,3}(\.\d{3}){2,}$|^[1-9]\d{0,2}\.000$")


def parse_decimal(value, *, allow_zero: bool = True, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise DomainError("invalid_decimal", "El importe debe ser un decimal exacto, no un float.")
    if isinstance(value, Decimal):
        number = value
    else:
        if value is None:
            raise DomainError("invalid_decimal", "Falta el importe.")
        text = str(value).strip()
        if text == "" or text.lower() in {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
            raise DomainError("invalid_decimal", "Importe no numérico.")
        if "," in text and "." in text:
            raise DomainError("invalid_decimal", "Separadores de miles y decimales mezclados.")
        if _GROUPING.match(text):
            raise DomainError("invalid_decimal", "El agrupado de miles es ambiguo; escribe el decimal con punto o coma.")
        if text.count(",") > 1:
            raise DomainError("invalid_decimal", "Coma decimal ambigua.")
        if "," in text:
            text = text.replace(",", ".")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise DomainError("invalid_decimal", "Importe no numérico.") from exc
    if not number.is_finite():
        raise DomainError("invalid_decimal", "Importe no finito.")
    if number < 0 and not allow_negative:
        raise DomainError("invalid_decimal", "El importe no puede ser negativo.")
    if number == 0 and not allow_zero:
        raise DomainError("invalid_decimal", "El cero exige una indicación explícita de gratuito.")
    return number


def money_display(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def canonical_decimal(value) -> str:
    """Stable exact string without context-sensitive normalize/rounding."""
    text = format(Decimal(str(value)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
