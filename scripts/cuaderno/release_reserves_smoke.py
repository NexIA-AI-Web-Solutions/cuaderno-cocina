#!/usr/bin/env python3
"""Release smoke for the persistent Integral DEMO stock reserve fixture."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, ROUND_CEILING, localcontext
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import HttpSession, SmokeFailure, _decimal, _guard_base_url, _guard_environment, _items
else:
    from release_http_smoke import HttpSession, SmokeFailure, _decimal, _guard_base_url, _guard_environment, _items


DEMO_USER = "demo-integral"
DEMO_SPACE = "Cuaderno Integral DEMO"
FOOD_NAME = "Aceite DEMO"
PACKAGE_LABEL = "Garrafa de 5 L"
UNIT_NAME = "L"
MINIMUM = Decimal("6")
PACKAGE_QUANTITY = Decimal("5")
REFERENCE_PRICE = Decimal("32")


def _positive_id(value, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise SmokeFailure(f"{label} no devolvió un identificador positivo.")
    return value


def _one(rows: list, predicate, label: str) -> dict:
    matching = [row for row in rows if isinstance(row, dict) and predicate(row)]
    if len(matching) != 1:
        raise SmokeFailure(f"{label} no existe de forma unívoca en el Space DEMO.")
    return matching[0]


def _minimum_envelope(payload) -> tuple[dict, list]:
    if not isinstance(payload, dict) or payload.get("edition") != "integral":
        raise SmokeFailure("La API de mínimos no devolvió el sobre Integral.")
    household = payload.get("household")
    rows = payload.get("items")
    if not isinstance(household, dict) or not isinstance(rows, list):
        raise SmokeFailure("La API de mínimos devolvió un sobre incompleto.")
    _positive_id(household.get("id"), "household")
    if not isinstance(household.get("name"), str):
        raise SmokeFailure("El hogar activo no tiene nombre textual.")
    return household, rows


def _expected_packages(missing: Decimal, quantity: Decimal = PACKAGE_QUANTITY) -> Decimal:
    if missing < 0 or quantity <= 0:
        raise SmokeFailure("No se puede calcular una reposición con cantidades inválidas.")
    with localcontext() as context:
        context.prec = 64
        return (missing / quantity).to_integral_value(rounding=ROUND_CEILING) if missing else Decimal("0")


def _snapshot(session: HttpSession, path: str):
    payload = session.json("GET", path, csrf=False)
    rows = _items(payload)
    if isinstance(payload, dict):
        if (
            type(payload.get("count")) is not int
            or payload["count"] != len(rows)
            or payload.get("next") is not None
            or payload.get("previous") is not None
        ):
            raise SmokeFailure("El snapshot HTTP está paginado o su conteo no es completo.")
        timestamp = payload.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise SmokeFailure("El snapshot paginado no incluye timestamp de transporte válido.")
        payload = dict(payload)
        del payload["timestamp"]
    return payload


def _active_integral_space(session: HttpSession) -> dict:
    edition = session.json("GET", "/api/cuaderno/edition/", csrf=False)
    if not isinstance(edition, dict) or edition.get("edition") != "integral":
        raise SmokeFailure("demo-integral no está en la edición Integral.")
    memberships = _items(session.json("GET", "/api/user-space/all_personal/", csrf=False))
    active = [row for row in memberships if isinstance(row, dict) and row.get("active") is True]
    if len(active) != 1:
        raise SmokeFailure("demo-integral debe tener exactamente un Space activo.")
    space_id = _positive_id(active[0].get("space"), "Space activo")
    space = session.json("GET", f"/api/space/{space_id}/", csrf=False)
    if not isinstance(space, dict) or space.get("name") != DEMO_SPACE:
        raise SmokeFailure("El Space activo no es Cuaderno Integral DEMO.")
    return space


def _demo_package(session: HttpSession) -> dict:
    packages = _items(session.json("GET", "/api/cuaderno/packages/", csrf=False))
    package = _one(
        packages,
        lambda row: row.get("food_name") == FOOD_NAME
        and row.get("label") == PACKAGE_LABEL
        and row.get("unit_name") == UNIT_NAME
        and _decimal(row.get("quantity"), "quantity") == PACKAGE_QUANTITY,
        "La garrafa DEMO de aceite",
    )
    _positive_id(package.get("id"), "package")
    _positive_id(package.get("food"), "food")
    _positive_id(package.get("unit"), "unit")
    price = package.get("current_price")
    if (
        not isinstance(price, dict)
        or price.get("explicit_free") is not False
        or _decimal(price.get("amount"), "current_price.amount") != REFERENCE_PRICE
    ):
        raise SmokeFailure("La garrafa DEMO no conserva su precio de referencia de 32 EUR.")
    return package


def _oil_minimum(rows: list, food_id: int, unit_id: int, household_id: int) -> dict | None:
    oil_rows = [row for row in rows if isinstance(row, dict) and row.get("food") == food_id]
    if not oil_rows:
        return None
    if len(oil_rows) != 1:
        raise SmokeFailure("Aceite DEMO tiene varios mínimos; no se sobrescriben.")
    row = oil_rows[0]
    _positive_id(row.get("id"), "minimum.id")
    if (
        row.get("household") != household_id
        or row.get("unit") != unit_id
        or row.get("location") is not None
        or _decimal(row.get("quantity"), "minimum.quantity") != MINIMUM
        or not isinstance(row.get("updated_at"), str)
        or not row["updated_at"]
    ):
        raise SmokeFailure("Aceite DEMO ya tiene un mínimo con hogar, unidad, cantidad o ubicación distintos; no se sobrescribe.")
    return row


def _assert_same_document(first: dict, second: dict) -> None:
    if _positive_id(first.get("id"), "minimum.id") != _positive_id(second.get("id"), "minimum.id"):
        raise SmokeFailure("Repetir el mínimo creó otro documento.")
    if first.get("updated_at") != second.get("updated_at") or first != second:
        raise SmokeFailure("Repetir el mismo mínimo creó una actualización o auditoría duplicada.")


def _assert_replenishment(session: HttpSession, package: dict) -> dict:
    payload = session.json("POST", "/api/cuaderno/replenishment/", payload={})
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise SmokeFailure("Reposición no devolvió su sobre de items.")
    item = _one(payload["items"], lambda row: row.get("food") == package["food"], "Reposición de Aceite DEMO")
    if item.get("unit") != package["unit"] or item.get("package") != package["id"]:
        raise SmokeFailure("Reposición no utilizó la unidad y garrafa DEMO de referencia.")
    required = _decimal(item.get("required"), "required")
    usable = _decimal(item.get("usable_stock"), "usable_stock")
    minimum = _decimal(item.get("minimum_stock"), "minimum_stock")
    target = _decimal(item.get("target_stock"), "target_stock")
    missing = _decimal(item.get("missing"), "missing")
    if required < 0 or usable < 0 or minimum != MINIMUM:
        raise SmokeFailure("Reposición devolvió necesidades, stock o mínimo inválidos.")
    with localcontext() as context:
        context.prec = 64
        expected_target = required + MINIMUM
        expected_missing = max(expected_target - usable, Decimal("0"))
        expected_packages = _expected_packages(expected_missing)
        expected_purchase = expected_packages * PACKAGE_QUANTITY
    if target != expected_target or missing != expected_missing:
        raise SmokeFailure("Reposición no aplica objetivo = necesario + reserva y falta = max(objetivo - stock, 0).")
    if _decimal(item.get("packages"), "packages") != expected_packages:
        raise SmokeFailure("Reposición no redondeó los envases de 5 L hacia arriba.")
    if _decimal(item.get("purchase_quantity"), "purchase_quantity") != expected_purchase:
        raise SmokeFailure("La cantidad de compra no coincide con los envases propuestos.")
    if _decimal(item.get("reference_price"), "reference_price") != REFERENCE_PRICE or item.get("currency") != "EUR":
        raise SmokeFailure("Reposición no conserva el coste de referencia DEMO de 32 EUR.")
    if item.get("location_shortfalls") != []:
        raise SmokeFailure("Un mínimo global no debe generar déficits por ubicación.")
    return item


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    session = HttpSession()
    ready = session.json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    session.login(DEMO_USER, password)
    _active_integral_space(session)
    package = _demo_package(session)

    inventory_path = "/api/inventory-entry/?" + urlencode({"page_size": "100"})
    inventory_before = _snapshot(session, inventory_path)
    orders_before = _snapshot(session, "/api/cuaderno/purchase-orders/")
    if len(_items(orders_before)) >= 100:
        raise SmokeFailure("La lista de pedidos alcanzó el límite 100; el snapshot completo es ambiguo.")

    minimum_path = "/api/cuaderno/stock-minimums/"
    household, existing_rows = _minimum_envelope(session.json("GET", minimum_path, csrf=False))
    household_id = household["id"]
    existing = _oil_minimum(existing_rows, package["food"], package["unit"], household_id)
    body = {"food": package["food"], "unit": package["unit"], "quantity": "6", "location": None}

    first_household, first_rows = _minimum_envelope(session.json("PUT", minimum_path, payload=body))
    if first_household["id"] != household_id:
        raise SmokeFailure("Guardar la reserva cambió de hogar activo.")
    first = _oil_minimum(first_rows, package["food"], package["unit"], household_id)
    if first is None:
        raise SmokeFailure("Guardar la reserva DEMO no devolvió su documento.")
    second_household, second_rows = _minimum_envelope(session.json("PUT", minimum_path, payload=body))
    if second_household["id"] != household_id:
        raise SmokeFailure("Repetir la reserva cambió de hogar activo.")
    second = _oil_minimum(second_rows, package["food"], package["unit"], household_id)
    if second is None:
        raise SmokeFailure("Repetir la reserva DEMO eliminó su documento.")
    _assert_same_document(first, second)
    if existing is not None and existing != first:
        raise SmokeFailure("Una reserva DEMO ya válida cambió al repetirla.")

    session.request("PUT", minimum_path, payload={**body, "quantity": "7"}, csrf=False, expected=(403,))
    protected_household, protected_rows = _minimum_envelope(session.json("GET", minimum_path, csrf=False))
    if protected_household["id"] != household_id:
        raise SmokeFailure("La comprobación CSRF cambió de hogar activo.")
    protected = _oil_minimum(protected_rows, package["food"], package["unit"], household_id)
    if protected is None or protected != second:
        raise SmokeFailure("La escritura sin CSRF alteró la reserva DEMO.")

    replenishment = _assert_replenishment(session, package)
    inventory_after = _snapshot(session, inventory_path)
    orders_after = _snapshot(session, "/api/cuaderno/purchase-orders/")
    if inventory_after != inventory_before:
        raise SmokeFailure("Configurar una reserva alteró el inventario nativo.")
    if orders_after != orders_before:
        raise SmokeFailure("Calcular reposición creó o alteró pedidos.")
    session.logout()
    return {
        "account": DEMO_USER,
        "space": DEMO_SPACE,
        "minimum_id": second["id"],
        "minimum": second["quantity"],
        "required": replenishment["required"],
        "missing": replenishment["missing"],
        "packages": replenishment["packages"],
        "persistent_demo_fixture": True,
        "stock_unchanged": True,
        "orders_unchanged": True,
        "csrf_protected": True,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_RESERVES_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_RESERVES_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
