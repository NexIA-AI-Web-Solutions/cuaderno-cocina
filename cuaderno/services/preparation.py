"""Frozen, service-local preparation checklists backed by native recipe steps."""

from __future__ import annotations

import hashlib
import json

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch
from rest_framework.exceptions import ValidationError

from cookbook.models import Recipe, Step
from cuaderno.models import ServicePlan, ServicePreparationItem
from cuaderno.services.costing import visible_recipes
from cuaderno.services.subrecipes import MAX_NATIVE_GRAPH_RECIPES


def _snapshot_identifier(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError({"preparation": f"El identificador {field} congelado no es válido."})
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"preparation": f"El identificador {field} congelado no es válido."}) from exc
    if parsed <= 0 or str(parsed) != str(value):
        raise ValidationError({"preparation": f"El identificador {field} congelado no es válido."})
    return parsed


def _ordered_recipe_ids(snapshot: dict) -> list[int]:
    if not isinstance(snapshot, dict):
        raise ValidationError({"preparation": "La ficha congelada del servicio no es válida."})
    root_value = snapshot.get("recipe_id")
    if root_value is None:
        return []
    root_id = _snapshot_identifier(root_value, "recipe_id")
    raw_graph = snapshot.get("recipe_graph", {})
    if not isinstance(raw_graph, dict):
        raise ValidationError({"preparation": "El grafo congelado de recetas no es válido."})

    graph: dict[int, list[int]] = {}
    mentioned = {root_id}
    for raw_parent, raw_children in raw_graph.items():
        parent = _snapshot_identifier(raw_parent, "recipe_graph")
        if not isinstance(raw_children, list):
            raise ValidationError({"preparation": "El grafo congelado de recetas no es válido."})
        children = [_snapshot_identifier(child, "recipe_graph") for child in raw_children]
        graph[parent] = children
        mentioned.add(parent)
        mentioned.update(children)

    ordered: list[int] = []
    visited: set[int] = set()
    active: set[int] = set()

    def visit(recipe_id: int):
        if recipe_id in active:
            raise ValidationError({"preparation": "El grafo congelado de recetas contiene un ciclo."})
        if recipe_id in visited:
            return
        if len(visited) >= MAX_NATIVE_GRAPH_RECIPES:
            raise ValidationError({"preparation": "La ficha supera el límite de recetas de preparación."})
        active.add(recipe_id)
        visited.add(recipe_id)
        ordered.append(recipe_id)
        for child_id in graph.get(recipe_id, []):
            visit(child_id)
        active.remove(recipe_id)

    visit(root_id)
    if visited != mentioned:
        raise ValidationError({"preparation": "El grafo congelado contiene recetas desconectadas."})
    return ordered


def seed_preparation(plan: ServicePlan, user) -> list[ServicePreparationItem]:
    """Freeze native steps once; caller owns the confirmation transaction and locks."""
    if plan.state != ServicePlan.CONFIRMED:
        raise ValidationError({"state": "La preparación solo se crea al confirmar el servicio."})
    existing = list(
        ServicePreparationItem._base_manager.select_for_update()
        .filter(service_id=plan.pk, space_id=plan.space_id)
        .order_by("position", "pk")
    )
    if existing:
        return existing

    recipe_ids = _ordered_recipe_ids(plan.snapshot)
    if not recipe_ids:
        return []
    visible_ids = set(
        visible_recipes(user, plan.space)
        .filter(pk__in=recipe_ids)
        .values_list("pk", flat=True)
    )
    if visible_ids != set(recipe_ids):
        raise ValidationError({"preparation": "Una receta congelada ya no es visible para confirmar el servicio."})

    step_rows = Step._base_manager.filter(space_id=plan.space_id).order_by("order", "pk")
    recipes = {
        recipe.pk: recipe
        for recipe in Recipe._base_manager.filter(space_id=plan.space_id, pk__in=recipe_ids)
        .prefetch_related(Prefetch("steps", queryset=step_rows, to_attr="preparation_steps"))
    }
    if set(recipes) != set(recipe_ids):
        raise ValidationError({"preparation": "Una receta congelada ya no pertenece al espacio del servicio."})

    items = []
    position = 0
    for recipe_id in recipe_ids:
        for step in recipes[recipe_id].preparation_steps:
            items.append(ServicePreparationItem(
                space_id=plan.space_id,
                service_id=plan.pk,
                source_step_id=step.pk,
                task_key=f"{recipe_id}:{step.pk}",
                position=position,
                recipe_id_snapshot=recipe_id,
                name=step.name,
                instruction=step.instruction,
            ))
            position += 1
    if items:
        ServicePreparationItem._base_manager.bulk_create(items)
    return list(
        ServicePreparationItem._base_manager.filter(service_id=plan.pk, space_id=plan.space_id)
        .order_by("position", "pk")
    )


def service_log_revision(plan: ServicePlan) -> int:
    content_type = ContentType.objects.get_for_model(ServicePlan)
    return (
        LogEntry.objects.filter(content_type=content_type, object_id=str(plan.pk))
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )


def preparation_revision(plan: ServicePlan, items: list[ServicePreparationItem]) -> str:
    envelope = {
        "service_id": plan.pk,
        "state": plan.state,
        "confirmed_at": plan.confirmed_at.isoformat() if plan.confirmed_at else None,
        "latest_service_log": service_log_revision(plan),
        "items": [{
            "id": item.pk,
            "source_step_id": item.source_step_id,
            "task_key": item.task_key,
            "position": item.position,
            "recipe_id": item.recipe_id_snapshot,
            "name": item.name,
            "instruction": item.instruction,
            "checked": item.checked,
            "checked_at": item.checked_at.isoformat() if item.checked_at else None,
            "updated_by": item.updated_by_id,
            "updated_at": item.updated_at.isoformat(),
        } for item in items],
    }
    encoded = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preparation_payload(plan: ServicePlan, items: list[ServicePreparationItem]) -> dict:
    return {
        "service_id": plan.pk,
        "state": plan.state,
        "can_edit": plan.state == ServicePlan.CONFIRMED and bool(items),
        "revision": preparation_revision(plan, items),
        "items": [{
            "id": item.pk,
            "source_step_id": item.source_step_id,
            "position": item.position,
            "recipe_id": item.recipe_id_snapshot,
            "name": item.name,
            "instruction": item.instruction,
            "checked": item.checked,
            "checked_at": item.checked_at.isoformat() if item.checked_at else None,
            "updated_by": item.updated_by_id,
        } for item in items],
    }
