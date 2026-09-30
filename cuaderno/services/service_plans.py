"""Persistent service workflow on native MealPlan and InventoryEntry rows."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import Food, InventoryEntry, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal
from cuaderno.models import ServicePlan, SpaceProfile, StockMovement
from cuaderno.services.costing import cost_recipe, current_price, reference_package
from cuaderno.services.ledger import IdempotencyConflict, apply_movement, movement_fingerprint
from cuaderno.services.subrecipes import convert_native_quantity, sheet_from_recipes


def decimal_string(value) -> str:
    return canonical_decimal(value)


def accessible_service_plans(request, plan_id=None, *, as_list=False):
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
    materialized = None
    if as_list:
        # The list response needs the same bounded rows that ACLs inspect.
        # Keep detail/transitions as querysets, but do not fetch list snapshots twice.
        materialized = list(rows.order_by("-pk").annotate(_root_recipe_id=F("meal_plan__recipe_id"))[:100])
        candidates = [
            {"pk": plan.pk, "meal_plan__recipe_id": plan._root_recipe_id, "snapshot": plan.snapshot}
            for plan in materialized
        ]
    else:
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
    if materialized is not None:
        allowed = set(allowed_ids)
        # Match PostgreSQL ASC NULLS LAST for legacy undated services.
        return sorted(
            (plan for plan in materialized if plan.pk in allowed),
            key=lambda plan: (plan.service_date is None, plan.service_date, plan.pk),
        )
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
    needs, cost, graph, warnings, versions, finance, yield_details = [], None, {}, [], {}, None, []
    allergens = None
    if recipe is not None:
        base_servings = Decimal(str(recipe.servings))
        if base_servings <= 0:
            raise ValidationError({"recipe": "Las raciones base de la receta deben ser positivas."})
        try:
            sheet = sheet_from_recipes(
                [recipe.pk], plan.space, user, factor_ratios={recipe.pk: (plan.covers, base_servings)},
            )
            cost = cost_recipe(recipe, plan.covers, as_of=confirmed_at, user=user)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        needs = _snapshot_needs(sheet, plan.space)
        graph = sheet.get("edges", {})
        warnings = sheet.get("warnings", [])
        yield_details = sheet.get("ingredient_yields", [])
        versions = _source_versions(recipe, needs, confirmed_at)
        from cuaderno.services.allergens import recipe_allergens
        try:
            allergens = recipe_allergens(user=user, space=plan.space, recipe_id=recipe.pk)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        from cuaderno.services.recipe_finance import read_recipe_finance
        profile, _ = SpaceProfile.objects.get_or_create(space=plan.space)
        try:
            finance = read_recipe_finance(recipe, cost, profile)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
    plan.snapshot = {
        "schema_version": 2 if yield_details else 1,
        "confirmed_at": confirmed_at.isoformat(),
        "service_date": plan.service_date.isoformat(),
        "covers": decimal_string(plan.covers),
        "recipe_id": recipe.pk if recipe else None,
        "needs": needs,
        "cost": cost,
        "finance": finance,
        "recipe_graph": graph,
        "warnings": warnings,
        "source_versions": versions,
        "allergens": allergens,
    }
    if yield_details:
        plan.snapshot["ingredient_yields"] = yield_details
    plan.state = ServicePlan.CONFIRMED
    plan.confirmed_at = confirmed_at
    plan.save(update_fields=["snapshot", "state", "confirmed_at"])
    from cuaderno.services.preparation import seed_preparation
    seed_preparation(plan, user)
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


def _reversal_key(plan, key, index, movement_id):
    digest = hashlib.sha256(f"{plan.pk}:{key}:{index}:{movement_id}".encode("utf-8")).hexdigest()
    return f"service-reversal:{plan.pk}:{digest}"


@transaction.atomic
def reverse_service_plan(plan: ServicePlan, user, raw_key) -> tuple[ServicePlan, list[int], bool]:
    """Compensate the complete production, never an isolated allocation.

    Cancellation is terminal: preserve the original production and frozen
    financial/needs documents, adding only the reversal audit. A Space lock
    serializes replay, competing reversals and all native stock writers.
    """
    key = _production_key(plan, raw_key)
    key_sha256 = hashlib.sha256(key.encode("utf-8")).hexdigest()
    type(plan.space).objects.select_for_update().only("pk").get(pk=plan.space_id)
    plan = ServicePlan.objects.select_for_update().get(pk=plan.pk, space_id=plan.space_id)

    def invalid():
        raise ValidationError({"production": "El historial de producción no permite una reversión completa segura."})

    if not isinstance(plan.snapshot, dict):
        invalid()
    production = plan.snapshot.get("production")
    if not isinstance(production, dict):
        invalid()
    from cuaderno.services.production_waste import validate_frozen_classification
    validate_frozen_classification(plan)
    audit = production.get("reversal")
    if audit is not None:
        if not isinstance(audit, dict) or plan.state != ServicePlan.CANCELLED:
            invalid()
        if audit.get("key_sha256") != key_sha256:
            raise IdempotencyConflict({"idempotency_key": "El servicio ya se revirtió con otra clave."})
    elif plan.state != ServicePlan.PRODUCED:
        raise ValidationError({"state": "Solo se puede revertir la producción completa de un servicio producido."})
    if not plan.produced_key or plan.produced_at is None:
        invalid()
    if ServicePlan.objects.filter(
        space_id=plan.space_id, snapshot__production__reversal__key_sha256=key_sha256,
    ).exclude(pk=plan.pk).exists():
        raise IdempotencyConflict({"idempotency_key": "La clave ya pertenece a la reversión de otro servicio."})

    original_ids = production.get("movement_ids")
    if (not isinstance(original_ids, list) or len(original_ids) > 10000
            or any(type(value) is not int or not 0 < value <= 9223372036854775807 for value in original_ids)
            or len(set(original_ids)) != len(original_ids)):
        invalid()
    edition = production.get("edition")
    if (edition not in (SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL)
            or type(production.get("stock_changed")) is not bool
            or production["stock_changed"] != bool(original_ids)
            or (edition == SpaceProfile.PROFESIONAL and original_ids)
            or (edition == SpaceProfile.INTEGRAL and plan.household_id is None)):
        invalid()

    # A shortened snapshot must not restore only a subset of allocations.
    actual_ids = set(StockMovement.objects.filter(
        space_id=plan.space_id, kind=StockMovement.CONSUME, reverses__isnull=True,
        metadata_snapshot__origin__type="service_plan", metadata_snapshot__origin__id=plan.pk,
    ).order_by("pk").values_list("pk", flat=True)[:10001])
    if actual_ids != set(original_ids):
        invalid()
    originals = {
        row.pk: row for row in StockMovement.objects.select_for_update()
        .filter(space_id=plan.space_id, pk__in=original_ids).order_by("pk")
    }
    reversals = list(StockMovement.objects.select_for_update().filter(
        space_id=plan.space_id, reverses_id__in=original_ids,
    ).order_by("pk"))
    if len(originals) != len(original_ids) or (audit is None and reversals):
        invalid()
    entries = {
        row.pk: row for row in InventoryEntry.objects.select_for_update(of=("self",))
        .filter(space_id=plan.space_id, pk__in=[row.entry_id for row in originals.values()])
        .select_related("inventory_location", "unit", "food").order_by("pk")
    }
    for index, identifier in enumerate(original_ids):
        original = originals[identifier]
        metadata = original.metadata_snapshot
        entry = entries.get(original.entry_id)
        if not isinstance(metadata, dict) or entry is None:
            invalid()
        origin = metadata.get("origin")
        if (not isinstance(origin, dict) or origin.get("type") != "service_plan"
                or type(origin.get("id")) is not int or origin["id"] != plan.pk
                or origin.get("service_date") != plan.snapshot.get("service_date")
                or original.kind != StockMovement.CONSUME or original.reverses_id is not None
                or not original.quantity.is_finite() or original.quantity <= 0
                or original.idempotency_key != _movement_key(plan, plan.produced_key, index, entry.pk)
                or type(metadata.get("household_id")) is not int
                or metadata.get("household_id") != plan.household_id
                or entry.inventory_location.space_id != plan.space_id
                or entry.inventory_location.household_id != plan.household_id
                or type(metadata.get("unit_id")) is not int or type(metadata.get("food_id")) is not int
                or metadata.get("unit_id") != entry.unit_id or metadata.get("food_id") != entry.food_id
                or entry.unit_id is None or entry.unit.space_id != plan.space_id
                or entry.food_id is None or entry.food.space_id != plan.space_id):
            invalid()
        if original.fingerprint != movement_fingerprint(
            entry_id=entry.pk, kind=StockMovement.CONSUME,
            canonical_quantity=canonical_decimal(original.quantity), origin=origin,
        ):
            invalid()

    if audit is not None:
        ids = audit.get("movement_ids")
        audit_originals = audit.get("original_movement_ids")
        if (set(audit) != {"key_sha256", "reversed_at", "reversed_by", "original_movement_ids", "movement_ids"}
                or not isinstance(ids, list) or len(ids) != len(original_ids)
                or any(type(value) is not int or not 0 < value <= 9223372036854775807 for value in ids)
                or len(set(ids)) != len(ids) or set(ids) & set(original_ids)
                or not isinstance(audit_originals, list)
                or any(type(value) is not int for value in audit_originals) or audit_originals != original_ids
                or type(audit.get("reversed_by")) is not int or audit["reversed_by"] <= 0
                or not isinstance(audit.get("reversed_at"), str)):
            invalid()
        try:
            reversed_at = datetime.fromisoformat(audit["reversed_at"])
        except ValueError:
            invalid()
        if timezone.is_naive(reversed_at) or reversed_at < plan.produced_at:
            invalid()
        by_id = {row.pk: row for row in reversals}
        if set(by_id) != set(ids):
            invalid()
        for index, (original_id, reversal_id) in enumerate(zip(original_ids, ids)):
            original, reversal = originals[original_id], by_id[reversal_id]
            if (reversal.reverses_id != original_id or reversal.entry_id != original.entry_id
                    or reversal.kind != StockMovement.RECEIPT or reversal.quantity != original.quantity
                    or reversal.created_by_id != audit["reversed_by"] or reversal.created_at > reversed_at
                    or reversal.idempotency_key != _reversal_key(plan, key, index, original_id)
                    or not isinstance(reversal.metadata_snapshot, dict)):
                invalid()
            metadata = reversal.metadata_snapshot
            if any(metadata.get(field) != original.metadata_snapshot.get(field)
                   for field in ("food_id", "unit_id", "household_id", "origin")):
                invalid()
            if reversal.fingerprint != movement_fingerprint(
                entry_id=original.entry_id, kind=StockMovement.RECEIPT,
                canonical_quantity=canonical_decimal(original.quantity), reverses_id=original_id,
                origin=original.metadata_snapshot["origin"],
            ):
                invalid()
        return plan, ids, bool(ids)

    reversal_ids = []
    for index, identifier in enumerate(original_ids):
        original = originals[identifier]
        movement = apply_movement(
            entry_id=original.entry_id, space=plan.space, user=user, kind=StockMovement.RECEIPT,
            quantity=original.quantity, idempotency_key=_reversal_key(plan, key, index, identifier),
            reverses_id=identifier, origin=original.metadata_snapshot["origin"],
        )
        reversal_ids.append(movement.pk)
    snapshot = deepcopy(plan.snapshot)
    snapshot["production"]["reversal"] = {
        "key_sha256": key_sha256, "reversed_at": timezone.now().isoformat(),
        "reversed_by": user.pk, "original_movement_ids": list(original_ids), "movement_ids": reversal_ids,
    }
    plan.snapshot = snapshot
    plan.state = ServicePlan.CANCELLED
    plan.save(update_fields=["snapshot", "state"])
    return plan, reversal_ids, bool(reversal_ids)


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
        from cuaderno.services.production_waste import validate_frozen_classification
        validate_frozen_classification(plan)
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

    from cuaderno.services.production_waste import classify_declared_loss
    classification = classify_declared_loss(plan.snapshot, user.pk, timezone.now())
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
    classification["recorded_at"] = produced_at.isoformat()
    snapshot = dict(plan.snapshot)
    snapshot["production"] = {
        "schema_version": 2,
        "produced_at": produced_at.isoformat(),
        "edition": profile.edition,
        "movement_ids": movement_ids,
        "stock_changed": stock_changed,
        "waste_classification": classification,
    }
    plan.snapshot = snapshot
    plan.state = ServicePlan.PRODUCED
    plan.produced_at = produced_at
    plan.produced_key = produced_key
    plan.save(update_fields=["snapshot", "state", "produced_at", "produced_key"])
    return plan, movement_ids, stock_changed
