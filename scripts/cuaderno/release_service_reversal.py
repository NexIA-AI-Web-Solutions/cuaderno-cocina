#!/usr/bin/env python3
"""Smoke HTTP de producción y reversión completa sobre la DEMO local."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
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
DOCUMENT_DECIMAL_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
CLASSIFICATION_KEYS = {
    "schema_version", "policy", "classification_only", "included_in_gross_needs",
    "additional_stock_movement", "coverage", "status", "recorded_by", "recorded_at", "lines",
}
CLASSIFICATION_LINE_KEYS = {
    "ingredient_id", "food_id", "food_name", "unit_id", "unit_name", "quantity_basis",
    "yield_ratio", "purchased_quantity", "useful_quantity", "waste_quantity", "cause",
}


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


def _document_decimal(value, label: str) -> Decimal:
    if not isinstance(value, str) or len(value) > 160 or DOCUMENT_DECIMAL_RE.fullmatch(value) is None:
        raise SmokeFailure(f"{label} no es un decimal textual congelado válido.")
    result = Decimal(value)
    if len(result.as_tuple().digits) > 64 or (result and not -64 <= result.adjusted() <= 64):
        raise SmokeFailure(f"{label} excede la precisión congelada admitida.")
    return result


def _document_id(value, label: str) -> int:
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise SmokeFailure(f"{label} no es un identificador congelado válido.")
    return value


def _document_label(value, label: str) -> str:
    if (not isinstance(value, str) or not 0 < len(value) <= 1024
            or any(ord(character) < 32 or 127 <= ord(character) <= 159
                   or 0xD800 <= ord(character) <= 0xDFFF for character in value)):
        raise SmokeFailure(f"{label} no es una etiqueta congelada válida.")
    return value


def _classification_identity(row: dict, prefix: str) -> bool:
    identifier, name = row.get(f"{prefix}_id"), row.get(f"{prefix}_name")
    if identifier is None and name is None:
        return False
    _document_id(identifier, f"waste.{prefix}_id")
    _document_label(name, f"waste.{prefix}_name")
    return True


def _waste_classification(value, *, produced_at: str, actor_id: int) -> dict:
    if not isinstance(value, dict) or set(value) != CLASSIFICATION_KEYS:
        raise SmokeFailure("La clasificación de merma tiene campos desconocidos o incompletos.")
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("policy") != "declared_yield_estimate"
            or value.get("classification_only") is not True
            or value.get("included_in_gross_needs") is not True
            or value.get("additional_stock_movement") is not False
            or value.get("coverage") != "declared_yields_only"
            or value.get("recorded_by") != actor_id
            or value.get("recorded_at") != produced_at):
        raise SmokeFailure("La política congelada de merma no coincide con la producción.")
    _document_id(value["recorded_by"], "waste.recorded_by")
    _aware(value["recorded_at"], "waste.recorded_at")
    lines = value.get("lines")
    if not isinstance(lines, list) or len(lines) > 10000:
        raise SmokeFailure("Las trazas congeladas de merma no forman una lista acotada.")
    incomplete = False
    for row in lines:
        if not isinstance(row, dict) or set(row) != CLASSIFICATION_LINE_KEYS:
            raise SmokeFailure("Una traza de merma tiene campos desconocidos o incompletos.")
        _document_id(row.get("ingredient_id"), "waste.ingredient_id")
        food_known = _classification_identity(row, "food")
        unit_known = _classification_identity(row, "unit")
        if not food_known and unit_known:
            raise SmokeFailure("Una traza de merma tiene unidad sin alimento congelado.")
        incomplete = incomplete or not food_known or not unit_known
        basis, raw_ratio = row.get("quantity_basis"), row.get("yield_ratio")
        if (not isinstance(basis, str) or basis not in {"gross", "net_usable"}
                or row.get("cause") != "declared_yield"):
            raise SmokeFailure("Una traza de merma no conserva su política declarada.")
        purchased = _document_decimal(row.get("purchased_quantity"), "waste.purchased_quantity")
        if raw_ratio is None:
            if basis != "gross" or row.get("useful_quantity") is not None or row.get("waste_quantity") is not None:
                raise SmokeFailure("Una traza sin rendimiento inventa cantidades útiles o merma.")
            incomplete = True
            continue
        ratio = _document_decimal(raw_ratio, "waste.yield_ratio")
        if not 0 < ratio <= 1:
            raise SmokeFailure("El rendimiento congelado debe estar entre cero y uno.")
        useful = _document_decimal(row.get("useful_quantity"), "waste.useful_quantity")
        waste = _document_decimal(row.get("waste_quantity"), "waste.waste_quantity")
        with localcontext() as context:
            context.prec, context.rounding = 64, ROUND_HALF_EVEN
            ratio_matches = useful == purchased * ratio if basis == "gross" else purchased == useful / ratio
            if not ratio_matches or purchased < useful or waste != purchased - useful:
                raise SmokeFailure("Las cantidades congeladas no corresponden al rendimiento declarado.")
    expected_status = "unknown" if not lines else "incomplete" if incomplete else "declared"
    if value.get("status") != expected_status:
        raise SmokeFailure("El estado de cobertura de merma no corresponde a sus trazas.")
    return value


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
    legacy_base = {"produced_at", "edition", "movement_ids", "stock_changed"}
    version_two_base = legacy_base | {"schema_version", "waste_classification"}
    expected_base = version_two_base if "schema_version" in production else legacy_base
    if set(production) not in (expected_base, expected_base | {"reversal"}):
        raise SmokeFailure("Producción contiene campos desconocidos o incompletos.")
    _aware(production.get("produced_at"), "production.produced_at")
    if payload.get("produced_at") != production.get("produced_at"):
        raise SmokeFailure("La fecha del servicio producido no coincide con su documento congelado.")
    if expected_base == version_two_base:
        if type(production.get("schema_version")) is not int or production["schema_version"] != 2:
            raise SmokeFailure("La versión del documento de producción no está soportada.")
        _waste_classification(
            production.get("waste_classification"),
            produced_at=production["produced_at"],
            actor_id=_document_id(payload.get("created_by"), "service.created_by"),
        )
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


def _produce_owned_service(
    session: HttpSession, *, service_id: int, recipe_id: int, edition: str,
    production_key: str, recovery,
) -> dict:
    """Produce and validate inside the compensation boundary."""
    with _production_recovery_guard(True, recovery):
        detail = _post_transition(session, service_id, "produce", production_key)
        detail = _service_detail(detail, service_id, recipe_id)
        if detail.get("state") != "produced":
            raise SmokeFailure("Producir no dejó el servicio en estado producido.")
        _production_document(detail, service_id, edition)
        return detail


def _recover_owned_production(
    session: HttpSession, *, service_id: int, recipe_id: int, edition: str,
    production_key: str, reversal_key: str, verify_recovered,
) -> dict:
    path = f"/api/cuaderno/services/{service_id}/"
    current = session.json("GET", path, csrf=False)
    detail = _service_detail(current, service_id, recipe_id)
    if detail.get("state") == "cancelled":
        production, original_ids = _production_document(detail, service_id, edition)
        audit = production.get("reversal")
        expected_hash = hashlib.sha256(reversal_key.encode("utf-8")).hexdigest()
        if (not isinstance(audit, dict) or set(audit) != AUDIT_KEYS
                or audit.get("key_sha256") != expected_hash
                or audit.get("reversed_by") != detail.get("created_by")):
            raise SmokeFailure(
                "CHECKPOINT: el servicio figura cancelado sin la reversión propia verificable; no se modifica.",
            )
        _aware(audit.get("reversed_at"), "reversal.reversed_at")
        reversal_ids = audit.get("movement_ids")
        if (audit.get("original_movement_ids") != original_ids
                or not isinstance(reversal_ids, list)
                or any(type(identifier) is not int or identifier <= 0 for identifier in reversal_ids)
                or len(reversal_ids) != len(set(reversal_ids))
                or set(reversal_ids) & set(original_ids)
                or (edition == "integral" and len(reversal_ids) != len(original_ids))
                or (edition == "profesional" and reversal_ids)):
            raise SmokeFailure(
                "CHECKPOINT: el servicio cancelado no conserva una reversión completa verificable; no se modifica.",
            )
        verify_recovered()
        return detail
    if detail.get("state") != "produced":
        raise SmokeFailure(
            "CHECKPOINT: el servicio ya no conserva la producción propia verificable; no se modifica.",
        )
    production, original_ids = _production_document(detail, service_id, edition)
    produced_snapshot = deepcopy(detail["snapshot"])
    replay = _post_transition(session, service_id, "produce", production_key)
    replay_production, replay_ids = _production_document(replay, service_id, edition)
    if (replay_ids != original_ids or replay_production != production
            or _persisted_service(replay) != detail):
        raise SmokeFailure(
            "CHECKPOINT: la clave de producción no reproduce exactamente el servicio; no se revierte.",
        )
    reversed_payload = _post_transition(session, service_id, "reverse", reversal_key)
    _validate_reversal(
        reversed_payload, service_id=service_id, recipe_id=recipe_id, edition=edition,
        produced_snapshot=produced_snapshot, reversal_key=reversal_key,
    )
    verify_recovered()
    return reversed_payload


def _reverse_owned_service(
    session: HttpSession, *, service_id: int, recipe_id: int, edition: str,
    reversal_key: str, produced_snapshot: dict, verify_recovered, recovery,
) -> dict:
    """Reverse and validate the persisted outcome inside recovery boundary."""
    with _production_recovery_guard(True, recovery):
        detail = _post_transition(session, service_id, "reverse", reversal_key)
        _validate_reversal(
            detail, service_id=service_id, recipe_id=recipe_id, edition=edition,
            produced_snapshot=produced_snapshot, reversal_key=reversal_key,
        )
        verify_recovered()
        return detail


@contextmanager
def _production_recovery_guard(enabled: bool, recovery):
    try:
        yield
    except Exception as original:
        if enabled:
            try:
                recovery()
            except Exception:
                raise SmokeFailure(
                    "CHECKPOINT: falló una comprobación después de producir y no se pudo verificar la "
                    "compensación propia. Conserva el servicio para diagnóstico local; no lo modifiques automáticamente.",
                ) from original
        raise


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
    produced_here = False

    def verify_recovered_inventory() -> None:
        restored = _inventory_amount(session, package)
        if edition == "integral":
            expected = (inventory_initial, Decimal("5"))
            if restored != expected:
                raise SmokeFailure("Integral no recuperó la misma existencia DEMO con 5 L.")
        elif restored != (inventory_initial, stock_initial):
            raise SmokeFailure("Profesional no conservó intacto su inventario DEMO.")

    if detail["state"] == "confirmed":
        before_denied = session.json("GET", path, csrf=False)
        session.request(
            "POST", path, payload={"action": "produce", "idempotency_key": production_key},
            csrf=False, expected=(403,),
        )
        if session.json("GET", path, csrf=False) != before_denied:
            raise SmokeFailure("Producir sin CSRF alteró el servicio.")
        detail = _produce_owned_service(
            session, service_id=service_id, recipe_id=recipe_id, edition=edition,
            production_key=production_key,
            recovery=lambda: _recover_owned_production(
                session, service_id=service_id, recipe_id=recipe_id, edition=edition,
                production_key=production_key, reversal_key=reversal_key,
                verify_recovered=verify_recovered_inventory,
            ),
        )
        produced_here = True

    if detail["state"] == "produced":
        with _production_recovery_guard(
            produced_here,
            lambda: _recover_owned_production(
                session, service_id=service_id, recipe_id=recipe_id, edition=edition,
                production_key=production_key, reversal_key=reversal_key,
                verify_recovered=verify_recovered_inventory,
            ),
        ):
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
            detail = _reverse_owned_service(
                session, service_id=service_id, recipe_id=recipe_id, edition=edition,
                reversal_key=reversal_key, produced_snapshot=produced_snapshot,
                verify_recovered=verify_recovered_inventory,
                recovery=lambda: _recover_owned_production(
                    session, service_id=service_id, recipe_id=recipe_id, edition=edition,
                    production_key=production_key, reversal_key=reversal_key,
                    verify_recovered=verify_recovered_inventory,
                ),
            )
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
