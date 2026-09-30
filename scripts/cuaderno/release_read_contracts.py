#!/usr/bin/env python3
"""Smoke HTTP solo lectura de rol, alérgenos y aislamiento entre Spaces DEMO."""

from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

if __package__:
    from .release_http_smoke import ACCOUNT_PREFIX, EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment
    from .release_reserves_smoke import _demo_package
    from .release_yields_smoke import _active_space, _assert_same_snapshots, _complete_items, _demo_recipe, _state_snapshots
else:
    from release_http_smoke import ACCOUNT_PREFIX, EDITIONS, HttpSession, SmokeFailure, _guard_base_url, _guard_environment
    from release_reserves_smoke import _demo_package
    from release_yields_smoke import _active_space, _assert_same_snapshots, _complete_items, _demo_recipe, _state_snapshots


ROLE_KEYS = {
    "code", "label", "space", "can_operate_cuaderno", "can_manage_edition",
    "native_permissions_preserved",
}
ALLERGEN_KEYS = {"scope", "assessment", "undeclared_means_absent", "unknown_ingredients", "foods"}
SCOPE_KEYS = {"type", "id", "name"}
FOOD_KEYS = {"id", "name", "declarations"}
DECLARATION_KEYS = {"id", "name", "state"}
MAX_SAFE_ID = 9007199254740991


def _safe_id(value, label: str) -> int:
    if type(value) is not int or not 0 < value <= MAX_SAFE_ID:
        raise SmokeFailure(f"{label} no es un identificador JSON seguro.")
    return value


def _safe_name(value, label: str) -> str:
    if (not isinstance(value, str) or not 0 < len(value) <= 128
            or any(ord(character) < 32 or 127 <= ord(character) <= 159
                   or 0xD800 <= ord(character) <= 0xDFFF for character in value)):
        raise SmokeFailure(f"{label} no es un nombre textual seguro.")
    return value


def _validate_operational_role(payload, *, edition: str, space_id: int):
    _safe_id(space_id, "Space activo")
    if not isinstance(payload, dict) or payload.get("edition") != edition:
        raise SmokeFailure(f"La edición de demo-{edition} no coincide con su sesión.")
    role = payload.get("operational_role")
    if not isinstance(role, dict) or set(role) != ROLE_KEYS:
        raise SmokeFailure("El rol operativo tiene campos desconocidos o incompletos.")
    if (
        role.get("code") != "admin"
        or role.get("label") != "Responsable"
        or role.get("space") != space_id
        or role.get("can_operate_cuaderno") is not True
        or role.get("can_manage_edition") is not True
        or role.get("native_permissions_preserved") is not True
    ):
        raise SmokeFailure("La cuenta DEMO no conserva el rol Responsable de su Space activo.")
    return role


def _validate_allergens(payload, *, scope_type: str, scope_id: int, scope_name: str):
    if scope_type not in {"food", "recipe"}:
        raise SmokeFailure("El alcance de alérgenos no está soportado.")
    _safe_id(scope_id, "allergens.scope.id")
    _safe_name(scope_name, "allergens.scope.name")
    if not isinstance(payload, dict) or set(payload) != ALLERGEN_KEYS:
        raise SmokeFailure("La ficha de alérgenos tiene campos desconocidos o incompletos.")
    scope = payload.get("scope")
    if (not isinstance(scope, dict) or set(scope) != SCOPE_KEYS
            or scope.get("type") != scope_type or scope.get("id") != scope_id
            or scope.get("name") != scope_name):
        raise SmokeFailure("La ficha de alérgenos no corresponde al recurso solicitado.")
    if payload.get("assessment") not in {"unknown", "declared"}:
        raise SmokeFailure("La evaluación de alérgenos no es declarada ni desconocida.")
    if payload.get("undeclared_means_absent") is not False or type(payload.get("unknown_ingredients")) is not bool:
        raise SmokeFailure("La ficha infiere ausencia o no declara su cobertura desconocida.")
    foods = payload.get("foods")
    if not isinstance(foods, list) or len(foods) > 10000:
        raise SmokeFailure("La ficha de alérgenos no contiene una lista acotada de alimentos.")
    food_ids, any_declared = [], False
    for food in foods:
        if not isinstance(food, dict) or set(food) != FOOD_KEYS:
            raise SmokeFailure("Un alimento de la ficha tiene campos desconocidos o incompletos.")
        food_ids.append(_safe_id(food.get("id"), "allergens.food.id"))
        _safe_name(food.get("name"), "allergens.food.name")
        declarations = food.get("declarations")
        if not isinstance(declarations, list) or len(declarations) > 10000:
            raise SmokeFailure("Las declaraciones de un alimento no forman una lista acotada.")
        declaration_ids = []
        for declaration in declarations:
            if not isinstance(declaration, dict) or set(declaration) != DECLARATION_KEYS:
                raise SmokeFailure("Una declaración tiene campos desconocidos o incompletos.")
            declaration_ids.append(_safe_id(declaration.get("id"), "allergens.declaration.id"))
            _safe_name(declaration.get("name"), "allergens.declaration.name")
            if declaration.get("state") not in {"unknown", "declared"}:
                raise SmokeFailure("Una declaración inventa un estado seguro o ausente.")
            any_declared = any_declared or declaration["state"] == "declared"
        if len(declaration_ids) != len(set(declaration_ids)):
            raise SmokeFailure("Una declaración aparece duplicada para el mismo alimento.")
    if len(food_ids) != len(set(food_ids)):
        raise SmokeFailure("Un alimento aparece duplicado en la ficha consolidada.")
    if (payload["assessment"] == "declared") is not any_declared:
        raise SmokeFailure("La evaluación no corresponde a las declaraciones consolidadas.")
    if scope_type == "food" and (
        len(foods) != 1 or food_ids != [scope_id] or foods[0]["name"] != scope_name
        or payload["unknown_ingredients"] is not False
    ):
        raise SmokeFailure("La ficha de alimento no conserva un alcance unívoco.")
    return payload


def _denied_without_names(session, path: str, names: tuple[str, ...]) -> None:
    status, _content_type, body = session.request("GET", path, csrf=False, expected=(404,))
    if status != 404 or any(name.encode("utf-8") in body for name in names):
        raise SmokeFailure("Una lectura ajena filtró metadatos del recurso extranjero.")


def _assert_foreign_reads_denied(session, *, food_id: int, recipe_id: int, package_id: int,
                                 food_name: str, recipe_name: str):
    food_id = _safe_id(food_id, "foreign.food")
    recipe_id = _safe_id(recipe_id, "foreign.recipe")
    package_id = _safe_id(package_id, "foreign.package")
    names = (_safe_name(food_name, "foreign.food_name"), _safe_name(recipe_name, "foreign.recipe_name"))
    for path in (
        f"/api/food/{food_id}/",
        f"/api/recipe/{recipe_id}/",
        f"/api/cuaderno/allergens/?{urlencode({'food': food_id})}",
        f"/api/cuaderno/allergens/?{urlencode({'recipe': recipe_id})}",
        f"/api/cuaderno/packages/{package_id}/prices/?limit=20&offset=0",
    ):
        _denied_without_names(session, path, names)
    rows = _complete_items(
        session.json("GET", "/api/cuaderno/packages/", csrf=False), "Paquetes del Space atacante",
    )
    if len(rows) > 10000:
        raise SmokeFailure("El catálogo de paquetes excede el límite verificable.")
    for row in rows:
        if not isinstance(row, dict):
            raise SmokeFailure("El catálogo de paquetes contiene filas no estructuradas.")
        _safe_id(row.get("id"), "package.id")
        _safe_id(row.get("food"), "package.food")
        _safe_name(row.get("food_name"), "package.food_name")
    if any(
        row.get("id") == package_id or row.get("food") == food_id
        for row in rows
    ):
        raise SmokeFailure("El catálogo de paquetes incluyó identificadores de otro Space.")


def _check_account(edition: str, title: str, password: str) -> tuple[dict, dict, HttpSession, dict]:
    session = HttpSession()
    logged_in = False
    try:
        session.login(f"{ACCOUNT_PREFIX}{edition}", password)
        logged_in = True
        space = _active_space(session, edition, title)
        space_id = _safe_id(space.get("id"), "Space activo")
        role = _validate_operational_role(
            session.json("GET", "/api/cuaderno/edition/", csrf=False), edition=edition, space_id=space_id,
        )
        recipe_id = _demo_recipe(session)
        package = _demo_package(session)
        food_id = _safe_id(package.get("food"), "Aceite DEMO")
        package_id = _safe_id(package.get("id"), "package DEMO")
        include_services = edition != "esencial"
        before = _state_snapshots(session, include_services=include_services)
        food = _validate_allergens(
            session.json("GET", f"/api/cuaderno/allergens/?{urlencode({'food': food_id})}", csrf=False),
            scope_type="food", scope_id=food_id, scope_name="Aceite DEMO",
        )
        recipe = _validate_allergens(
            session.json("GET", f"/api/cuaderno/allergens/?{urlencode({'recipe': recipe_id})}", csrf=False),
            scope_type="recipe", scope_id=recipe_id, scope_name="Salsa DEMO",
        )
        _assert_same_snapshots(before, _state_snapshots(session, include_services=include_services))
        result = {
            "mode": "read_only", "role": role["code"], "role_label": role["label"],
            "food_assessment": food["assessment"], "recipe_assessment": recipe["assessment"],
            "undeclared_means_absent": False, "domain_write_requests": 0,
        }
        resources = {
            "food_id": food_id, "recipe_id": recipe_id, "package_id": package_id,
            "food_name": "Aceite DEMO", "recipe_name": "Salsa DEMO",
        }
        return result, resources, session, before
    except Exception:
        if logged_in:
            try:
                session.logout()
            except Exception:
                pass
        raise


def run() -> dict:
    _guard_base_url()
    password = _guard_environment()
    ready = HttpSession().json("GET", "/health/ready/", csrf=False)
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise SmokeFailure("Readiness no confirma aplicación y BD locales disponibles.")
    owners = {}
    results = {}
    try:
        for edition, title in EDITIONS.items():
            results[edition], resources, session, before = _check_account(edition, title, password)
            owners[edition] = (resources, session, before)
        for attacker_edition, (_own, attacker, _before) in owners.items():
            for owner_edition, (foreign, _owner, _owner_before) in owners.items():
                if attacker_edition != owner_edition:
                    _assert_foreign_reads_denied(attacker, **foreign)
        for edition, (_resources, session, before) in owners.items():
            _assert_same_snapshots(before, _state_snapshots(session, include_services=edition != "esencial"))
    finally:
        original_active = sys.exc_info()[0] is not None
        logout_error = None
        for _resources, session, _before in owners.values():
            try:
                session.logout()
            except Exception as exc:
                if not original_active and logout_error is None:
                    logout_error = exc
        if logout_error is not None:
            raise logout_error
    return {
        "ready": True, "mode": "read_only", "accounts_checked": len(results),
        "cross_space_denied": True, "domain_write_requests": 0, "editions": results,
    }


def main() -> int:
    try:
        result = run()
    except SmokeFailure as exc:
        print(f"CUADERNO_RELEASE_READ_CONTRACTS ERROR: {exc}", file=sys.stderr)
        return 1
    print("CUADERNO_RELEASE_READ_CONTRACTS " + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
