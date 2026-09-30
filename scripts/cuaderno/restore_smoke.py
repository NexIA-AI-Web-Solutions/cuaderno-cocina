"""Read-only functional fingerprint for the explicitly local demo/restore DB."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recipes.settings")


def _require_keys(value, keys, label):
    if not isinstance(value, dict) or not set(keys).issubset(value):
        raise ValueError(f"{label} no conserva el envelope esperado.")


def validate_ingredient_yields(document, recipe_id, edition):
    _require_keys(document, {"recipe_id", "edition", "can_edit", "ingredients"}, "Mermas")
    if (
        document["recipe_id"] != recipe_id
        or document["edition"] != edition
        or type(document["can_edit"]) is not bool
        or not isinstance(document["ingredients"], list)
    ):
        raise ValueError("Mermas no corresponden a la receta/edición restaurada.")
    if edition == "esencial" and document["can_edit"]:
        raise ValueError("Esencial permite consultar mermas, no editarlas.")
    for row in document["ingredients"]:
        _require_keys(
            row,
            {"id", "food_name", "amount", "unit", "quantity_basis", "yield_ratio", "is_subrecipe"},
            "Ingrediente con merma",
        )
    return document


def validate_stock_minimums(document):
    _require_keys(document, {"edition", "household", "locations", "items"}, "Mínimos")
    if document["edition"] != "integral" or not isinstance(document["locations"], list) or not isinstance(document["items"], list):
        raise ValueError("Mínimos no conservan el envelope Integral.")
    _require_keys(document["household"], {"id", "name"}, "Hogar de mínimos")
    for location in document["locations"]:
        _require_keys(location, {"id", "name"}, "Ubicación de mínimos")
    for row in document["items"]:
        _require_keys(
            row,
            {
                "id", "household", "food", "food_name", "unit", "unit_name", "quantity",
                "location", "location_name", "updated_by", "updated_at",
            },
            "Metadata de mínimo",
        )
    return document


def validate_replenishment(document):
    _require_keys(document, {"items"}, "Reposición")
    if not isinstance(document["items"], list):
        raise ValueError("Reposición no contiene una lista de propuestas.")
    return document


def validate_preparation(document, service_id, state):
    _require_keys(document, {"service_id", "state", "can_edit", "revision", "items"}, "Preparación")
    positive_id = lambda value: type(value) is int and value > 0
    if (not positive_id(document["service_id"]) or document["service_id"] != service_id
            or document["state"] != state or state not in {"draft", "confirmed", "produced", "cancelled"}
            or type(document["can_edit"]) is not bool or not isinstance(document["items"], list)
            or not isinstance(document["revision"], str)
            or re.fullmatch(r"[0-9a-f]{64}", document["revision"]) is None):
        raise ValueError("Preparación no corresponde al servicio/estado restaurado.")
    if document["can_edit"] != (state == "confirmed" and bool(document["items"])):
        raise ValueError("Preparación histórica/vacía o terminal no debe aparecer editable.")
    if state == "draft" and document["items"]:
        raise ValueError("Un borrador no puede contener pasos congelados antes de confirmar.")
    seen = set()
    for position, item in enumerate(document["items"]):
        _require_keys(item, {
            "id", "source_step_id", "position", "recipe_id", "name", "instruction",
            "checked", "checked_at", "updated_by",
        }, "Tarea congelada")
        if (not positive_id(item["id"]) or item["id"] in seen
                or type(item["position"]) is not int or item["position"] != position
                or not positive_id(item["recipe_id"])
                or (item["source_step_id"] is not None and not positive_id(item["source_step_id"]))
                or not isinstance(item["name"], str) or not isinstance(item["instruction"], str)
                or type(item["checked"]) is not bool
                or (item["updated_by"] is not None and not positive_id(item["updated_by"]))):
            raise ValueError("Una tarea restaurada perdió identidad, texto o metadatos.")
        seen.add(item["id"])
        if item["checked"]:
            if not isinstance(item["checked_at"], str) or not positive_id(item["updated_by"]):
                raise ValueError("Una tarea marcada necesita fecha consciente y autor.")
            try:
                checked_at = datetime.fromisoformat(item["checked_at"])
            except ValueError as exc:
                raise ValueError("La fecha de preparación restaurada no es válida.") from exc
            if checked_at.utcoffset() is None:
                raise ValueError("La fecha de preparación necesita zona horaria.")
        elif item["checked_at"] is not None:
            raise ValueError("Una tarea sin marcar no conserva fecha de marcado.")
    return document


def payload_sha256(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection, transaction
    from django.test import Client
    from django_scopes import scopes_disabled
    from cookbook.models import InventoryEntry, Recipe, UserSpace
    from cuaderno.models import PurchaseOrder, StockMovement
    from cuaderno.services.costing import cost_recipe, visible_recipes

    database = connection.settings_dict["NAME"]
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"} or not (
        database == "cuaderno_demo" or database.startswith("cuaderno_restore_")
    ):
        raise ValueError("Smoke restringido a la base demo o destino restore nuevo.")
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
    with transaction.atomic(), scopes_disabled():
        users = list(get_user_model().objects.filter(username__in=["demo-esencial", "demo-profesional", "demo-integral"]).order_by("pk"))
        if not users:
            users = [get_user_model().objects.get(username="demo")]
        password = os.environ.get("CUADERNO_DEMO_PASSWORD")
        profiles, costs, finances, services = [], [], [], []
        ingredient_yields, stock_minimums, replenishments, preparations = [], [], [], []
        for user in users:
            if not password or not user.check_password(password):
                raise ValueError("La contraseña DEMO no autentica el usuario restaurado.")
            client = Client()
            if not client.login(username=user.username, password=password):
                raise ValueError("Login Django del destino restaurado falló.")
            response = client.get("/api/cuaderno/edition/")
            if response.status_code != 200:
                raise ValueError("Perfil/permiso del usuario restaurado no accesible.")
            membership = UserSpace.objects.get(user=user, active=True)
            profiles.append({"user": user.pk, "space": membership.space_id, "edition": response.json()})
            edition = response.json()["edition"]
            for recipe in visible_recipes(user, membership.space).order_by("pk"):
                costs.append({"recipe": recipe.pk, "cost": cost_recipe(recipe, recipe.servings, user=user)})
                api = client.get(f"/api/cuaderno/recipes/{recipe.pk}/cost/")
                if api.status_code != 200:
                    raise ValueError("Escandallo restaurado no accesible por API.")
                yields_api = client.get(f"/api/cuaderno/recipes/{recipe.pk}/ingredient-yields/")
                if yields_api.status_code != 200:
                    raise ValueError("Mermas restauradas no accesibles por API.")
                ingredient_yields.append({
                    "user": user.pk,
                    "recipe": recipe.pk,
                    "document": validate_ingredient_yields(yields_api.json(), recipe.pk, edition),
                })
                if edition in {"profesional", "integral"}:
                    finance = client.get(f"/api/cuaderno/recipes/{recipe.pk}/finance/")
                    if finance.status_code != 200:
                        raise ValueError("Propiedades financieras restauradas no accesibles por API.")
                    finances.append({"recipe": recipe.pk, "finance": finance.json()})
            if edition in {"profesional", "integral"}:
                from cuaderno.models import ServicePlan
                for service in ServicePlan.objects.filter(space=membership.space).order_by("pk"):
                    api = client.get(f"/api/cuaderno/services/{service.pk}/")
                    if api.status_code != 200:
                        raise ValueError("Servicio restaurado no accesible por API.")
                    services.append({"user": user.pk, "service": service.pk, "document": api.json()})
                    preparation = client.get(f"/api/cuaderno/services/{service.pk}/preparation/")
                    if preparation.status_code != 200:
                        raise ValueError("Preparación restaurada no accesible por API.")
                    preparations.append({
                        "user": user.pk, "service": service.pk,
                        "document": validate_preparation(preparation.json(), service.pk, service.state),
                    })
            if edition == "integral":
                minimums_api = client.get("/api/cuaderno/stock-minimums/")
                if minimums_api.status_code != 200:
                    raise ValueError("Mínimos restaurados no accesibles por API.")
                stock_minimums.append({
                    "user": user.pk,
                    "space": membership.space_id,
                    "document": validate_stock_minimums(minimums_api.json()),
                })
                balances_before = list(
                    InventoryEntry.objects.filter(space=membership.space)
                    .order_by("pk").values_list("pk", "amount")
                )
                orders_before = list(PurchaseOrder.objects.filter(space=membership.space).order_by("pk").values())
                replenishment_api = client.post(
                    "/api/cuaderno/replenishment/", data={}, content_type="application/json"
                )
                if replenishment_api.status_code != 200:
                    raise ValueError("Consulta de reposición restaurada no accesible por API.")
                balances_after = list(
                    InventoryEntry.objects.filter(space=membership.space)
                    .order_by("pk").values_list("pk", "amount")
                )
                orders_after = list(PurchaseOrder.objects.filter(space=membership.space).order_by("pk").values())
                if balances_after != balances_before or orders_after != orders_before:
                    raise ValueError("Consultar reposición alteró saldos o pedidos restaurados.")
                replenishments.append({
                    "user": user.pk,
                    "space": membership.space_id,
                    "document": validate_replenishment(replenishment_api.json()),
                })
            foreign = Recipe.objects.exclude(space=membership.space).first()
            if foreign and client.get(f"/api/cuaderno/recipes/{foreign.pk}/cost/").status_code != 404:
                raise ValueError("La API restaurada expone una receta de otro Space.")
        stocks = list(InventoryEntry.objects.order_by("pk").values_list("pk", "space_id", "food_id", "unit_id", "amount"))
        denied = Client().get("/api/cuaderno/edition/")
        if denied.status_code == 200:
            raise ValueError("La API permitió lectura anónima del perfil.")
        for entry in InventoryEntry.objects.all():
            last = StockMovement.objects.filter(entry=entry).order_by("-pk").first()
            if last and last.balance_after is not None and last.balance_after != entry.amount:
                raise ValueError("La proyección de saldo no coincide con el último movimiento restaurado.")
        payload = {
            "profiles": profiles,
            "costs": costs,
            "stocks": stocks,
            "finances": finances,
            "services": services,
            "ingredient_yields": ingredient_yields,
            "stock_minimums": stock_minimums,
            "replenishments": replenishments,
            "preparations": preparations,
        }
        digest = payload_sha256(payload)
        transaction.set_rollback(True)
    print("CUADERNO_SMOKE=" + json.dumps({"passed": True, "sha256": digest, "login": True, "anonymous_denied": True,
                                          "users_verified": len(users), "costs_verified": len(costs), "balances_verified": len(stocks),
                                         "finances_verified": len(finances), "services_verified": len(services),
                                         "ingredient_yields_verified": len(ingredient_yields),
                                         "stock_minimums_verified": len(stock_minimums),
                                         "replenishments_verified": len(replenishments),
                                         "preparations_verified": len(preparations),
                                         "preparation_items_verified": sum(len(row["document"]["items"]) for row in preparations)}))


if __name__ == "__main__":
    main()
