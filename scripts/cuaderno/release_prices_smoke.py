#!/usr/bin/env python3
"""Read-only release HTTP smoke for DEMO price history and recipe impact."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from decimal import Decimal, localcontext

if __package__:
    from .release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment
    from .release_reserves_smoke import PACKAGE_QUANTITY, REFERENCE_PRICE, _demo_package, _positive_id
    from .release_yields_smoke import _active_space, _assert_same_snapshots, _demo_recipe, _state_snapshots
else:
    from release_http_smoke import EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment
    from release_reserves_smoke import PACKAGE_QUANTITY, REFERENCE_PRICE, _demo_package, _positive_id
    from release_yields_smoke import _active_space, _assert_same_snapshots, _demo_recipe, _state_snapshots


ACCOUNT_PREFIX = "demo-"
INGREDIENT_LITRES = Decimal("0.4")
SERVINGS = Decimal("4")
HISTORY_LIMIT = 20
EXPECTED_HISTORY_KEYS = {
    "package", "currency", "as_of", "current_price_id", "count", "next_offset", "items",
}
EXPECTED_HISTORY_ITEM_KEYS = {
    "id", "amount", "explicit_free", "valid_from", "created_at", "created_by", "note", "is_current",
}
EXPECTED_IMPACT_KEYS = {
    "recipe_id", "package", "as_of", "current_price_id", "previous_price_id", "affected",
    "before", "after", "difference", "difference_per_serving", "currency", "price_policy",
}
EXPECTED_SHEET_KEYS = {
    "status", "unrounded", "display", "known_subtotal", "total", "warnings",
    "base_servings", "servings", "per_serving", "lines",
}
_UNSIGNED_FIXED = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)
_SIGNED_FIXED = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)


def _fixed_decimal(
    value,
    label: str,
    *,
    signed: bool = False,
    max_digits: int = 64,
    max_fraction: int = 64,
) -> Decimal:
    if not isinstance(value, str) or len(value) > 256:
        raise SmokeFailure(f"{label} no llegó como decimal textual acotado.")
    pattern = _SIGNED_FIXED if signed else _UNSIGNED_FIXED
    if pattern.fullmatch(value) is None or (value.startswith("-") and Decimal(value) == 0):
        raise SmokeFailure(f"{label} no es un decimal fijo canónico.")
    unsigned = value.removeprefix("-")
    whole, separator, fraction = unsigned.partition(".")
    significant = (whole.lstrip("0") + fraction).lstrip("0") or "0"
    if len(significant) > max_digits or (separator and len(fraction) > max_fraction):
        raise SmokeFailure(f"{label} excede la precisión permitida.")
    return Decimal(value)


def _aware_datetime(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise SmokeFailure(f"{label} no es una fecha textual.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SmokeFailure(f"{label} no es una fecha ISO válida.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SmokeFailure(f"{label} no incluye zona horaria.")
    return parsed


def _validate_history(payload, *, package_id):
    if not isinstance(payload, dict) or set(payload) != EXPECTED_HISTORY_KEYS:
        raise SmokeFailure("El historial no devolvió su sobre exacto.")
    response_package_id = _positive_id(payload.get("package"), "history.package")
    if response_package_id != package_id or payload.get("currency") != "EUR":
        raise SmokeFailure("El historial no pertenece al formato DEMO en EUR.")
    as_of = _aware_datetime(payload.get("as_of"), "history.as_of")
    current_id = _positive_id(payload.get("current_price_id"), "history.current_price_id")
    count = payload.get("count")
    items = payload.get("items")
    if type(count) is not int or count < 1 or not isinstance(items, list) or not 1 <= len(items) <= HISTORY_LIMIT:
        raise SmokeFailure("El historial tiene conteo o página inválidos.")
    if count < len(items):
        raise SmokeFailure("El conteo del historial es menor que su página.")
    expected_next = len(items) if count > len(items) else None
    next_offset = payload.get("next_offset")
    if next_offset is not None and type(next_offset) is not int:
        raise SmokeFailure("El siguiente offset del historial no es un entero exacto.")
    if next_offset != expected_next:
        raise SmokeFailure("El siguiente offset del historial no coincide con la página.")
    if count > len(items) and len(items) != HISTORY_LIMIT:
        raise SmokeFailure("El historial truncado no llenó el límite solicitado.")

    versions = {}
    dates = {}
    ordered = []
    for row in items:
        if not isinstance(row, dict) or set(row) != EXPECTED_HISTORY_ITEM_KEYS:
            raise SmokeFailure("El historial contiene una versión con forma inválida.")
        version_id = _positive_id(row.get("id"), "price.id")
        if version_id in versions:
            raise SmokeFailure("El historial contiene versiones duplicadas.")
        amount = _fixed_decimal(
            row.get("amount"), "price.amount", max_digits=32, max_fraction=16,
        )
        explicit_free = row.get("explicit_free")
        if type(explicit_free) is not bool or amount < 0 or ((amount == 0) != explicit_free):
            raise SmokeFailure("El historial contiene un precio o gratuidad incoherentes.")
        valid_from = _aware_datetime(row.get("valid_from"), "price.valid_from")
        _aware_datetime(row.get("created_at"), "price.created_at")
        _positive_id(row.get("created_by"), "price.created_by")
        if not isinstance(row.get("note"), str) or type(row.get("is_current")) is not bool:
            raise SmokeFailure("El historial contiene autoría o estado sin tipo válido.")
        if row["is_current"] is not (version_id == current_id):
            raise SmokeFailure("La marca de precio actual no coincide con el identificador global.")
        if valid_from > as_of and row["is_current"]:
            raise SmokeFailure("Una versión futura aparece como precio actual.")
        versions[version_id] = amount
        dates[version_id] = valid_from
        ordered.append((valid_from, version_id))
    if ordered != sorted(ordered, reverse=True):
        raise SmokeFailure("El historial no está ordenado por fecha e identificador descendentes.")
    if current_id not in versions:
        raise SmokeFailure("El precio actual DEMO no aparece en la primera página del historial.")
    effective = [version_id for valid_from, version_id in ordered if valid_from <= as_of]
    if not effective or effective[0] != current_id:
        raise SmokeFailure("El precio actual no es la primera versión efectiva a la fecha del historial.")
    if versions[current_id] != REFERENCE_PRICE:
        raise SmokeFailure("El historial no conserva el precio actual DEMO de 32 EUR.")
    return {
        "as_of": as_of,
        "current_price_id": current_id,
        "count": count,
        "versions": versions,
        "dates": dates,
    }


def _sheet_total(sheet, *, status: str, label: str) -> Decimal | None:
    if not isinstance(sheet, dict) or set(sheet) != EXPECTED_SHEET_KEYS or sheet.get("status") != status:
        raise SmokeFailure(f"{label} no tiene estado {status}.")
    if not isinstance(sheet.get("warnings"), list) or not isinstance(sheet.get("lines"), list):
        raise SmokeFailure(f"{label} no contiene listas de avisos y líneas válidas.")
    base_servings = _fixed_decimal(sheet.get("base_servings"), f"{label}.base_servings")
    servings = _fixed_decimal(sheet.get("servings"), f"{label}.servings")
    known = _fixed_decimal(sheet.get("known_subtotal"), f"{label}.known_subtotal")
    if base_servings <= 0 or servings != SERVINGS or known < 0:
        raise SmokeFailure(f"{label} no conserva raciones o subtotal conocidos válidos.")
    if status != "complete":
        if any(sheet.get(key) is not None for key in ("total", "unrounded", "display", "per_serving")):
            raise SmokeFailure(f"{label} convirtió un coste desconocido en cero.")
        return None
    total = _fixed_decimal(sheet.get("total"), f"{label}.total")
    unrounded = _fixed_decimal(sheet.get("unrounded"), f"{label}.unrounded")
    _fixed_decimal(sheet.get("display"), f"{label}.display")
    per_serving = _fixed_decimal(sheet.get("per_serving"), f"{label}.per_serving")
    if total != unrounded or per_serving != total / servings:
        raise SmokeFailure(f"{label} no conserva el total exacto sin redondear.")
    return total


def _validate_impact(payload, *, recipe_id, package_id, history):
    if not isinstance(payload, dict) or set(payload) != EXPECTED_IMPACT_KEYS:
        raise SmokeFailure("El impacto no devolvió su sobre exacto.")
    response_recipe_id = _positive_id(payload.get("recipe_id"), "impact.recipe_id")
    response_package_id = _positive_id(payload.get("package"), "impact.package")
    if response_recipe_id != recipe_id or response_package_id != package_id:
        raise SmokeFailure("El impacto pertenece a otra receta o formato.")
    if payload.get("currency") != "EUR" or payload.get("price_policy") not in {"net", "gross"}:
        raise SmokeFailure("El impacto no declaró moneda y política de precio válidas.")
    _aware_datetime(payload.get("as_of"), "impact.as_of")
    if payload.get("affected") is not True:
        raise SmokeFailure("La garrafa DEMO no aparece como precio usado por Salsa DEMO.")
    current_id = _positive_id(payload.get("current_price_id"), "impact.current_price_id")
    if current_id != history["current_price_id"]:
        raise SmokeFailure("Impacto e historial discrepan sobre el precio actual.")
    current_amount = history["versions"][current_id]
    with localcontext() as context:
        context.prec = 64
        expected_after = current_amount * INGREDIENT_LITRES / PACKAGE_QUANTITY
    after = _sheet_total(payload.get("after"), status="complete", label="impact.after")
    if after != expected_after or after != Decimal("2.56"):
        raise SmokeFailure("El impacto actual de 400 mL no es 2.56 EUR.")

    previous_id = payload.get("previous_price_id")
    if previous_id is None:
        before = _sheet_total(payload.get("before"), status="incomplete", label="impact.before")
        if payload.get("difference") is not None or payload.get("difference_per_serving") is not None:
            raise SmokeFailure("Un precio anterior desconocido produjo una diferencia numérica.")
        return {"after": after, "before": before, "difference": None}

    previous_id = _positive_id(previous_id, "impact.previous_price_id")
    if previous_id == current_id:
        raise SmokeFailure("Las versiones anterior y actual del impacto son la misma.")
    if previous_id not in history["versions"]:
        raise SmokeFailure("La versión anterior no aparece en la página de historial validada.")
    previous_amount = history["versions"][previous_id]
    with localcontext() as context:
        context.prec = 64
        expected_before = previous_amount * INGREDIENT_LITRES / PACKAGE_QUANTITY
        expected_difference = expected_after - expected_before
        expected_per_serving = expected_difference / SERVINGS
    before = _sheet_total(payload.get("before"), status="complete", label="impact.before")
    difference = _fixed_decimal(payload.get("difference"), "impact.difference", signed=True)
    difference_per_serving = _fixed_decimal(
        payload.get("difference_per_serving"), "impact.difference_per_serving", signed=True,
    )
    if before != expected_before or difference != expected_difference or difference_per_serving != expected_per_serving:
        raise SmokeFailure("El impacto no coincide con los precios declarados en el historial.")
    return {"after": after, "before": before, "difference": difference}


def _assert_invalid_queries(session: HttpSession, history_path: str) -> dict[str, int]:
    invalid_queries = (
        ("limit_blank", f"{history_path}?limit=&offset=0", (400,)),
        ("offset_blank", f"{history_path}?limit=20&offset=", (400,)),
        ("limit_oversized", f"{history_path}?limit={'9' * 10_000}&offset=0", (400, 414)),
        ("offset_oversized", f"{history_path}?limit=20&offset={'9' * 10_000}", (400, 414)),
    )
    statuses = {}
    for label, path, expected in invalid_queries:
        status, _content_type, _body = session.request(
            "GET", path, csrf=False, expected=expected,
        )
        statuses[label] = status
    return statuses


def _assert_unauthenticated(history_path: str, impact_path: str) -> None:
    session = HttpSession()
    for path in (history_path, impact_path):
        status, _content_type, body = session.request("GET", path, csrf=False, expected=(401, 403))
        if status not in (401, 403) or b"Salsa DEMO" in body or b"Aceite DEMO" in body:
            raise SmokeFailure("Una lectura sin autenticar expuso datos del fixture DEMO.")


def _check_account(session: HttpSession, edition: str, title: str, password: str) -> tuple[dict, tuple[str, str]]:
    session.login(f"{ACCOUNT_PREFIX}{edition}", password)
    _active_space(session, edition, title)
    recipe_id = _demo_recipe(session)
    package = _demo_package(session)
    include_services = edition != "esencial"
    before = _state_snapshots(session, include_services=include_services)

    history_path = f"/api/cuaderno/packages/{package['id']}/prices/"
    history = _validate_history(
        session.json("GET", f"{history_path}?limit=20&offset=0", csrf=False),
        package_id=package["id"],
    )
    impact_path = f"/api/cuaderno/recipes/{recipe_id}/price-impact/?package={package['id']}&servings=4"
    impact = _validate_impact(
        session.json("GET", impact_path, csrf=False),
        recipe_id=recipe_id,
        package_id=package["id"],
        history=history,
    )
    invalid_queries = _assert_invalid_queries(session, history_path)
    _assert_same_snapshots(before, _state_snapshots(session, include_services=include_services))
    session.logout()
    return (
        {
            "mode": "read_only",
            "history_scope": "live_not_database_snapshot",
            "history_count": history["count"],
            "current_price": str(REFERENCE_PRICE),
            "current_cost": str(impact["after"]),
            "previous_price_known": impact["before"] is not None,
            "invalid_queries": invalid_queries,
            "stock_unchanged": True,
            "confirmed_services_check": "unchanged" if include_services else "not_authorized_in_essential",
            "domain_write_requests": 0,
        },
        (history_path, impact_path),
    )


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    editions = {}
    privacy_paths = None
    for edition, title in EDITIONS.items():
        editions[edition], paths = _check_account(HttpSession(), edition, title, password)
        privacy_paths = privacy_paths or paths
    if privacy_paths is None:
        raise SmokeFailure("No hay cuentas DEMO configuradas para validar precios.")
    _assert_unauthenticated(*privacy_paths)
    return {
        "ready": True,
        "accounts_checked": len(editions),
        "mode": "read_only",
        "domain_write_requests": 0,
        "unauthenticated_denied": True,
        "editions": editions,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_PRICES_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_PRICES_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
