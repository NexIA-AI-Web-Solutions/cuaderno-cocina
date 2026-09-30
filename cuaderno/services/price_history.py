"""Read-only dated price history and recipe-local impact calculations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext

from cuaderno.domain.errors import DomainError
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
from cuaderno.services.costing import _cost_recipe_lines, _load_costing_context, _sheet
from cuaderno.services.subrecipes import native_recipe_graph


def _profile_values(space_id: int) -> tuple[str, str]:
    """Read commercial metadata without creating rows from a GET request."""
    profile = SpaceProfile.objects.filter(space_id=space_id).only("currency", "price_policy").first()
    if profile is None:
        return "EUR", ""
    return profile.currency, profile.price_policy


def price_history_payload(
    package: PackageFormat,
    as_of,
    limit: int,
    offset: int,
) -> dict:
    """Serialize one package's complete dated history, one bounded page at a time."""
    prices = PriceVersion.objects.filter(space_id=package.space_id, package_id=package.pk)
    current = prices.filter(valid_from__lte=as_of).order_by("-valid_from", "-id").only("id").first()
    current_id = current.pk if current is not None else None
    count = prices.count()
    rows = []
    if offset < count:
        rows = list(
            prices.order_by("-valid_from", "-id")
            .only(
                "id",
                "amount",
                "explicit_free",
                "valid_from",
                "created_at",
                "created_by_id",
                "note",
            )[offset : offset + limit]
        )
    consumed = offset + len(rows)
    currency, _price_policy = _profile_values(package.space_id)
    return {
        "package": package.pk,
        "currency": currency,
        "as_of": as_of.isoformat(),
        "current_price_id": current_id,
        "count": count,
        "next_offset": consumed if consumed < count else None,
        "items": [
            {
                "id": row.pk,
                "amount": format(row.amount, "f"),
                "explicit_free": row.explicit_free,
                "valid_from": row.valid_from.isoformat(),
                "created_at": row.created_at.isoformat(),
                "created_by": row.created_by_id,
                "note": row.note,
                "is_current": row.pk == current_id,
            }
            for row in rows
        ],
    }


def _context_with_price(context, package_id: int, price: PriceVersion | None):
    prices = dict(context.prices)
    if price is None:
        prices.pop(package_id, None)
    else:
        prices[package_id] = price
    return replace(context, prices=prices)


class _TrackingPrices(dict):
    """Record only package prices the existing costing engine actually requests."""

    def __init__(self, values):
        super().__init__(values)
        self.read_keys: set[int] = set()

    def get(self, key, default=None):
        self.read_keys.add(key)
        return super().get(key, default)


def _cost_sheet(recipe, as_of, base_servings, servings, context) -> dict:
    warnings: list[str] = []
    lines = _cost_recipe_lines(
        recipe, 1, as_of, warnings, (), context, factor_ratio=(servings, base_servings),
    )
    return _sheet(lines, warnings, base_servings, servings)


def recipe_price_impact_payload(recipe, package: PackageFormat, servings: Decimal, as_of, user) -> dict:
    """Compare the latest two effective versions without recalculating the catalog."""
    roots, recipe_cache, _edges = native_recipe_graph([recipe.pk], recipe.space_id, user)
    base_servings = recipe.servings or 1
    if base_servings <= 0:
        raise DomainError("invalid_servings", "Las raciones base deben ser mayores que cero.")

    versions = list(
        PriceVersion.objects.filter(
            space_id=recipe.space_id,
            package_id=package.pk,
            valid_from__lte=as_of,
        )
        .order_by("-valid_from", "-id")[:2]
    )
    current = versions[0] if versions else None
    previous = versions[1] if len(versions) > 1 else None
    context = _load_costing_context(recipe_cache, recipe.space_id, as_of)

    with localcontext() as decimal_context:
        decimal_context.prec = 64
        captured_after_context = _context_with_price(context, package.pk, current)
        tracked_prices = _TrackingPrices(captured_after_context.prices)
        after_context = replace(captured_after_context, prices=tracked_prices)
        after = _cost_sheet(roots[0], as_of, base_servings, servings, after_context)
        affected = package.pk in tracked_prices.read_keys
        if affected:
            before_context = _context_with_price(context, package.pk, previous)
            before = _cost_sheet(roots[0], as_of, base_servings, servings, before_context)
        else:
            before = deepcopy(after)

        difference = None
        difference_per_serving = None
        if before["status"] == "complete" and after["status"] == "complete":
            before_total = Decimal(before["unrounded"])
            after_total = Decimal(after["unrounded"])
            delta = after_total - before_total
            difference = format(delta, "f")
            difference_per_serving = format(delta / servings, "f")

    currency, price_policy = _profile_values(recipe.space_id)
    return {
        "recipe_id": recipe.pk,
        "package": package.pk,
        "as_of": as_of.isoformat(),
        "current_price_id": current.pk if current is not None else None,
        "previous_price_id": previous.pk if previous is not None else None,
        "affected": affected,
        "before": before,
        "after": after,
        "difference": difference,
        "difference_per_serving": difference_per_serving,
        "currency": currency,
        "price_policy": price_policy,
    }
