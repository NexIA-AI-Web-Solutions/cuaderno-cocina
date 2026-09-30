#!/usr/bin/env python3
"""Release smoke for standalone waste valuation in the local Integral DEMO."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import HttpSession, SmokeFailure, _guard_base_url, _guard_environment, _items
    from .release_preparation_smoke import _native_stock_amount_token
    from .release_reserves_smoke import _active_integral_space, _demo_package, _positive_id, _snapshot
else:
    from release_http_smoke import HttpSession, SmokeFailure, _guard_base_url, _guard_environment, _items
    from release_preparation_smoke import _native_stock_amount_token
    from release_reserves_smoke import _active_integral_space, _demo_package, _positive_id, _snapshot


DEMO_USER = "demo-integral"
DEMO_SPACE = "Cuaderno Integral DEMO"
FOOD_NAME = "Aceite DEMO"
PACKAGE_LABEL = "Garrafa de 5 L"
UNIT_NAME = "L"
CAUSE = "Limpieza smoke release DEMO"
QUANTITY = Decimal("0.125")
EXPECTED_VALUE = Decimal("0.8")
MOVEMENT_KEY = "release-waste-demo-v1"
REVERSAL_KEY = "release-waste-demo-v1-reverse"
MOVEMENTS_PATH = "/api/cuaderno/movements/"
_FIXED = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d{1,16})?$")


def _fixed_decimal(value, label: str) -> Decimal:
    if not isinstance(value, str) or len(value) > 96 or _FIXED.fullmatch(value) is None:
        raise SmokeFailure(f"{label} no es un decimal fijo textual acotado.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise SmokeFailure(f"{label} no es un decimal válido.") from exc
    if not parsed.is_finite():
        raise SmokeFailure(f"{label} no es finito.")
    return parsed


def _fixture_stock_token(value) -> tuple[str, str]:
    token = _native_stock_amount_token(value)
    if token not in {("int", "5"), ("float", "5.0")}:
        raise SmokeFailure("La existencia Aceite DEMO no conserva el fixture exacto de 5 L.")
    return token


def _aware(value, label: str) -> None:
    if not isinstance(value, str):
        raise SmokeFailure(f"{label} no es una fecha textual.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SmokeFailure(f"{label} no es una fecha ISO válida.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SmokeFailure(f"{label} no incluye zona horaria.")


def _validate_valuation(payload, *, package_id: int, unit_id: int, quantity: Decimal) -> Decimal:
    expected_keys = {
        "policy", "status", "amount", "currency", "price_policy", "as_of", "reason",
        "input", "package", "price_version", "calculation",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise SmokeFailure("La valoración no devolvió su snapshot completo.")
    if (
        payload.get("policy") != "replacement_estimate"
        or payload.get("status") != "complete"
        or payload.get("currency") != "EUR"
        or payload.get("price_policy") not in {"net", "gross"}
        or payload.get("reason") is not None
    ):
        raise SmokeFailure("La valoración no declaró su política de reposición completa.")
    _aware(payload.get("as_of"), "valuation.as_of")
    amount = _fixed_decimal(payload.get("amount"), "valuation.amount")
    if amount != EXPECTED_VALUE:
        raise SmokeFailure("La valoración de 0.125 L no es 0.8 EUR.")

    input_data = payload.get("input")
    if not isinstance(input_data, dict) or set(input_data) != {"quantity", "unit_id", "unit_name"}:
        raise SmokeFailure("La valoración no congeló su cantidad de entrada.")
    if (
        _fixed_decimal(input_data.get("quantity"), "valuation.input.quantity") != quantity
        or _positive_id(input_data.get("unit_id"), "valuation.input.unit_id") != unit_id
        or input_data.get("unit_name") != UNIT_NAME
    ):
        raise SmokeFailure("La cantidad o unidad valorada no coincide con el desperdicio.")

    package = payload.get("package")
    if not isinstance(package, dict) or set(package) != {"id", "label", "quantity", "unit_id", "unit_name"}:
        raise SmokeFailure("La valoración no congeló el formato de referencia.")
    if (
        _positive_id(package.get("id"), "valuation.package.id") != package_id
        or package.get("label") != PACKAGE_LABEL
        or _fixed_decimal(package.get("quantity"), "valuation.package.quantity") != Decimal("5")
        or _positive_id(package.get("unit_id"), "valuation.package.unit_id") != unit_id
        or package.get("unit_name") != UNIT_NAME
    ):
        raise SmokeFailure("La valoración no usó la garrafa DEMO de 5 L.")

    price = payload.get("price_version")
    if not isinstance(price, dict) or set(price) != {"id", "amount", "explicit_free", "valid_from"}:
        raise SmokeFailure("La valoración no congeló la versión de precio.")
    _positive_id(price.get("id"), "valuation.price_version.id")
    if _fixed_decimal(price.get("amount"), "valuation.price_version.amount") != Decimal("32") or price.get("explicit_free") is not False:
        raise SmokeFailure("La valoración no usó el precio DEMO de 32 EUR.")
    _aware(price.get("valid_from"), "valuation.price_version.valid_from")

    calculation = payload.get("calculation")
    expected_calculation_keys = {
        "quantity_in_package_unit", "package_fraction", "computed_amount", "working_precision", "rounding",
    }
    if not isinstance(calculation, dict) or set(calculation) != expected_calculation_keys:
        raise SmokeFailure("La valoración no explicó su cálculo Decimal.")
    if (
        _fixed_decimal(calculation.get("quantity_in_package_unit"), "valuation.converted") != quantity
        or _fixed_decimal(calculation.get("package_fraction"), "valuation.fraction") != Decimal("0.025")
        or _fixed_decimal(calculation.get("computed_amount"), "valuation.computed") != amount
        or calculation.get("working_precision") != 64
        or calculation.get("rounding") != "HALF_EVEN"
    ):
        raise SmokeFailure("El cálculo de valoración no conserva Decimal64/HALF_EVEN.")
    return amount


def _movement_rows(payload) -> list[dict]:
    if not isinstance(payload, list) or len(payload) >= 100 or any(not isinstance(row, dict) for row in payload):
        raise SmokeFailure("El historial de movimientos está truncado o tiene forma inválida.")
    ids = [_positive_id(row.get("id"), "movement.id") for row in payload]
    if len(ids) != len(set(ids)):
        raise SmokeFailure("El historial contiene movimientos duplicados.")
    return payload


def _owned_movement(rows, *, movement_id: int, entry_id: int, household_id: int) -> dict:
    rows = _movement_rows(rows)
    matches = [row for row in rows if row.get("id") == movement_id]
    if len(matches) != 1:
        raise SmokeFailure("El movimiento propio no aparece de forma unívoca en el historial completo.")
    row = matches[0]
    metadata = row.get("metadata_snapshot")
    if (
        row.get("kind") != "waste"
        or _positive_id(row.get("entry"), "movement.entry") != entry_id
        or row.get("reverses") is not None
        or _fixed_decimal(row.get("quantity"), "movement.quantity") != QUANTITY
        or not isinstance(metadata, dict)
        or _positive_id(metadata.get("household_id"), "movement.household") != household_id
        or metadata.get("origin") != {"type": "standalone_waste", "cause": CAUSE}
    ):
        raise SmokeFailure("El movimiento no coincide con la identidad reservada del smoke.")
    _aware(row.get("created_at"), "movement.created_at")
    return row


def _restored_balance(balance_after, quantity: Decimal) -> Decimal:
    return _fixed_decimal(balance_after, "movement.balance") + quantity


def _validate_reversal(payload, *, original: dict, expected_balance: Decimal) -> int:
    if not isinstance(payload, dict):
        raise SmokeFailure("La reversión no devolvió un documento JSON.")
    reversal_id = _positive_id(payload.get("movement_id"), "reversal.movement_id")
    if (
        payload.get("kind") != "receipt"
        or _positive_id(payload.get("reverses"), "reversal.reverses") != original.get("id")
        or _fixed_decimal(payload.get("balance"), "reversal.balance") != expected_balance
        or _fixed_decimal(payload.get("current_balance"), "reversal.current_balance") != expected_balance
        or payload.get("metadata_snapshot") != original.get("metadata_snapshot")
    ):
        raise SmokeFailure("La reversión no restauró saldo, origen y valoración exactos.")
    return reversal_id


def _compensate_owned(session: HttpSession, *, movement_id: int, entry_id: int, household_id: int) -> dict:
    original = _owned_movement(
        session.json("GET", MOVEMENTS_PATH, csrf=False),
        movement_id=movement_id,
        entry_id=entry_id,
        household_id=household_id,
    )
    expected = _restored_balance(original.get("balance"), QUANTITY)
    reversal = session.json(
        "POST",
        MOVEMENTS_PATH,
        payload={"reverse_of": movement_id, "idempotency_key": REVERSAL_KEY},
        expected=(201,),
    )
    _validate_reversal(reversal, original=original, expected_balance=expected)
    return reversal


def _compensate_attempted(session: HttpSession, *, body: dict, movement_id, entry_id: int, household_id: int) -> dict:
    if movement_id is None:
        replay = session.json("POST", MOVEMENTS_PATH, payload=body, expected=(201,))
        if not isinstance(replay, dict):
            raise SmokeFailure("No se pudo identificar el movimiento tras reintentar la clave reservada.")
        movement_id = _positive_id(replay.get("movement_id"), "recovery.movement_id")
    return _compensate_owned(
        session, movement_id=movement_id, entry_id=entry_id, household_id=household_id,
    )


def _demo_entry(inventory_payload, *, package: dict) -> tuple[dict, int, tuple[str, str]]:
    rows = _items(inventory_payload)
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        food = row.get("food")
        unit = row.get("unit")
        location = row.get("inventory_location")
        household = location.get("household") if isinstance(location, dict) else None
        if (
            isinstance(food, dict) and type(food.get("id")) is int and food.get("id") == package["food"] and food.get("name") == FOOD_NAME
            and isinstance(unit, dict) and type(unit.get("id")) is int and unit.get("id") == package["unit"] and unit.get("name") == UNIT_NAME
            and isinstance(household, dict) and type(household.get("id")) is int and household["id"] > 0
        ):
            matches.append((row, household["id"]))
    if len(matches) != 1:
        raise SmokeFailure("La existencia Aceite DEMO/L no es unívoca en el hogar activo.")
    row, household_id = matches[0]
    _positive_id(row.get("id"), "inventory.entry")
    stock_token = _fixture_stock_token(row.get("amount"))
    return row, household_id, stock_token


def _row_by_id(inventory_payload, entry_id: int) -> dict:
    matches = [row for row in _items(inventory_payload) if isinstance(row, dict) and row.get("id") == entry_id]
    if len(matches) != 1:
        raise SmokeFailure("La existencia DEMO desapareció del snapshot completo.")
    return matches[0]


def _assert_lower_editions(password: str, entry_id: int) -> None:
    for edition, title in (("esencial", "Esencial"), ("profesional", "Profesional")):
        session = HttpSession()
        session.login(f"demo-{edition}", password)
        payload = session.json("GET", "/api/cuaderno/edition/", csrf=False)
        if not isinstance(payload, dict) or payload.get("edition") != edition:
            raise SmokeFailure(f"demo-{edition} no conserva su edición.")
        memberships = _items(session.json("GET", "/api/user-space/all_personal/", csrf=False))
        active = [row for row in memberships if isinstance(row, dict) and row.get("active") is True]
        if len(active) != 1:
            raise SmokeFailure(f"demo-{edition} no tiene un único Space activo.")
        space_id = _positive_id(active[0].get("space"), f"Space {edition}")
        space = session.json("GET", f"/api/space/{space_id}/", csrf=False)
        if not isinstance(space, dict) or space.get("name") != f"Cuaderno {title} DEMO":
            raise SmokeFailure(f"demo-{edition} no pertenece al Space DEMO esperado.")
        inventory_path = "/api/inventory-entry/?" + urlencode({"page_size": "100", "empty": "true"})
        before = _snapshot(session, inventory_path)
        session.request(
            "POST", MOVEMENTS_PATH,
            payload={
                "entry": entry_id, "kind": "waste", "quantity": "0.125",
                "cause": CAUSE, "idempotency_key": f"{MOVEMENT_KEY}-{edition}",
            },
            expected=(403,),
        )
        after = _snapshot(session, inventory_path)
        if after != before:
            raise SmokeFailure(f"El rechazo {edition} alteró su inventario.")
        session.logout()


def _assert_added_only(before: list[dict], after: list[dict], allowed: set[int]) -> None:
    before_by_id = {row["id"]: row for row in _movement_rows(before)}
    after_by_id = {row["id"]: row for row in _movement_rows(after)}
    if any(after_by_id.get(pk) != row for pk, row in before_by_id.items()):
        raise SmokeFailure("El smoke reescribió movimientos históricos.")
    if set(after_by_id) - set(before_by_id) - allowed:
        raise SmokeFailure("El smoke creó movimientos ajenos a la operación reservada.")


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    session = HttpSession()
    ready = session.json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    session.login(DEMO_USER, password)
    space = _active_integral_space(session)
    if space.get("name") != DEMO_SPACE:
        raise SmokeFailure("La cuenta Integral no está en el Space DEMO exacto.")
    package = _demo_package(session)
    inventory_path = "/api/inventory-entry/?" + urlencode({"page_size": "100", "empty": "true"})
    inventory_before = _snapshot(session, inventory_path)
    entry, household_id, baseline_stock_token = _demo_entry(inventory_before, package=package)
    entry_id = entry["id"]
    _assert_lower_editions(password, entry_id)
    movements_before = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
    if len(movements_before) > 97:
        raise SmokeFailure("El historial no deja margen para movimiento y reversión sin alcanzar el límite 100.")

    body = {
        "entry": entry_id, "kind": "waste", "quantity": "0.125",
        "cause": CAUSE, "idempotency_key": MOVEMENT_KEY,
    }
    candidate_id = None
    creation_attempted = False
    try:
        creation_attempted = True
        first = session.json("POST", MOVEMENTS_PATH, payload=body, expected=(201,))
        if not isinstance(first, dict):
            raise SmokeFailure("Registrar desperdicio no devolvió un documento.")
        candidate_id = _positive_id(first.get("movement_id"), "waste.movement_id")
        rows_after_first = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
        original = _owned_movement(
            rows_after_first, movement_id=candidate_id, entry_id=entry_id, household_id=household_id,
        )
        valuation = original["metadata_snapshot"].get("valuation")
        _validate_valuation(valuation, package_id=package["id"], unit_id=package["unit"], quantity=QUANTITY)
        if first.get("metadata_snapshot") != original["metadata_snapshot"]:
            raise SmokeFailure("Respuesta e historial discrepan sobre el snapshot del desperdicio.")
        expected_restored = _restored_balance(original.get("balance"), QUANTITY)
        if expected_restored != Decimal("5"):
            raise SmokeFailure("El movimiento reservado no corresponde al fixture histórico de 5 L.")
        original_was_new = candidate_id not in {row["id"] for row in movements_before}
        _assert_added_only(movements_before, rows_after_first, {candidate_id} if original_was_new else set())

        replay = session.json("POST", MOVEMENTS_PATH, payload=body, expected=(201,))
        if replay.get("movement_id") != candidate_id or replay.get("metadata_snapshot") != original["metadata_snapshot"]:
            raise SmokeFailure("Repetir el desperdicio no devolvió el documento original.")
        rows_after_replay = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
        if rows_after_replay != rows_after_first:
            raise SmokeFailure("Repetir el desperdicio creó auditoría duplicada.")

        session.request("POST", MOVEMENTS_PATH, payload={**body, "cause": "Otra causa"}, expected=(409,))
        session.request("POST", MOVEMENTS_PATH, payload={**body, "idempotency_key": MOVEMENT_KEY + "-invalid", "cause": ""}, expected=(400,))
        session.request("POST", MOVEMENTS_PATH, payload={**body, "idempotency_key": MOVEMENT_KEY + "-csrf"}, csrf=False, expected=(403,))
        if _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False)) != rows_after_first:
            raise SmokeFailure("Conflicto, validación o CSRF alteraron el historial.")

        reversal = session.json(
            "POST", MOVEMENTS_PATH,
            payload={"reverse_of": candidate_id, "idempotency_key": REVERSAL_KEY},
            expected=(201,),
        )
        reversal_id = _validate_reversal(reversal, original=original, expected_balance=expected_restored)
        rows_after_reverse = _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False))
        allowed = {reversal_id} if reversal_id not in {row["id"] for row in rows_after_first} else set()
        _assert_added_only(rows_after_first, rows_after_reverse, allowed)
        reversal_replay = session.json(
            "POST", MOVEMENTS_PATH,
            payload={"reverse_of": candidate_id, "idempotency_key": REVERSAL_KEY},
            expected=(201,),
        )
        _validate_reversal(reversal_replay, original=original, expected_balance=expected_restored)
        if _movement_rows(session.json("GET", MOVEMENTS_PATH, csrf=False)) != rows_after_reverse:
            raise SmokeFailure("Repetir la reversión creó auditoría duplicada.")

        inventory_after = _snapshot(session, inventory_path)
        final_entry = _row_by_id(inventory_after, entry_id)
        if _fixture_stock_token(final_entry.get("amount")) != baseline_stock_token:
            raise SmokeFailure("La reversión no restauró el token nativo exacto del saldo inicial.")
        before_other = {row.get("id"): row for row in _items(inventory_before) if row.get("id") != entry_id}
        after_other = {row.get("id"): row for row in _items(inventory_after) if row.get("id") != entry_id}
        if before_other != after_other:
            raise SmokeFailure("El smoke alteró otra existencia del hogar.")
    except Exception as original_error:
        if creation_attempted:
            try:
                _compensate_attempted(
                    session, body=body, movement_id=candidate_id,
                    entry_id=entry_id, household_id=household_id,
                )
            except Exception as compensation_error:
                raise SmokeFailure(
                    f"{original_error} Además, no se pudo compensar con seguridad el movimiento propio: {compensation_error}"
                ) from original_error
        try:
            session.logout()
        except Exception:
            pass
        raise

    session.logout()

    return {
        "account": DEMO_USER,
        "space": DEMO_SPACE,
        "entry_id": entry_id,
        "movement_id": candidate_id,
        "reversal_id": reversal_id,
        "quantity": "0.125",
        "valuation": "0.8",
        "currency": "EUR",
        "balance_restored": True,
        "idempotent_replay": True,
        "csrf_protected": True,
        "lower_editions_forbidden": True,
        "audit_rows_preserved": True,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_WASTE_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_WASTE_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
