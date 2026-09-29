"""Persistent service workflow on native MealPlan and InventoryEntry rows."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import Food, InventoryEntry, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal
from cuaderno.models import ServicePlan, SpaceProfile
from cuaderno.services.costing import cost_recipe, current_price, reference_package
from cuaderno.services.ledger import IdempotencyConflict, apply_movement
from cuaderno.services.subrecipes import convert_native_quantity, sheet_from_recipes


def decimal_string(value) -> str:
    return canonical_decimal(value)


def accessible_service_plans(request, plan_id=None):
    rows = ServicePlan.objects.filter(space=request.space)
    if plan_id is not None:
        rows = rows.filter(pk=plan_id)
    if not has_group_permission(request, ["admin"]):
        membership = getattr(request, "user_space", None)
        if membership is None:
            return rows.none()
        if membership.household_id:
            rows = rows.filter(
                Q(household_id=membership.household_id)
                | Q(household__isnull=True, created_by=request.user)
            )
        else:
            rows = rows.filter(household__isnull=True, created_by=request.user)

    # A frozen sheet can disclose every recipe in its graph, not just the
    # MealPlan root. Re-evaluate native recipe ACLs for list, detail and every
    # transition. Admin oversight does not override a private recipe.
    # Detail/transition inspects one candidate; list is capped to latest 100.
    candidates = list(rows.order_by("-pk")[:100].values("pk", "meal_plan__recipe_id", "snapshot"))
    required_by_plan: dict[int, set[int] | None] = {}
    all_recipe_ids: set[int] = set()

    def recipe_id(value):
        if isinstance(value, bool):
            raise ValueError
        parsed = int(value)
        if parsed <= 0:
            raise ValueError
        return parsed

    for row in candidates:
        required = set()
        try:
            if row["meal_plan__recipe_id"]:
                required.add(recipe_id(row["meal_plan__recipe_id"]))
            snapshot = row["snapshot"] or {}
            if not isinstance(snapshot, dict):
                raise ValueError
            if snapshot.get("recipe_id"):
                required.add(recipe_id(snapshot["recipe_id"]))
            graph = snapshot.get("recipe_graph") or {}
            if not isinstance(graph, dict):
                raise ValueError
            for parent, children in graph.items():
                required.add(recipe_id(parent))
                if not isinstance(children, list):
                    raise ValueError
                required.update(recipe_id(child) for child in children)
        except (TypeError, ValueError):
            required_by_plan[row["pk"]] = None
            continue
        required_by_plan[row["pk"]] = required
        all_recipe_ids.update(required)

    from cuaderno.services.costing import visible_recipes

    visible_ids = set(
        visible_recipes(request.user, request.space)
        .filter(pk__in=all_recipe_ids)
        .values_list("pk", flat=True)
    )
    allowed_ids = [
        plan_id
        for plan_id, required in required_by_plan.items()
        if required is not None and required.issubset(visible_ids)
    ]
    return rows.filter(pk__in=allowed_ids)


def serialize_service_plan(plan: ServicePlan) -> dict:
    return {
        "id": plan.pk,
        "title": plan.title,
        "covers": decimal_string(plan.covers),
        "service_date": plan.service_date.isoformat() if plan.service_date else None,
        "state": plan.state,
        "meal_plan": plan.meal_plan_id,
        "household": plan.household_id,
        "snapshot": plan.snapshot,
        "confirmed_at": plan.confirmed_at.isoformat() if plan.confirmed_at else None,
        "produced_at": plan.produced_at.isoformat() if plan.produced_at else None,
        "created_by": plan.created_by_id,
    }


def _snapshot_needs(sheet: dict, space) -> list[dict]:
    names = list(sheet.get("needs", {}))
    foods = {row.name: row for row in Food.objects.filter(space=space, name__in=names)}
    unit_names = {name for name in sheet.get("units", {}).values() if name}
    units = {row.name: row for row in Unit.objects.filter(space=space, name__in=unit_names)}
    needs = []
    for name in sorted(names):
        food = foods.get(name)
        if food is None:
            raise ValidationError({"recipe": f"El alimento {name} ya no está disponible en este espacio."})
        unit_name = sheet.get("units", {}).get(name)
        unit = units.get(unit_name)
        needs.append(
            {
                "food_id": food.pk,
                "food_name": food.name,
                "unit_id": unit.pk if unit else None,
                "unit_name": unit_name,
                "quantity": decimal_string(sheet["needs"][name]),
            }
        )
    return needs


def _source_versions(recipe, needs: list[dict], at) -> dict:
    prices = {}
    for need in needs:
        food = Food.objects.get(pk=need["food_id"], space=recipe.space)
        package = reference_package(food)
        price = current_price(package, at) if package else None
        prices[str(food.pk)] = price.pk if price else None
    return {
        "recipe": {"id": recipe.pk, "updated_at": recipe.updated_at.isoformat()},
        "price_versions": prices,
    }


@transaction.atomic
def confirm_service_plan(plan: ServicePlan, user) -> ServicePlan:
    type(plan.space).objects.select_for_update().get(pk=plan.space_id)
    plan = (
        ServicePlan.objects.select_for_update(of=("self",))
        .select_related("meal_plan__recipe", "space")
        .get(pk=plan.pk, space=plan.space)
    )
    if plan.state == ServicePlan.CONFIRMED:
        return plan
    if plan.state != ServicePlan.DRAFT:
        raise ValidationError({"state": "Solo se puede confirmar un servicio en borrador."})
    if plan.service_date is None:
        raise ValidationError({"service_date": "El servicio heredado necesita una fecha antes de confirmarse."})
    recipe = plan.meal_plan.recipe if plan.meal_plan_id else None
    confirmed_at = timezone.now()
    needs, cost, graph, warnings, versions = [], None, {}, [], {}
    if recipe is not None:
        base_servings = Decimal(str(recipe.servings))
        if base_servings <= 0:
            raise ValidationError({"recipe": "Las raciones base de la receta deben ser positivas."})
        factor = Decimal(plan.covers) / base_servings
        try:
            sheet = sheet_from_recipes([recipe.pk], plan.space, user, factors={recipe.pk: factor})
            cost = cost_recipe(recipe, plan.covers, as_of=confirmed_at, user=user)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        needs = _snapshot_needs(sheet, plan.space)
        graph = sheet.get("edges", {})
        warnings = sheet.get("warnings", [])
        versions = _source_versions(recipe, needs, confirmed_at)
    plan.snapshot = {
        "schema_version": 1,
        "confirmed_at": confirmed_at.isoformat(),
        "service_date": plan.service_date.isoformat(),
        "covers": decimal_string(plan.covers),
        "recipe_id": recipe.pk if recipe else None,
        "needs": needs,
        "cost": cost,
        "recipe_graph": graph,
        "warnings": warnings,
        "source_versions": versions,
    }
    plan.state = ServicePlan.CONFIRMED
    plan.confirmed_at = confirmed_at
    plan.save(update_fields=["snapshot", "state", "confirmed_at"])
    return plan


@transaction.atomic
def cancel_service_plan(plan: ServicePlan) -> ServicePlan:
    type(plan.space).objects.select_for_update().get(pk=plan.space_id)
    plan = ServicePlan.objects.select_for_update().get(pk=plan.pk, space=plan.space)
    if plan.state == ServicePlan.CANCELLED:
        return plan
    if plan.state not in (ServicePlan.DRAFT, ServicePlan.CONFIRMED):
        raise ValidationError({"state": "Un servicio producido no se puede cancelar sin una reversión de stock."})
    plan.state = ServicePlan.CANCELLED
    plan.save(update_fields=["state"])
    return plan


def _production_key(plan: ServicePlan, raw_key) -> str:
    if not isinstance(raw_key, str) or not raw_key.strip() or len(raw_key) > 128:
        raise ValidationError({"idempotency_key": "La producción necesita una clave de hasta 128 caracteres."})
    return raw_key.strip()


def _owner_household(plan: ServicePlan):
    return plan.household_id


def _locked_allocations(plan: ServicePlan) -> list[tuple[InventoryEntry, Decimal]]:
    household_id = _owner_household(plan)
    if household_id is None:
        raise ValidationError({"stock": "El servicio no tiene un hogar de inventario asignado."})
    needs = plan.snapshot.get("needs") or []
    food_ids = [need.get("food_id") for need in needs if need.get("food_id")]
    # A late production cannot revive a lot that expired after the planned
    # service date. Stock must be usable both for the service and today.
    usable_on = max(plan.service_date, timezone.localdate())
    entries = list(
        InventoryEntry.objects.select_for_update(of=("self",))
        .filter(
            space=plan.space,
            inventory_location__household_id=household_id,
            food_id__in=food_ids,
            amount__gt=0,
        )
        .filter(Q(expires__isnull=True) | Q(expires__gte=usable_on))
        .select_related("food", "unit", "inventory_location")
        .order_by("food_id", F("expires").asc(nulls_last=True), "id")
    )
    by_food = {}
    for entry in entries:
        by_food.setdefault(entry.food_id, []).append(entry)
    allocations = []
    for need in needs:
        try:
            remaining = Decimal(str(need["quantity"]))
        except Exception as exc:
            raise ValidationError({"snapshot": "La cantidad congelada no es válida."}) from exc
        if not remaining.is_finite() or remaining <= 0:
            raise ValidationError({"snapshot": "La cantidad congelada debe ser positiva."})
        unit_id = need.get("unit_id")
        if not unit_id:
            raise ValidationError({"stock": f"{need.get('food_name')} no tiene unidad convertible."})
        required_unit = Unit.objects.filter(pk=unit_id, space=plan.space).first()
        food = Food.objects.filter(pk=need.get("food_id"), space=plan.space).first()
        if required_unit is None or food is None:
            raise ValidationError({"snapshot": "Un alimento o unidad congelado ya no está disponible."})
        for entry in by_food.get(food.pk, []):
            if remaining <= 0:
                break
            if entry.unit_id is None:
                continue
            try:
                available_required = convert_native_quantity(entry.amount, entry.unit, required_unit, food, plan.space)
            except DomainError:
                continue
            if available_required <= 0:
                continue
            if available_required <= remaining:
                entry_quantity = Decimal(entry.amount)
                used_required = available_required
            else:
                try:
                    entry_quantity = convert_native_quantity(remaining, required_unit, entry.unit, food, plan.space)
                except DomainError:
                    continue
                used_required = remaining
            allocations.append((entry, entry_quantity))
            remaining -= used_required
        if remaining > 0:
            raise ValidationError(
                {"insufficient_stock": {"food": need.get("food_name"), "missing": decimal_string(remaining), "unit": need.get("unit_name")}}
            )
    return allocations


def _movement_key(plan: ServicePlan, produced_key: str, index: int, entry_id: int) -> str:
    digest = hashlib.sha256(f"{plan.pk}:{produced_key}:{index}:{entry_id}".encode()).hexdigest()
    return f"service:{plan.pk}:{digest}"


@transaction.atomic
def produce_service_plan(plan: ServicePlan, user, raw_key) -> tuple[ServicePlan, list[int], bool]:
    produced_key = _production_key(plan, raw_key)
    type(plan.space).objects.select_for_update().get(pk=plan.space_id)
    plan = (
        ServicePlan.objects.select_for_update(of=("self",))
        .select_related("space")
        .get(pk=plan.pk, space=plan.space)
    )
    conflict = ServicePlan.objects.filter(space=plan.space, produced_key=produced_key).exclude(pk=plan.pk).exists()
    if conflict:
        raise IdempotencyConflict({"idempotency_key": "La clave ya pertenece a otro servicio."})
    if plan.state == ServicePlan.PRODUCED:
        if plan.produced_key != produced_key:
            raise IdempotencyConflict({"idempotency_key": "El servicio ya se produjo con otra clave."})
        production = plan.snapshot.get("production") or {}
        return plan, list(production.get("movement_ids") or []), bool(production.get("stock_changed"))
    if plan.state != ServicePlan.CONFIRMED:
        raise ValidationError({"state": "Solo se puede producir un servicio confirmado."})
    if plan.snapshot.get("recipe_id") is None:
        raise ValidationError({"recipe": "El servicio necesita una receta antes de producirse."})
    blocking_codes = {"ingredient_incomplete", "yield_missing"}
    blocking_warnings = [
        warning
        for warning in (plan.snapshot.get("warnings") or [])
        if isinstance(warning, dict) and warning.get("code") in blocking_codes
    ]
    if blocking_warnings:
        raise ValidationError(
            {"production_sheet": "Completa los ingredientes y rendimientos pendientes antes de producir."}
        )

    profile = SpaceProfile.objects.select_for_update().get(space=plan.space)
    movement_ids = []
    stock_changed = False
    if profile.edition == SpaceProfile.INTEGRAL:
        allocations = _locked_allocations(plan)
        for index, (entry, quantity) in enumerate(allocations):
            movement = apply_movement(
                entry_id=entry.pk,
                space=plan.space,
                user=user,
                kind="consume",
                quantity=quantity,
                idempotency_key=_movement_key(plan, produced_key, index, entry.pk),
                origin={
                    "type": "service_plan",
                    "id": plan.pk,
                    "service_date": plan.service_date.isoformat(),
                },
            )
            movement_ids.append(movement.pk)
        stock_changed = bool(movement_ids)

    produced_at = timezone.now()
    snapshot = dict(plan.snapshot)
    snapshot["production"] = {
        "produced_at": produced_at.isoformat(),
        "edition": profile.edition,
        "movement_ids": movement_ids,
        "stock_changed": stock_changed,
    }
    plan.snapshot = snapshot
    plan.state = ServicePlan.PRODUCED
    plan.produced_at = produced_at
    plan.produced_key = produced_key
    plan.save(update_fields=["snapshot", "state", "produced_at", "produced_key"])
    return plan, movement_ids, stock_changed
