"""Recipe finance metadata stored in Tandoor's native Recipe properties."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from cookbook.models import FoodProperty, Property, PropertyType, Recipe, Space
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal, parse_decimal
from cuaderno.models import SpaceProfile


SELLING_PRICE_PER_SERVING_SLUG = "cuaderno_selling_price_per_serving"
BUDGET_PER_PERSON_SLUG = "cuaderno_budget_per_person"
FINANCE_UNIT = "EUR/persona"

_DEFINITIONS = {
    "selling_price_per_serving": {
        "slug": SELLING_PRICE_PER_SERVING_SLUG,
        "name": "Precio de venta por persona",
        "category": PropertyType.PRICE,
    },
    "budget_per_person": {
        "slug": BUDGET_PER_PERSON_SLUG,
        "name": "Presupuesto por persona",
        "category": PropertyType.GOAL,
    },
}
_BY_SLUG = {definition["slug"]: (key, definition) for key, definition in _DEFINITIONS.items()}


def _money(value, *, field: str) -> Decimal:
    try:
        amount = parse_decimal(value, allow_zero=True)
    except DomainError as exc:
        raise DomainError("invalid_recipe_finance", f"{field}: {exc.message}") from exc

    exponent = amount.as_tuple().exponent
    decimal_places = max(-exponent, 0)
    integer_places = max(amount.adjusted() + 1, 0) if amount else 0
    if decimal_places > 4 or integer_places > 28 or integer_places + decimal_places > 32:
        raise DomainError(
            "invalid_recipe_finance",
            f"{field}: usa como máximo 28 enteros y 4 decimales.",
        )
    return amount


def _linked_properties(recipe: Recipe) -> dict[str, Property]:
    through = Recipe.properties.through
    property_ids = through._base_manager.filter(recipe_id=recipe.pk).values_list("property_id", flat=True)
    rows = list(
        Property._base_manager.filter(
            pk__in=property_ids,
            property_type__open_data_slug__in=_BY_SLUG,
        ).select_related("property_type")
    )
    found = {}
    for prop in rows:
        definition_entry = _BY_SLUG.get(prop.property_type.open_data_slug)
        if definition_entry is None:
            continue
        key, definition = definition_entry
        if key in found:
            raise DomainError("invalid_recipe_finance", f"La receta tiene más de una propiedad reservada para {key}.")
        if prop.space_id != recipe.space_id or prop.property_type.space_id != recipe.space_id:
            raise DomainError("recipe_finance_space", "La propiedad financiera pertenece a otro espacio.")
        if prop.property_type.category != definition["category"] or prop.property_type.unit != FINANCE_UNIT:
            raise DomainError("invalid_recipe_finance", f"La propiedad reservada {definition['slug']} está mal configurada.")
        if prop.property_amount is not None:
            _money(prop.property_amount, field=key)
        found[key] = prop
    return found


def _cost_per_serving(cost: dict) -> tuple[Decimal | None, list[str]]:
    if not isinstance(cost, dict):
        raise DomainError("invalid_recipe_finance", "El escandallo debe ser un objeto.")
    status = cost.get("status")
    if status not in {"complete", "incomplete", "invalid", "needs_conversion"}:
        raise DomainError("invalid_recipe_finance", "El estado del escandallo no es válido.")
    raw_warnings = cost.get("warnings") or []
    if not isinstance(raw_warnings, list) or any(not isinstance(item, str) for item in raw_warnings):
        raise DomainError("invalid_recipe_finance", "Los avisos del escandallo no son válidos.")
    value = cost.get("per_serving")
    parsed = _derived_decimal(value) if value is not None else None
    if status == "complete" and parsed is None:
        raise DomainError("invalid_recipe_finance", "Un escandallo completo necesita coste por persona.")
    if status != "complete":
        parsed = None
    return parsed, list(raw_warnings)


def _derived_decimal(value) -> Decimal:
    """Validate a calculated cost without applying the 4-place storage limit."""
    try:
        amount = parse_decimal(value, allow_zero=True)
    except DomainError as exc:
        raise DomainError("invalid_recipe_finance", f"ingredient_cost_per_serving: {exc.message}") from exc
    exponent = amount.as_tuple().exponent
    if amount and (amount.adjusted() >= 32 or exponent < -32):
        raise DomainError("invalid_recipe_finance", "El coste calculado queda fuera del dominio admitido.")
    return amount


def read_recipe_finance(recipe: Recipe, cost: dict, profile: SpaceProfile) -> dict:
    """Read native properties and calculate non-accounting per-person indicators."""
    if not recipe.pk or profile.space_id != recipe.space_id:
        raise DomainError("recipe_finance_space", "La receta y la política deben pertenecer al mismo espacio.")
    properties = _linked_properties(recipe)
    values = {
        key: (None if properties.get(key) is None or properties[key].property_amount is None else properties[key].property_amount)
        for key in _DEFINITIONS
    }
    ingredient_cost, warnings = _cost_per_serving(cost)
    if ingredient_cost is None:
        warnings.append("cost_incomplete")
    if values["selling_price_per_serving"] is None:
        warnings.append("selling_price_unknown")
    if values["budget_per_person"] is None:
        warnings.append("budget_unknown")

    policy = profile.price_policy if profile.price_policy in {SpaceProfile.NET, SpaceProfile.GROSS} else None
    policy_ready = policy is not None and profile.currency == "EUR"
    if policy is None:
        warnings.append("price_policy_unknown")
    if profile.currency != "EUR":
        warnings.append("currency_unsupported")

    difference = ratio = budget_gap = None
    calculated = False
    if ingredient_cost is not None and policy_ready:
        sale = values["selling_price_per_serving"]
        if sale is not None:
            if sale == 0:
                warnings.append("selling_price_zero")
            else:
                with localcontext() as context:
                    context.prec = 64
                    difference = sale - ingredient_cost
                    ratio = (ingredient_cost / sale).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                calculated = True
        budget = values["budget_per_person"]
        if budget is not None:
            with localcontext() as context:
                context.prec = 64
                budget_gap = budget - ingredient_cost
            calculated = True

    return {
        "selling_price_per_serving": _decimal_or_none(values["selling_price_per_serving"]),
        "budget_per_person": _decimal_or_none(values["budget_per_person"]),
        "ingredient_cost_per_serving": _decimal_or_none(ingredient_cost),
        "difference_per_serving": _decimal_or_none(difference),
        "food_cost_ratio": None if ratio is None else format(ratio, "f"),
        "budget_gap_per_person": _decimal_or_none(budget_gap),
        "price_policy": policy,
        "status": "complete" if calculated else "incomplete",
        "warnings": list(dict.fromkeys(warnings)),
        "net_profit": None,
    }


def _decimal_or_none(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _property_type(space_id: int, definition: dict) -> PropertyType:
    row = PropertyType._base_manager.filter(
        space_id=space_id,
        open_data_slug=definition["slug"],
    ).first()
    if row is None:
        if PropertyType._base_manager.filter(space_id=space_id, name=definition["name"]).exists():
            raise DomainError(
                "invalid_recipe_finance",
                f"Ya existe un tipo llamado {definition['name']} sin el identificador reservado.",
            )
        row = PropertyType._base_manager.create(
            space_id=space_id,
            name=definition["name"],
            category=definition["category"],
            unit=FINANCE_UNIT,
            open_data_slug=definition["slug"],
        )
    if row.category != definition["category"] or row.unit != FINANCE_UNIT:
        raise DomainError("invalid_recipe_finance", f"La propiedad reservada {definition['slug']} está mal configurada.")
    return row


def _unlink(recipe_id: int, prop: Property) -> None:
    through = Recipe.properties.through
    through._base_manager.filter(recipe_id=recipe_id, property_id=prop.pk).delete()
    used_by_recipe = through._base_manager.filter(property_id=prop.pk).exists()
    used_by_food = FoodProperty._base_manager.filter(property_id=prop.pk).exists()
    if not used_by_recipe and not used_by_food:
        Property._base_manager.filter(pk=prop.pk).delete()


@transaction.atomic
def write_recipe_finance(recipe: Recipe, data: dict, user) -> None:
    """Write only supplied finance keys and audit actual changes with Django's native log."""
    if not isinstance(data, dict):
        raise DomainError("invalid_recipe_finance", "Los datos financieros deben ser un objeto.")
    unknown = set(data) - set(_DEFINITIONS)
    if unknown:
        raise DomainError("invalid_recipe_finance", "Hay campos financieros desconocidos.")
    if not recipe.pk or not getattr(user, "pk", None):
        raise DomainError("invalid_recipe_finance", "La receta y el autor deben estar guardados.")

    parsed = {
        key: None if data[key] is None else _money(data[key], field=key)
        for key in data
    }
    Space._base_manager.select_for_update().get(pk=recipe.space_id)
    locked = Recipe._base_manager.select_for_update().get(pk=recipe.pk)
    properties = _linked_properties(locked)
    through = Recipe.properties.through
    changed = []

    for key, value in parsed.items():
        current = properties.get(key)
        if value is None:
            if current is not None:
                _unlink(locked.pk, current)
                changed.append(_DEFINITIONS[key]["slug"])
            continue
        if current is not None and current.property_amount == value:
            continue

        definition = _DEFINITIONS[key]
        property_type = _property_type(locked.space_id, definition)
        if current is not None:
            shared = (
                through._base_manager.filter(property_id=current.pk).exclude(recipe_id=locked.pk).exists()
                or FoodProperty._base_manager.filter(property_id=current.pk).exists()
            )
            if shared:
                through._base_manager.filter(recipe_id=locked.pk, property_id=current.pk).delete()
                current = None
            else:
                current.property_amount = value
                current.property_type = property_type
                current.space_id = locked.space_id
                current.save(update_fields=["property_amount", "property_type", "space"])
        if current is None:
            current = Property._base_manager.create(
                space_id=locked.space_id,
                property_type=property_type,
                property_amount=value,
            )
            through._base_manager.create(recipe_id=locked.pk, property_id=current.pk)
        changed.append(definition["slug"])

    if not changed:
        return
    locked.updated_at = timezone.now()
    locked.save(update_fields=["updated_at"])
    recipe.updated_at = locked.updated_at
    LogEntry.objects.create(
        user_id=user.pk,
        content_type=ContentType.objects.get_for_model(Recipe),
        object_id=str(locked.pk),
        object_repr=str(locked)[:200],
        action_flag=CHANGE,
        change_message=json.dumps([{"changed": {"fields": changed}}]),
    )
