#!/usr/bin/env python3
"""Release HTTP smoke for persistent service preparation checklists."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _decimal, _guard_base_url, _guard_environment, _items
    from .release_reserves_smoke import _positive_id, _snapshot
    from .release_yields_smoke import _active_space, _demo_recipe
else:
    from release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _decimal, _guard_base_url, _guard_environment, _items
    from release_reserves_smoke import _positive_id, _snapshot
    from release_yields_smoke import _active_space, _demo_recipe


ACCOUNT_PREFIX = "demo-"
SERVICE_TITLE = "Preparación HTTP DEMO"
SERVICE_DATE = "2026-10-25"
SERVICE_COVERS = Decimal("4")
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
ITEM_KEYS = {
    "id", "source_step_id", "position", "recipe_id", "name", "instruction",
    "checked", "checked_at", "updated_by",
}
PREPARATION_KEYS = {"service_id", "state", "can_edit", "revision", "items"}
INVENTORY_PATH = "/api/inventory-entry/?" + urlencode({"page_size": "100"})


def _aware_timestamp(value, label: str) -> str:
    if not isinstance(value, str):
        raise SmokeFailure(f"{label} no devolvió fecha textual.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SmokeFailure(f"{label} no devolvió una fecha ISO válida.") from exc
    if parsed.utcoffset() is None:
        raise SmokeFailure(f"{label} no incluye zona horaria.")
    return value


def _preparation_path(service_id: int) -> str:
    service_id = _positive_id(service_id, "service.id")
    return f"/api/cuaderno/services/{service_id}/preparation/"


def _preparation_payload(payload, service_id: int, *, checked: bool | None = None) -> tuple[str, list[dict]]:
    service_id = _positive_id(service_id, "service.id")
    if not isinstance(payload, dict) or set(payload) != PREPARATION_KEYS:
        raise SmokeFailure("Preparación no devolvió el sobre completo y conocido.")
    if (
        _positive_id(payload.get("service_id"), "preparation.service_id") != service_id
        or payload.get("state") != "confirmed"
        or payload.get("can_edit") is not True
    ):
        raise SmokeFailure("Preparación no corresponde al servicio confirmado editable.")
    revision = payload.get("revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise SmokeFailure("Preparación no devolvió una revisión SHA-256 canónica.")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise SmokeFailure("Salsa DEMO debe congelar al menos un paso de preparación.")
    identifiers = []
    for position, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            raise SmokeFailure("Un paso de preparación tiene campos incompletos o desconocidos.")
        identifiers.append(_positive_id(item.get("id"), "preparation.item.id"))
        _positive_id(item.get("source_step_id"), "preparation.item.source_step_id")
        _positive_id(item.get("recipe_id"), "preparation.item.recipe_id")
        if (
            type(item.get("position")) is not int
            or item["position"] != position
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("instruction"), str)
        ):
            raise SmokeFailure("El paso congelado perdió posición o texto nativo.")
        if type(item.get("checked")) is not bool:
            raise SmokeFailure("El estado checked no es booleano estricto.")
        if checked is not None and item["checked"] is not checked:
            raise SmokeFailure("El checklist no conserva el estado checked esperado.")
        if item["checked"]:
            _aware_timestamp(item.get("checked_at"), "preparation.checked_at")
            _positive_id(item.get("updated_by"), "preparation.updated_by")
        elif item.get("checked_at") is not None:
            raise SmokeFailure("Un paso desmarcado conserva checked_at.")
        elif item.get("updated_by") is not None:
            _positive_id(item.get("updated_by"), "preparation.updated_by")
    if len(identifiers) != len(set(identifiers)):
        raise SmokeFailure("Preparación devolvió identificadores duplicados.")
    return revision, items


def _frozen_signature(items: list[dict]) -> tuple[tuple, ...]:
    return tuple((
        item["id"], item["source_step_id"], item["position"], item["recipe_id"],
        item["name"], item["instruction"],
    ) for item in items)


def _assert_frozen_signature(items: list[dict], expected: tuple[tuple, ...]) -> None:
    if _frozen_signature(items) != expected:
        raise SmokeFailure("Los pasos congelados cambiaron durante la edición; no se sobrescriben.")


def _non_target_state(items: list[dict], target_id: int) -> tuple[tuple, ...]:
    return tuple(
        (item["id"], item["checked"], item["checked_at"], item["updated_by"])
        for item in items if item["id"] != target_id
    )


def _assert_non_target_state(items: list[dict], target_id: int, expected: tuple[tuple, ...]) -> None:
    if _non_target_state(items, target_id) != expected:
        raise SmokeFailure("Otro paso cambió estado, fecha o autor; no se sobrescribe el objetivo.")


def _target_item(items: list[dict], item_id: int) -> dict:
    item = next((row for row in items if row["id"] == item_id), None)
    if item is None:
        raise SmokeFailure("El paso propio desapareció durante el smoke.")
    return item


def _assert_all_unchecked(items: list[dict]) -> None:
    if any(item["checked"] is not False or item["checked_at"] is not None for item in items):
        raise SmokeFailure("El checklist no quedó completamente desmarcado.")


def _service_rows(session: HttpSession) -> list[dict]:
    payload = session.json("GET", "/api/cuaderno/services/", csrf=False)
    if not isinstance(payload, list) or len(payload) >= 100 or any(not isinstance(row, dict) for row in payload):
        raise SmokeFailure("La lista de servicios es ambigua, está truncada o contiene filas inválidas.")
    identifiers = [_positive_id(row.get("id"), "service.id") for row in payload]
    if len(identifiers) != len(set(identifiers)):
        raise SmokeFailure("La lista de servicios contiene identificadores duplicados.")
    return payload


def _confirmed_snapshot(rows: list[dict]) -> dict[int, dict]:
    return {row["id"]: row for row in rows if row.get("state") == "confirmed"}


def _assert_previous_services(previous: dict[int, dict], current_rows: list[dict]) -> None:
    current = {row["id"]: row for row in current_rows}
    for service_id, frozen in previous.items():
        if current.get(service_id) != frozen:
            raise SmokeFailure("El smoke alteró un servicio que ya estaba confirmado.")


def _inventory_amount_rows(session: HttpSession) -> list[tuple[int, str]]:
    rows = _items(_snapshot(session, INVENTORY_PATH))
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise SmokeFailure("Inventario devolvió una fila inválida.")
        identifier = _positive_id(row.get("id"), "inventory.id")
        amount = _decimal(row.get("amount"), "inventory.amount")
        result.append((identifier, format(amount, "f")))
    return sorted(result)


def _service_detail(payload, service_id: int, recipe_id: int) -> dict:
    service_id = _positive_id(service_id, "service.id")
    recipe_id = _positive_id(recipe_id, "recipe.id")
    if not isinstance(payload, dict) or _positive_id(payload.get("id"), "service.id") != service_id:
        raise SmokeFailure("El servicio no devolvió su detalle completo.")
    if (
        payload.get("title") != SERVICE_TITLE
        or payload.get("service_date") != SERVICE_DATE
        or payload.get("state") != "confirmed"
        or _decimal(payload.get("covers"), "service.covers") != SERVICE_COVERS
    ):
        raise SmokeFailure("El servicio reservado no coincide con el fixture HTTP exacto.")
    snapshot = payload.get("snapshot")
    if (
        not isinstance(snapshot, dict)
        or _positive_id(snapshot.get("recipe_id"), "snapshot.recipe_id") != recipe_id
    ):
        raise SmokeFailure("El servicio no congeló Salsa DEMO.")
    return payload


def _find_or_create_service(session: HttpSession, recipe_id: int) -> tuple[dict, bool, dict[int, dict]]:
    rows = _service_rows(session)
    previous = _confirmed_snapshot(rows)
    matches = [row for row in rows if row.get("title") == SERVICE_TITLE]
    if len(matches) > 1:
        raise SmokeFailure("Existe más de un servicio con el título reservado del smoke.")
    created = False
    if matches:
        service_id = _positive_id(matches[0].get("id"), "service.id")
    else:
        created_payload = session.json(
            "POST", "/api/cuaderno/services/",
            payload={
                "recipe": recipe_id,
                "covers": "4",
                "service_date": SERVICE_DATE,
                "title": SERVICE_TITLE,
            },
            expected=(201,),
        )
        if not isinstance(created_payload, dict):
            raise SmokeFailure("Crear servicio no devolvió un objeto JSON.")
        service_id = _positive_id(created_payload.get("id"), "service.id")
        created = True
    detail_path = f"/api/cuaderno/services/{service_id}/"
    detail = session.json("GET", detail_path, csrf=False)
    if not isinstance(detail, dict):
        raise SmokeFailure("El detalle del servicio no devolvió un objeto JSON.")
    if detail.get("state") == "draft":
        if not created:
            raise SmokeFailure("El servicio reservado ya existía en borrador; no se confirma un estado ajeno.")
        detail = session.json("POST", detail_path, payload={"action": "confirm"})
    return _service_detail(detail, service_id, recipe_id), created, previous


def _write_body(item_id: int, checked: bool, revision: str) -> dict:
    return {"item": _positive_id(item_id, "preparation.item.id"), "checked": checked, "revision": revision}


def _restore_original(
    session: HttpSession,
    path: str,
    service_id: int,
    *,
    item_id: int,
    expected_revision: str | None,
    expected_signature: tuple[tuple, ...],
    expected_non_target_state: tuple[tuple, ...],
) -> str:
    fresh = session.json("GET", path, csrf=False)
    revision, items = _preparation_payload(fresh, service_id)
    _assert_frozen_signature(items, expected_signature)
    _assert_non_target_state(items, item_id, expected_non_target_state)
    item = _target_item(items, item_id)
    if item["checked"] is False:
        _assert_all_unchecked(items)
        return revision
    if expected_revision is None or revision != expected_revision:
        raise SmokeFailure("La revisión de recuperación no pertenece a este smoke; no se sobrescribe.")
    restored = session.json("PUT", path, payload=_write_body(item_id, False, revision))
    restored_revision, restored_items = _preparation_payload(restored, service_id)
    _assert_frozen_signature(restored_items, expected_signature)
    _assert_non_target_state(restored_items, item_id, expected_non_target_state)
    restored_item = _target_item(restored_items, item_id)
    if restored_item["checked"] is not False or restored_item["checked_at"] is not None:
        raise SmokeFailure("La recuperación CAS no restauró el estado desmarcado.")
    return restored_revision


def _exercise_preparation(session: HttpSession, detail: dict) -> dict:
    service_id = detail["id"]
    path = _preparation_path(service_id)
    original = session.json("GET", path, csrf=False)
    revision_a, items_a = _preparation_payload(original, service_id, checked=False)
    frozen_signature = _frozen_signature(items_a)
    item_id = items_a[0]["id"]
    non_target_state = _non_target_state(items_a, item_id)
    body_b = _write_body(item_id, True, revision_a)

    missing = dict(body_b)
    del missing["revision"]
    session.request("PUT", path, payload=missing, expected=(428,))
    session.request("PUT", path, payload=body_b, csrf=False, expected=(403,))
    if session.json("GET", path, csrf=False) != original:
        raise SmokeFailure("Una escritura rechazada alteró la preparación.")

    noop = session.json("PUT", path, payload=_write_body(item_id, False, revision_a))
    if noop != original:
        raise SmokeFailure("Un no-op alteró revisión, autor, fecha o contenido.")

    revision_b = None
    revision_c = None
    try:
        checked = session.json("PUT", path, payload=body_b)
        revision_b, items_b = _preparation_payload(checked, service_id)
        _assert_frozen_signature(items_b, frozen_signature)
        _assert_non_target_state(items_b, item_id, non_target_state)
        checked_item = _target_item(items_b, item_id)
        if checked_item["checked"] is not True:
            raise SmokeFailure("Marcar preparación no persistió checked=true.")
        actor_id = _positive_id(checked_item.get("updated_by"), "preparation.updated_by")
        _aware_timestamp(checked_item.get("checked_at"), "preparation.checked_at")
        session.request("PUT", path, payload=_write_body(item_id, False, revision_a), expected=(409,))
        checked_reread = session.json("GET", path, csrf=False)
        _, checked_reread_items = _preparation_payload(checked_reread, service_id)
        _assert_frozen_signature(checked_reread_items, frozen_signature)
        _assert_non_target_state(checked_reread_items, item_id, non_target_state)
        if checked_reread != checked:
            raise SmokeFailure("El conflicto stale alteró la preparación marcada.")

        unchecked = session.json("PUT", path, payload=_write_body(item_id, False, revision_b))
        revision_c, items_c = _preparation_payload(unchecked, service_id)
        _assert_frozen_signature(items_c, frozen_signature)
        _assert_non_target_state(items_c, item_id, non_target_state)
        _assert_all_unchecked(items_c)
        unchecked_item = _target_item(items_c, item_id)
        if (
            unchecked_item["checked"] is not False
            or unchecked_item["checked_at"] is not None
            or unchecked_item.get("updated_by") != actor_id
        ):
            raise SmokeFailure("Desmarcar no conservó autor ni limpió checked_at.")
        unchecked_reread = session.json("GET", path, csrf=False)
        _, unchecked_reread_items = _preparation_payload(unchecked_reread, service_id)
        _assert_frozen_signature(unchecked_reread_items, frozen_signature)
        _assert_non_target_state(unchecked_reread_items, item_id, non_target_state)
        _assert_all_unchecked(unchecked_reread_items)
        if unchecked_reread != unchecked:
            raise SmokeFailure("La preparación desmarcada no persistió al releer.")
    finally:
        recovered = _restore_original(
            session, path, service_id, item_id=item_id, expected_revision=revision_b,
            expected_signature=frozen_signature,
            expected_non_target_state=non_target_state,
        )
        if revision_c is None:
            revision_c = recovered

    if revision_b is None or revision_c is None or len({revision_a, revision_b, revision_c}) != 3:
        raise SmokeFailure("El ciclo A-B-A no produjo tres revisiones distintas.")
    final_payload = session.json("GET", path, csrf=False)
    _, final_items = _preparation_payload(final_payload, service_id)
    _assert_frozen_signature(final_items, frozen_signature)
    _assert_non_target_state(final_items, item_id, non_target_state)
    _assert_all_unchecked(final_items)
    if _target_item(final_items, item_id).get("updated_by") != actor_id:
        raise SmokeFailure("El autor del item objetivo no persistió tras desmarcarlo.")
    return {
        "service_id": service_id,
        "items": len(items_a),
        "checklist_writes": 2,
        "rejected_writes": 3,
        "checked_state_restored": True,
    }


def _check_editable_account(edition: str, title: str, password: str) -> tuple[dict, int]:
    session = HttpSession()
    session.login(f"{ACCOUNT_PREFIX}{edition}", password)
    _active_space(session, edition, title)
    recipe_id = _demo_recipe(session)
    inventory_before = _inventory_amount_rows(session)
    detail, created, previous = _find_or_create_service(session, recipe_id)
    snapshot_before = json.dumps(detail["snapshot"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = _exercise_preparation(session, detail)
    reread_detail = _service_detail(
        session.json("GET", f"/api/cuaderno/services/{detail['id']}/", csrf=False),
        detail["id"], recipe_id,
    )
    if json.dumps(reread_detail["snapshot"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) != snapshot_before:
        raise SmokeFailure("Editar preparación alteró el snapshot congelado del servicio.")
    if _inventory_amount_rows(session) != inventory_before:
        raise SmokeFailure("Editar preparación alteró saldos del inventario nativo.")
    _assert_previous_services(previous, _service_rows(session))
    session.logout()
    return {
        **result,
        "service_created": created,
        "service_confirmed": created,
        "snapshot_unchanged": True,
        "inventory_amounts_unchanged": True,
        "previous_confirmed_services_unchanged": True,
    }, detail["id"]


def _check_essential_isolation(password: str, foreign_service_ids: list[int]) -> dict:
    session = HttpSession()
    session.login("demo-esencial", password)
    _active_space(session, "esencial", EDITIONS["esencial"])
    for service_id in foreign_service_ids:
        service_id = _positive_id(service_id, "foreign_service.id")
        session.request("GET", f"/api/cuaderno/services/{service_id}/", csrf=False, expected=(403, 404))
        session.request("GET", _preparation_path(service_id), csrf=False, expected=(403, 404))
    session.logout()
    return {"foreign_services_denied": len(foreign_service_ids), "writes": 0}


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")

    editions = {}
    foreign_ids = []
    for edition in ("profesional", "integral"):
        result, service_id = _check_editable_account(edition, EDITIONS[edition], password)
        editions[edition] = result
        foreign_ids.append(service_id)
    editions["esencial"] = _check_essential_isolation(password, foreign_ids)
    created = sum(bool(row.get("service_created")) for row in editions.values())
    confirmed = sum(bool(row.get("service_confirmed")) for row in editions.values())
    checklist_writes = sum(row.get("checklist_writes", 0) for row in editions.values())
    return {
        "ready": True,
        "accounts_checked": len(editions),
        "services_created": created,
        "services_confirmed": confirmed,
        "checklist_writes": checklist_writes,
        "persistent_mutation": True,
        "services_retained": True,
        "audit_verified_over_http": False,
        "editions": editions,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_PREPARATION_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_PREPARATION_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
