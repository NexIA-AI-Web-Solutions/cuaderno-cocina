"""Frozen replacement-cost estimates for stock waste.

This is an operational estimate from the current reference package, not FIFO,
weighted-average inventory accounting, or profit.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from cookbook.models import Food, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal, parse_decimal, validate_explicit_price
from cuaderno.models import SpaceProfile
from cuaderno.services.costing import current_price, reference_package
from cuaderno.services.subrecipes import convert_native_quantity


def _profile_snapshot(space_id) -> tuple[str, str | None]:
    profile = SpaceProfile.objects.filter(space_id=space_id).only("currency", "price_policy").first()
    if profile is None:
        return "EUR", None
    policy = profile.price_policy if profile.price_policy in {SpaceProfile.NET, SpaceProfile.GROSS} else None
    return profile.currency, policy


def _input_snapshot(entry, quantity: Decimal, *, include_unit_name: bool) -> dict:
    return {
        "quantity": canonical_decimal(quantity),
        "unit_id": entry.unit_id,
        "unit_name": entry.unit.name if include_unit_name and entry.unit_id else None,
    }


def _package_snapshot(package) -> dict | None:
    if package is None:
        return None
    return {
        "id": package.pk,
        "label": package.label,
        "quantity": canonical_decimal(package.quantity),
        "unit_id": package.unit_id,
        "unit_name": package.unit.name if package.unit_id else None,
    }


def _price_snapshot(price) -> dict | None:
    if price is None:
        return None
    return {
        "id": price.pk,
        "amount": canonical_decimal(price.amount),
        "explicit_free": price.explicit_free,
        "valid_from": price.valid_from.isoformat(),
    }


def replacement_valuation(*, entry, quantity, as_of) -> dict:
    """Return a JSON-safe replacement estimate frozen at ``as_of``.

    Missing package, price, or a proven unit conversion is represented as an
    unknown estimate. It never turns into a zero-valued loss implicitly.
    """

    parsed_quantity = parse_decimal(quantity, allow_zero=False)
    currency, price_policy = _profile_snapshot(entry.space_id)
    snapshot = {
        "policy": "replacement_estimate",
        "status": "unknown",
        "amount": None,
        "currency": currency,
        "price_policy": price_policy,
        "as_of": as_of.isoformat(),
        "reason": None,
        # IDs are already present on the legacy row; related labels are not
        # dereferenced until their Space ownership has been proven below.
        "input": _input_snapshot(entry, parsed_quantity, include_unit_name=False),
        "package": None,
        "price_version": None,
        "calculation": None,
    }
    if entry.food_id is None:
        snapshot["reason"] = "food_missing"
        return snapshot
    if entry.unit_id is None:
        snapshot["reason"] = "unit_missing"
        return snapshot
    if not Food.objects.filter(pk=entry.food_id, space_id=entry.space_id).exists():
        snapshot["reason"] = "scope_mismatch"
        return snapshot
    if not Unit.objects.filter(pk=entry.unit_id, space_id=entry.space_id).exists():
        snapshot["reason"] = "scope_mismatch"
        return snapshot
    snapshot["input"] = _input_snapshot(entry, parsed_quantity, include_unit_name=True)

    package = reference_package(entry.food)
    if package is None:
        snapshot["reason"] = "reference_package_missing"
        return snapshot
    if (
        package.space_id != entry.space_id
        or package.food_id != entry.food_id
        or package.unit_id is None
        or not Unit.objects.filter(pk=package.unit_id, space_id=entry.space_id).exists()
    ):
        snapshot["reason"] = "scope_mismatch"
        return snapshot
    snapshot["package"] = _package_snapshot(package)
    if Decimal(package.quantity) <= 0:
        snapshot["reason"] = "reference_package_invalid"
        return snapshot

    price = current_price(package, as_of)
    if price is None:
        snapshot["reason"] = "price_missing"
        return snapshot
    if price.space_id != entry.space_id or price.package_id != package.pk:
        snapshot["reason"] = "scope_mismatch"
        return snapshot
    snapshot["price_version"] = _price_snapshot(price)
    try:
        validate_explicit_price(Decimal(price.amount), price.explicit_free)
    except DomainError:
        snapshot["reason"] = "price_invalid"
        return snapshot

    try:
        with localcontext() as context:
            context.prec = 64
            context.rounding = ROUND_HALF_EVEN
            converted = convert_native_quantity(
                parsed_quantity,
                entry.unit,
                package.unit,
                entry.food,
                entry.space,
            )
            package_fraction = converted / Decimal(package.quantity)
            amount = package_fraction * Decimal(price.amount)
    except DomainError:
        snapshot["reason"] = "conversion_missing"
        return snapshot

    snapshot.update({
        "status": "complete",
        "amount": canonical_decimal(amount),
        "reason": None,
        "calculation": {
            "quantity_in_package_unit": canonical_decimal(converted),
            "package_fraction": canonical_decimal(package_fraction),
            "computed_amount": canonical_decimal(amount),
            "working_precision": 64,
            "rounding": "HALF_EVEN",
        },
    })
    return snapshot
