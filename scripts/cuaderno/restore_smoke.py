"""Read-only functional fingerprint for the explicitly local demo/restore DB."""
from __future__ import annotations

import hashlib
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recipes.settings")


def main():
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connection, transaction
    from django.test import Client
    from django_scopes import scopes_disabled
    from cookbook.models import InventoryEntry, Recipe, UserSpace
    from cuaderno.models import StockMovement
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
        profiles, costs = [], []
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
            for recipe in visible_recipes(user, membership.space).order_by("pk"):
                costs.append({"recipe": recipe.pk, "cost": cost_recipe(recipe, recipe.servings, user=user)})
                api = client.get(f"/api/cuaderno/recipes/{recipe.pk}/cost/")
                if api.status_code != 200:
                    raise ValueError("Escandallo restaurado no accesible por API.")
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
        payload = {"profiles": profiles, "costs": costs, "stocks": stocks}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        transaction.set_rollback(True)
    print("CUADERNO_SMOKE=" + json.dumps({"passed": True, "sha256": digest, "login": True, "anonymous_denied": True,
                                         "users_verified": len(users), "costs_verified": len(costs), "balances_verified": len(stocks)}))


if __name__ == "__main__":
    main()
