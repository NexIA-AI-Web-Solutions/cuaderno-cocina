#!/usr/bin/env python3
"""Release HTTP smoke for DEMO ingredient-yield editing and isolation."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import (
        EDITIONS,
        HttpSession,
        SmokeFailure,
        _decimal,
        _guard_base_url,
        _guard_environment,
        _items,
    )
    from .release_reserves_smoke import _positive_id, _snapshot
else:
    from release_http_smoke import (
        EDITIONS,
        HttpSession,
        SmokeFailure,
        _decimal,
        _guard_base_url,
        _guard_environment,
        _items,
    )
    from release_reserves_smoke import _positive_id, _snapshot


ACCOUNT_PREFIX = "demo-"
RECIPE_NAME = "Salsa DEMO"
FOOD_NAME = "Aceite DEMO"
INGREDIENT_AMOUNT = Decimal("400")
INGREDIENT_UNIT = "mL"
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
INVENTORY_PATH = "/api/inventory-entry/?" + urlencode({"page_size": "100"})


def _complete_items(payload, label: str) -> list:
    rows = _items(payload)
    if isinstance(payload, dict):
        if (
            type(payload.get("count")) is not int
            or payload["count"] != len(rows)
            or payload.get("next") is not None
            or payload.get("previous") is not None
        ):
            raise SmokeFailure(f"{label} está paginado o tiene un conteo ambiguo.")
    return rows


def _active_space(session: HttpSession, edition: str, title: str) -> dict:
    edition_payload = session.json("GET", "/api/cuaderno/edition/", csrf=False)
    if not isinstance(edition_payload, dict) or edition_payload.get("edition") != edition:
        raise SmokeFailure(f"demo-{edition} no está en la edición esperada.")
    memberships = _items(session.json("GET", "/api/user-space/all_personal/", csrf=False))
    active = [row for row in memberships if isinstance(row, dict) and row.get("active") is True]
    if len(active) != 1:
        raise SmokeFailure(f"demo-{edition} debe tener exactamente un Space activo.")
    space_id = _positive_id(active[0].get("space"), "Space activo")
    space = session.json("GET", f"/api/space/{space_id}/", csrf=False)
    if not isinstance(space, dict) or space.get("name") != f"Cuaderno {title} DEMO":
        raise SmokeFailure(f"El Space activo de demo-{edition} no es el sintético esperado.")
    return space


def _demo_recipe(session: HttpSession) -> int:
    query = urlencode({"query": RECIPE_NAME, "page_size": "100"})
    rows = _complete_items(session.json("GET", f"/api/recipe/?{query}", csrf=False), "Recetas DEMO")
    matches = [row for row in rows if isinstance(row, dict) and row.get("name") == RECIPE_NAME]
    if len(matches) != 1:
        raise SmokeFailure("Salsa DEMO no existe de forma unívoca en el Space activo.")
    return _positive_id(matches[0].get("id"), "Salsa DEMO")


def _yield_fixture(
    payload,
    *,
    recipe_id: int,
    edition: str,
    can_edit: bool,
    expected_basis="gross",
    expected_ratio=None,
    check_policy=True,
) -> tuple[str, dict]:
    if not isinstance(payload, dict):
        raise SmokeFailure("La API de mermas no devolvió un objeto JSON.")
    revision = payload.get("revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise SmokeFailure("La revisión de mermas no es un SHA-256 canónico.")
    if payload.get("recipe_id") != recipe_id or payload.get("edition") != edition:
        raise SmokeFailure("La API de mermas devolvió otra receta o edición.")
    if payload.get("can_edit") is not can_edit:
        raise SmokeFailure("La capacidad de edición de mermas no coincide con la edición.")
    ingredients = payload.get("ingredients")
    if not isinstance(ingredients, list) or len(ingredients) != 1:
        raise SmokeFailure("Salsa DEMO debe contener exactamente una línea sintética.")
    line = ingredients[0]
    if (
        not isinstance(line, dict)
        or type(line.get("id")) is not int
        or line["id"] <= 0
        or line.get("food_name") != FOOD_NAME
        or _decimal(line.get("amount"), "ingredient.amount") != INGREDIENT_AMOUNT
        or line.get("unit") != INGREDIENT_UNIT
        or line.get("is_subrecipe") is not False
    ):
        raise SmokeFailure("La línea Aceite DEMO no coincide con el fixture sintético exacto.")
    if check_policy:
        ratio = line.get("yield_ratio")
        if expected_ratio is None:
            ratio_matches = ratio is None
        else:
            ratio_matches = _decimal(ratio, "yield_ratio") == Decimal(expected_ratio)
        if line.get("quantity_basis") != expected_basis or not ratio_matches:
            raise SmokeFailure("La política de merma DEMO no coincide con el estado esperado.")
    return revision, line


def _cost_total(session: HttpSession, recipe_id: int, expected: str) -> None:
    payload = session.json(
        "GET", f"/api/cuaderno/recipes/{recipe_id}/cost/?servings=4", csrf=False,
    )
    if not isinstance(payload, dict) or payload.get("status") != "complete":
        raise SmokeFailure("El coste de Salsa DEMO no está completo.")
    if _decimal(payload.get("total"), "cost.total") != Decimal(expected):
        raise SmokeFailure("El coste de Salsa DEMO no coincide con su política de merma.")


def _confirmed_services(payload) -> list:
    if not isinstance(payload, list):
        raise SmokeFailure("La lista de servicios no devolvió su contrato completo.")
    if len(payload) >= 100:
        raise SmokeFailure("La lista de servicios alcanzó el límite 100; el snapshot es ambiguo.")
    if any(not isinstance(row, dict) for row in payload):
        raise SmokeFailure("La lista de servicios contiene filas inválidas.")
    confirmed = [row for row in payload if row.get("state") == "confirmed"]
    identifiers = [_positive_id(row.get("id"), "service.id") for row in confirmed]
    if len(identifiers) != len(set(identifiers)):
        raise SmokeFailure("La lista de servicios confirmados contiene identificadores duplicados.")
    return sorted(confirmed, key=lambda row: row["id"])


def _state_snapshots(session: HttpSession, *, include_services: bool) -> dict:
    if include_services:
        services = _confirmed_services(session.json("GET", "/api/cuaderno/services/", csrf=False))
    else:
        session.request("GET", "/api/cuaderno/services/", csrf=False, expected=(403,))
        services = "not_authorized_in_essential"
    return {"stock": _snapshot(session, INVENTORY_PATH), "services": services}


def _without_wrapper_timestamp(payload):
    if not isinstance(payload, dict) or "timestamp" not in payload:
        return payload
    cleaned = dict(payload)
    del cleaned["timestamp"]
    return cleaned


def _assert_same_snapshots(before: dict, after: dict) -> None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise SmokeFailure("Los snapshots de control no son objetos.")
    if set(before) != {"stock", "services"} or set(after) != {"stock", "services"}:
        raise SmokeFailure("Los snapshots de control están incompletos.")
    normalized_before = {
        "stock": _without_wrapper_timestamp(before.get("stock")),
        "services": before.get("services"),
    }
    normalized_after = {
        "stock": _without_wrapper_timestamp(after.get("stock")),
        "services": after.get("services"),
    }
    if normalized_before != normalized_after:
        raise SmokeFailure("Editar mermas alteró stock o snapshots de servicios confirmados.")


def _write_body(ingredient_id: int, revision: str, basis: str, ratio) -> dict:
    return {
        "ingredient": ingredient_id,
        "quantity_basis": basis,
        "yield_ratio": ratio,
        "revision": revision,
    }


def _reread(session: HttpSession, path: str, recipe_id: int, edition: str, can_edit: bool, **policy):
    payload = session.json("GET", path, csrf=False)
    return _yield_fixture(
        payload, recipe_id=recipe_id, edition=edition, can_edit=can_edit, **policy,
    )


def _restore_original(
    session: HttpSession,
    path: str,
    recipe_id: int,
    edition: str,
    *,
    expected_revision: str | None,
) -> str:
    payload = session.json("GET", path, csrf=False)
    revision, line = _yield_fixture(
        payload, recipe_id=recipe_id, edition=edition, can_edit=True, check_policy=False,
    )
    if line.get("quantity_basis") == "gross" and line.get("yield_ratio") is None:
        return revision
    ratio = line.get("yield_ratio")
    if (
        line.get("quantity_basis") != "net_usable"
        or _decimal(ratio, "yield_ratio") != Decimal("0.8")
    ):
        raise SmokeFailure("La merma cambió a un estado ajeno; no se sobrescribe durante recuperación.")
    if expected_revision is None or revision != expected_revision:
        raise SmokeFailure("La revisión de recuperación no pertenece a este smoke; no se sobrescribe.")
    restored = session.json(
        "PUT", path,
        payload=_write_body(line["id"], revision, "gross", None),
    )
    restored_revision, _ = _yield_fixture(
        restored, recipe_id=recipe_id, edition=edition, can_edit=True,
    )
    return restored_revision


def _check_readonly_essential(session: HttpSession, recipe_id: int, path: str, edition: str) -> dict:
    revision, line = _reread(
        session, path, recipe_id, edition, False, expected_basis="gross", expected_ratio=None,
    )
    body = _write_body(line["id"], revision, "net_usable", "0.8")
    session.request("PUT", path, payload=body, expected=(403,))
    session.request("PUT", path, payload=body, csrf=False, expected=(403,))
    reread_revision, _ = _reread(
        session, path, recipe_id, edition, False, expected_basis="gross", expected_ratio=None,
    )
    if reread_revision != revision:
        raise SmokeFailure("Una escritura Esencial rechazada cambió la revisión de merma.")
    return {"mode": "read_only", "csrf_protected": True}


def _check_editable(session: HttpSession, recipe_id: int, path: str, edition: str) -> dict:
    revision_a, line = _reread(
        session, path, recipe_id, edition, True, expected_basis="gross", expected_ratio=None,
    )
    target = _write_body(line["id"], revision_a, "net_usable", "0.8")
    missing_revision = dict(target)
    del missing_revision["revision"]
    session.request("PUT", path, payload=missing_revision, expected=(428,))
    session.request("PUT", path, payload=target, csrf=False, expected=(403,))
    unchanged_revision, _ = _reread(
        session, path, recipe_id, edition, True, expected_basis="gross", expected_ratio=None,
    )
    if unchanged_revision != revision_a:
        raise SmokeFailure("Una escritura rechazada cambió la revisión de merma.")

    revision_b = None
    revision_a_again = None
    try:
        changed = session.json("PUT", path, payload=target)
        revision_b, changed_line = _yield_fixture(
            changed,
            recipe_id=recipe_id,
            edition=edition,
            can_edit=True,
            expected_basis="net_usable",
            expected_ratio="0.8",
        )
        _cost_total(session, recipe_id, "3.2")
        stale = _write_body(changed_line["id"], revision_a, "gross", None)
        session.request("PUT", path, payload=stale, expected=(409,))
        persisted_revision, _ = _reread(
            session, path, recipe_id, edition, True,
            expected_basis="net_usable", expected_ratio="0.8",
        )
        if persisted_revision != revision_b:
            raise SmokeFailure("El conflicto stale alteró la política o su revisión.")
    finally:
        revision_a_again = _restore_original(
            session, path, recipe_id, edition, expected_revision=revision_b,
        )

    if revision_b is None or len({revision_a, revision_b, revision_a_again}) != 3:
        raise SmokeFailure("El ciclo A-B-A no produjo tres revisiones distintas.")
    _cost_total(session, recipe_id, "2.56")
    return {
        "mode": "optimistic_edit",
        "missing_revision_rejected": True,
        "stale_revision_rejected": True,
        "csrf_protected": True,
        "fixture_restored": True,
    }


def _check_account(session: HttpSession, edition: str, title: str, password: str) -> dict:
    session.login(f"{ACCOUNT_PREFIX}{edition}", password)
    _active_space(session, edition, title)
    recipe_id = _demo_recipe(session)
    path = f"/api/cuaderno/recipes/{recipe_id}/ingredient-yields/"
    can_edit = edition != "esencial"
    _yield_fixture(
        session.json("GET", path, csrf=False),
        recipe_id=recipe_id,
        edition=edition,
        can_edit=can_edit,
    )
    _cost_total(session, recipe_id, "2.56")
    before = _state_snapshots(session, include_services=can_edit)
    if can_edit:
        result = _check_editable(session, recipe_id, path, edition)
    else:
        result = _check_readonly_essential(session, recipe_id, path, edition)
    _assert_same_snapshots(before, _state_snapshots(session, include_services=can_edit))
    session.logout()
    return {
        **result,
        "stock_unchanged": True,
        "confirmed_services_check": "unchanged" if can_edit else "not_authorized_in_essential",
        "audit_check": "not_checked_over_http",
    }


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    editions = {
        edition: _check_account(HttpSession(), edition, title, password)
        for edition, title in EDITIONS.items()
    }
    return {
        "ready": True,
        "accounts_checked": len(editions),
        "yield_edit_cycles": sum(row["mode"] == "optimistic_edit" for row in editions.values()),
        "native_audit_checked": False,
        "editions": editions,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_YIELDS_SMOKE ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_YIELDS_SMOKE " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
