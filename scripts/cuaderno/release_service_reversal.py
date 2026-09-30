#!/usr/bin/env python3
"""Smoke HTTP de producción y reversión completa sobre la DEMO local."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment, _items
    from .release_reserves_smoke import _demo_package, _positive_id, _snapshot
    from .release_waste_smoke import _assert_added_only, _movement_rows
    from .release_yields_smoke import _active_space, _demo_recipe
else:
    from release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment, _items
    from release_reserves_smoke import _demo_package, _positive_id, _snapshot
    from release_waste_smoke import _assert_added_only, _movement_rows
    from release_yields_smoke import _active_space, _demo_recipe


SERVICE_TITLE = "Verificación reversión"
SERVICE_DATE = "2026-10-25"
SERVICE_COVERS = Decimal("4")
INVENTORY_PATH = "/api/inventory-entry/?" + urlencode({"page_size": "100", "empty": "true"})
MOVEMENTS_PATH = "/api/cuaderno/movements/"
PRODUCTION_KEYS = {
    "profesional": "release-service-production-profesional-v1",
    "integral": "release-service-production-integral-v1",
}
REVERSAL_KEYS = {
    "profesional": "release-service-reversal-profesional-v1",
    "integral": "release-service-reversal-integral-v1",
}
AUDIT_KEYS = {"key_sha256", "reversed_at", "reversed_by", "original_movement_ids", "movement_ids"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _fixed_decimal(value, label: str) -> Decimal:
    if not isinstance(value, str) or len(value) > 96:
        raise SmokeFailure(f"{label} no llegó como decimal textual acotado.")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SmokeFailure(f"{label} no es un decimal válido.") from exc
    if not result.is_finite():
        raise SmokeFailure(f"{label} no es finito.")
    return result


def _native_decimal(value, label: str) -> Decimal:
    if type(value) not in (int, float):
        raise SmokeFailure(f"{label} no es un número JSON nativo.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise SmokeFailure(f"{label} no es decimal finito.") from exc
    if not result.is_finite():
        raise SmokeFailure(f"{label} no es finito.")
    return result


def _aware(value, label: str) -> None:
    if not isinstance(value, str):
        raise SmokeFailure(f"{label} no es una fecha textual.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SmokeFailure(f"{label} no es una fecha ISO válida.") from exc
    if parsed.utcoffset() is None:
        raise SmokeFailure(f"{label} no incluye zona horaria.")


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _service_rows(session: HttpSession) -> list[dict]:
    payload = session.json("GET", "/api/cuaderno/services/", csrf=False)
    if not isinstance(payload, list) or len(payload) >= 100 or any(not isinstance(row, dict) for row in payload):
        raise SmokeFailure("La lista completa de servicios es inválida o está truncada.")
    ids = [_positive_id(row.get("id"), "service.id") for row in payload]
    if len(ids) != len(set(ids)):
        raise SmokeFailure("La lista de servicios contiene identificadores duplicados.")
    return payload


def _service_detail(payload, service_id: int, recipe_id: int) -> dict:
    if not isinstance(payload, dict) or _positive_id(payload.get("id"), "service.id") != service_id:
        raise SmokeFailure("El detalle no corresponde al servicio reservado.")
    if (
        payload.get("title") != SERVICE_TITLE
        or payload.get("service_date") != SERVICE_DATE
        or _fixed_decimal(payload.get("covers"), "service.covers") != SERVICE_COVERS
        or payload.get("state") not in {"draft", "confirmed", "produced", "cancelled"}
    ):
        raise SmokeFailure("El servicio reservado no conserva título, fecha o comensales exactos.")
    snapshot = payload.get("snapshot")
    if payload["state"] != "draft" and (
        not isinstance(snapshot, dict) or _positive_id(snapshot.get("recipe_id"), "snapshot.recipe_id") != recipe_id
    ):
        raise SmokeFailure("El servicio no congeló Salsa DEMO.")
    _positive_id(payload.get("created_by"), "service.created_by")
    return payload


def _assert_initial_stock(edition: str, stock: Decimal, state: str) -> None:
    expected = Decimal("4.6") if edition == "integral" and state == "produced" else Decimal("5")
    if stock != expected:
        raise SmokeFailure("La existencia DEMO no coincide con el estado inicial; no se permite ningún POST.")


def _persisted_service(payload: dict) -> dict:
    """Action responses add ephemeral IDs/flags absent from detail GET."""
    result = dict(payload)
    for field in ("movement_ids", "reversal_movement_ids", "stock_changed"):
        result.pop(field, None)
    return result


def _find_or_create_service(session: HttpSession, recipe_id: int, *, edition: str, stock_initial: Decimal) -> tuple[dict, bool]:
    matches = [row for row in _service_rows(session) if row.get("title") == SERVICE_TITLE]
    if len(matches) > 1:
        raise SmokeFailure("Hay más de un servicio con el título reservado.")
    created = not matches
    if created:
        _assert_initial_stock(edition, stock_initial, "draft")
        row = session.json(
            "POST", "/api/cuaderno/services/",
            payload={"recipe": recipe_id, "covers": "4", "service_date": SERVICE_DATE, "title": SERVICE_TITLE},
            expected=(201,),
        )
        if not isinstance(row, dict):
            raise SmokeFailure("Crear servicio no devolvió un objeto.")
        service_id = _positive_id(row.get("id"), "service.id")
    else:
        service_id = _positive_id(matches[0].get("id"), "service.id")
    path = f"/api/cuaderno/services/{service_id}/"
    detail = session.json("GET", path, csrf=False)
    if not isinstance(detail, dict):
        raise SmokeFailure("El detalle del servicio no es un objeto.")
    # Preflight is read-only for existing documents. A preexisting draft does
    # not expose its recipe in the frozen snapshot: never guess its identity.
    _service_detail(detail, service_id, recipe_id)
    if detail["state"] == "draft" and not created:
        raise SmokeFailure("Hay un borrador reservado sin receta verificable; no se confirma ni modifica.")
    _assert_initial_stock(edition, stock_initial, detail["state"])
    if detail.get("state") == "draft":
        detail = session.json("POST", path, payload={"action": "confirm"})
    return _service_detail(detail, service_id, recipe_id), created


def _production_document(payload: dict, service_id: int, edition: str) -> tuple[dict, list[int]]:
    payload = _service_detail(payload, service_id, _positive_id(payload.get("snapshot", {}).get("recipe_id"), "snapshot.recipe_id"))
    if payload.get("state") not in {"produced", "cancelled"}:
        raise SmokeFailure("El servicio no está producido ni revertido.")
    production = payload["snapshot"].get("production")
    if not isinstance(production, dict):
        raise SmokeFailure("Falta el documento de producción congelado.")
    expected_base = {"produced_at", "edition", "movement_ids", "stock_changed"}
    if set(production) not in (expected_base, expected_base | {"reversal"}):
        raise SmokeFailure("Producción contiene campos desconocidos o incompletos.")
    _aware(production.get("produced_at"), "production.produced_at")
    ids = production.get("movement_ids")
    if not isinstance(ids, list) or any(type(pk) is not int or pk <= 0 for pk in ids) or len(ids) != len(set(ids)):
        raise SmokeFailure("Los movimientos originales no son identificadores únicos.")
    expected_stock = edition == "integral"
    if production.get("edition") != edition or production.get("stock_changed") is not expected_stock:
        raise SmokeFailure("La producción no respeta la política de la edición.")
    if (expected_stock and not ids) or (not expected_stock and ids):
        raise SmokeFailure("La producción y sus movimientos son incoherentes.")
    return production, ids


def _validate_reversal(
    payload: dict, *, service_id: int, recipe_id: int, edition: str,
    produced_snapshot: dict, reversal_key: str,
) -> list[int]:
    detail = _service_detail(payload, service_id, recipe_id)
    if detail.get("state") != "cancelled":
        raise SmokeFailure("La reversión no dejó el servicio cancelado.")
    production, original_ids = _production_document(detail, service_id, edition)
    audit = production.get("reversal")
    if not isinstance(audit, dict) or set(audit) != AUDIT_KEYS:
        raise SmokeFailure("La reversión no añadió el audit exacto de cinco campos.")
    expected_key_hash = hashlib.sha256(reversal_key.encode("utf-8")).hexdigest()
    if (
        not isinstance(audit.get("key_sha256"), str)
        or SHA256_RE.fullmatch(audit["key_sha256"]) is None
        or audit["key_sha256"] != expected_key_hash
    ):
        raise SmokeFailure("La reversión no congeló una huella SHA-256 canónica.")
    _aware(audit.get("reversed_at"), "reversal.reversed_at")
    if _positive_id(audit.get("reversed_by"), "reversal.reversed_by") != detail["created_by"]:
        raise SmokeFailure("El actor de reversión no coincide con la cuenta propietaria DEMO.")
    reversal_ids = audit.get("movement_ids")
    if (
        audit.get("original_movement_ids") != original_ids
        or not isinstance(reversal_ids, list)
        or any(type(pk) is not int or pk <= 0 for pk in reversal_ids)
        or len(reversal_ids) != len(set(reversal_ids))
        or set(reversal_ids) & set(original_ids)
        or payload.get("reversal_movement_ids") != reversal_ids
        or type(payload.get("stock_changed")) is not bool
        or payload["stock_changed"] is not (edition == "integral")
    ):
        raise SmokeFailure("La respuesta de reversión no corresponde a sus movimientos y edición.")
    if (edition == "integral" and len(reversal_ids) != len(original_ids)) or (edition == "profesional" and reversal_ids):
        raise SmokeFailure("La reversión no compensó exactamente la producción.")
    without_audit = deepcopy(detail["snapshot"])
    del without_audit["production"]["reversal"]
    if without_audit != produced_snapshot:
        raise SmokeFailure("La reversión alteró el snapshot producido en vez de anexar audit.")
    return reversal_ids


def _inventory_amount(session: HttpSession, package: dict) -> tuple[dict, Decimal]:
    snapshot = _snapshot(session, INVENTORY_PATH)
    matches = []
    for row in _items(snapshot):
        if not isinstance(row, dict):
            continue
        food = row.get("food")
        unit = row.get("unit")
        location = row.get("inventory_location")
        household = location.get("household") if isinstance(location, dict) else None
        if (
            isinstance(food, dict) and food.get("id") == package.get("food") and food.get("name") == "Aceite DEMO"
            and isinstance(unit, dict) and unit.get("id") == package.get("unit") and unit.get("name") == "L"
            and isinstance(household, dict) and type(household.get("id")) is int and household["id"] > 0
        ):
            matches.append(row)
    if len(matches) != 1:
        raise SmokeFailure("La existencia Aceite DEMO/L no es unívoca en el hogar activo.")
    entry = matches[0]
    _positive_id(entry.get("id"), "inventory.entry")
    return snapshot, _native_decimal(entry.get("amount"), "inventory.amount")


def _service_movements(rows: list[dict], service_id: int) -> list[dict]:
    result = []
    for row in _movement_rows(rows):
        metadata = row.get("metadata_snapshot")
        origin = metadata.get("origin") if isinstance(metadata, dict) else None
        if isinstance(origin, dict) and origin.get("type") == "service_plan" and origin.get("id") == service_id:
            result.append(row)
    return result


def _validate_integral_movements(rows: list[dict], *, service_id: int, original_ids: list[int], reversal_ids: list[int]) -> None:
    owned = _service_movements(rows, service_id)
    by_id = {row["id"]: row for row in owned}
    if set(by_id) != set(original_ids) | set(reversal_ids):
        raise SmokeFailure("El historial del servicio tiene movimientos ajenos, ausentes o duplicados.")
    if len(original_ids) != 1 or len(reversal_ids) != 1:
        raise SmokeFailure("Salsa DEMO debe consumir y restaurar una única existencia.")
    original = by_id[original_ids[0]]
    reversal = by_id[reversal_ids[0]]
    if (
        original.get("kind") != "consume"
        or original.get("reverses") is not None
        or _fixed_decimal(original.get("quantity"), "consume.quantity") != Decimal("0.4")
        or reversal.get("kind") != "receipt"
        or reversal.get("reverses") != original_ids[0]
        or _fixed_decimal(reversal.get("quantity"), "reversal.quantity") != Decimal("0.4")
    ):
        raise SmokeFailure("El ledger no refleja 400 mL como 0.4 L consumidos y restaurados.")


def _post_transition(session: HttpSession, service_id: int, action: str, key: str, **kwargs):
    return session.json(
        "POST", f"/api/cuaderno/services/{service_id}/",
        payload={"action": action, "idempotency_key": key}, **kwargs,
    )


def _exercise_account(edition: str, password: str) -> tuple[dict, HttpSession]:
    session = HttpSession()
    session.login(f"demo-{edition}", password)
    _active_space(session, edition, EDITIONS[edition])
    recipe_id = _demo_recipe(session)
    package = _demo_package(session)
    inventory_initial, stock_initial = _inventory_amount(session, package)
    detail, created = _find_or_create_service(session, recipe_id, edition=edition, stock_initial=stock_initial)
    initial_state = detail["state"]
    service_id = detail["id"]
    path = f"/api/cuaderno/services/{service_id}/"
    production_key = PRODUCTION_KEYS[edition]
    reversal_key = REVERSAL_KEYS[edition]
    confirmed_snapshot = deepcopy(detail["snapshot"]) if detail["state"] == "confirmed" else None

    if detail["state"] == "confirmed":
        before_denied = session.json("GET", path, csrf=False)
        session.request(
            "POST", path, payload={"action": "produce", "idempotency_key": production_key},
            csrf=False, expected=(403,),
        )
        if session.json("GET", path, csrf=False) != before_denied:
            raise SmokeFailure("Producir sin CSRF alteró el servicio.")
        detail = _post_transition(session, service_id, "produce", production_key)

    if detail["state"] == "produced":
        production, original_ids = _production_document(detail, service_id, edition)
        produced_snapshot = deepcopy(detail["snapshot"])
        if confirmed_snapshot is not None:
            without_production = deepcopy(produced_snapshot)
            without_production.pop("production", None)
            if without_production != confirmed_snapshot:
                raise SmokeFailure("Producir alteró el snapshot confirmado en vez de anexar producción.")
        replay_production = _post_transition(session, service_id, "produce", production_key)
        replay_document, replay_ids = _production_document(replay_production, service_id, edition)
        if replay_ids != original_ids or replay_document != production:
            raise SmokeFailure("Repetir producción con la misma clave no fue idempotente.")
        session.request(
            "POST", path,
            payload={"action": "produce", "idempotency_key": production_key + "-distinta"},
            expected=(409,),
        )
        if session.json("GET", path, csrf=False) != _persisted_service(replay_production):
            raise SmokeFailure("El conflicto de producción alteró el servicio.")

        if edition == "integral":
            _, stock_produced = _inventory_amount(session, package)
            expected_initial = Decimal("4.6") if initial_state == "produced" else Decimal("5")
            if stock_initial != expected_initial or stock_produced != Decimal("4.6"):
                raise SmokeFailure("Integral no pasó exactamente de 5 L a 4.6 L.")
            movements_before_reverse = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
        else:
            if _inventory_amount(session, package) != (inventory_initial, stock_initial):
                raise SmokeFailure("Profesional modificó el inventario al producir.")
            movements_before_reverse = []

        before_denied = session.json("GET", path, csrf=False)
        session.request(
            "POST", path, payload={"action": "reverse", "idempotency_key": reversal_key},
            csrf=False, expected=(403,),
        )
        if session.json("GET", path, csrf=False) != before_denied:
            raise SmokeFailure("Revertir sin CSRF alteró el servicio.")
        detail = _post_transition(session, service_id, "reverse", reversal_key)
    elif detail["state"] == "cancelled":
        production, original_ids = _production_document(detail, service_id, edition)
        produced_snapshot = deepcopy(detail["snapshot"])
        produced_snapshot["production"].pop("reversal", None)
        movements_before_reverse = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False)) if edition == "integral" else []
        session.request(
            "POST", path, payload={"action": "reverse", "idempotency_key": reversal_key},
            csrf=False, expected=(403,),
        )
        if session.json("GET", path, csrf=False) != detail:
            raise SmokeFailure("Repetir reversión sin CSRF alteró el servicio cancelado.")
        detail = _post_transition(session, service_id, "reverse", reversal_key)
    else:
        raise SmokeFailure("El servicio reservado tiene un estado no recuperable por este smoke.")

    reversal_ids = _validate_reversal(
        detail, service_id=service_id, recipe_id=recipe_id, edition=edition,
        produced_snapshot=produced_snapshot, reversal_key=reversal_key,
    )
    transition_response = detail
    after_first = session.json("GET", path, csrf=False)
    serialized_transition = _persisted_service(transition_response)
    if serialized_transition != after_first:
        raise SmokeFailure("La respuesta de reversión no coincide con el servicio persistido.")
    movement_state = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False)) if edition == "integral" else []
    replay = _post_transition(session, service_id, "reverse", reversal_key)
    if replay != transition_response or _validate_reversal(
        replay, service_id=service_id, recipe_id=recipe_id, edition=edition,
        produced_snapshot=produced_snapshot, reversal_key=reversal_key,
    ) != reversal_ids:
        raise SmokeFailure("Repetir la reversión no devolvió el mismo documento.")
    session.request(
        "POST", path, payload={"action": "reverse", "idempotency_key": reversal_key + "-distinta"}, expected=(409,),
    )
    if session.json("GET", path, csrf=False) != after_first:
        raise SmokeFailure("El conflicto de reversión alteró el servicio.")

    inventory_final, stock_final = _inventory_amount(session, package)
    if stock_final != Decimal("5"):
        raise SmokeFailure("La reversión no dejó la existencia DEMO en 5 L.")
    if edition == "integral":
        final_movements = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
        if final_movements != movement_state:
            raise SmokeFailure("Repetir o provocar conflicto creó movimientos adicionales.")
        _assert_added_only(movements_before_reverse, final_movements, set(reversal_ids))
        _validate_integral_movements(
            final_movements, service_id=service_id, original_ids=original_ids, reversal_ids=reversal_ids,
        )
    elif original_ids or reversal_ids or inventory_final != inventory_initial:
        raise SmokeFailure("Profesional tocó stock o generó movimientos de producción.")

    return {
        "service_id": service_id,
        "service_created": created,
        "state": "cancelled",
        "production_movement_ids": original_ids,
        "reversal_movement_ids": reversal_ids,
        "stock_restored": True,
        "replay_verified": True,
        "conflict_verified": True,
        "csrf_verified": True,
    }, session


def _assert_denied(session: HttpSession, service_id: int, key: str) -> None:
    path = f"/api/cuaderno/services/{_positive_id(service_id, 'foreign_service.id')}/"
    status, _, body = session.request("GET", path, csrf=False, expected=(403, 404))
    leak_marker = b"Verificaci"
    if status not in (403, 404) or leak_marker in body:
        raise SmokeFailure("El acceso ajeno filtró el servicio reservado.")
    status, _, body = session.request(
        "POST", path, payload={"action": "reverse", "idempotency_key": key}, expected=(403, 404),
    )
    if status not in (403, 404) or leak_marker in body:
        raise SmokeFailure("La reversión ajena filtró el servicio reservado.")


def _check_isolation(password: str, owners: dict[str, tuple[dict, HttpSession]]) -> dict:
    before = {
        edition: owner.json("GET", f"/api/cuaderno/services/{result['service_id']}/", csrf=False)
        for edition, (result, owner) in owners.items()
    }
    for edition, (result, attacker) in owners.items():
        other = "integral" if edition == "profesional" else "profesional"
        _assert_denied(attacker, owners[other][0]["service_id"], f"cross-space-{edition}-v1")
    essential = HttpSession()
    essential.login("demo-esencial", password)
    _active_space(essential, "esencial", EDITIONS["esencial"])
    essential.request("GET", "/api/cuaderno/services/", csrf=False, expected=(403,))
    for edition, (result, _) in owners.items():
        _assert_denied(essential, result["service_id"], f"essential-{edition}-v1")
    essential.logout()
    for edition, (result, owner) in owners.items():
        current = owner.json("GET", f"/api/cuaderno/services/{result['service_id']}/", csrf=False)
        if current != before[edition]:
            raise SmokeFailure("Una prueba de aislamiento alteró el servicio propietario.")
    return {"essential_denied": 2, "cross_space_denied": 2, "writes": 0}


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    owners = {edition: _exercise_account(edition, password) for edition in ("profesional", "integral")}
    isolation = _check_isolation(password, owners)
    results = {edition: result for edition, (result, _) in owners.items()}
    for _, session in owners.values():
        session.logout()
    return {
        "ready": True,
        "accounts_checked": 3,
        "persistent_mutation": True,
        "services_retained": True,
        "editions": results,
        "isolation": isolation,
        "evidence_digest": hashlib.sha256(_canonical(results).encode("utf-8")).hexdigest(),
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_SERVICE_REVERSAL ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_SERVICE_REVERSAL " + _canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
