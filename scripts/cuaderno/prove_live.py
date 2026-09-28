"""Exercise the live demo database through Django's client. Leaves synthetic rows."""

from __future__ import annotations

import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recipes.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django_scopes import scope, scopes_disabled

from cookbook.helper.permission_helper import create_space_for_user
from cookbook.models import Food, Household, InventoryEntry, InventoryLocation, Recipe, Unit
from cuaderno.models import PriceVersion, SpaceProfile, StockMovement

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
settings.CSRF_TRUSTED_ORIGINS = [*settings.CSRF_TRUSTED_ORIGINS, "http://testserver"]

User = get_user_model()
failures: list[str] = []
report: dict = {}


def expect(name: str, ok: bool, detail):
    report[name] = {"ok": bool(ok), "detail": detail}
    if not ok:
        failures.append(name)
        print(f"FAIL {name}: {detail}", file=sys.stderr)
    else:
        print(f"OK   {name}")


def main() -> int:
    demo = User.objects.get(username="demo")
    client = Client()
    client.raise_request_exception = False
    client.force_login(demo)

    with scopes_disabled():
        space = demo.userspace_set.get(active=True).space
        recipe = Recipe.objects.get(pk=1, space=space)
        servings_before = recipe.servings

    cost = client.get("/api/cuaderno/recipes/1/cost/?servings=1")
    body = cost.json() if cost.status_code == 200 else cost.content.decode()
    expect("cost_recipe", cost.status_code == 200 and body.get("saved_recipe") is False and body.get("status") == "complete", body)
    recipe.refresh_from_db()
    expect("cost_does_not_save_recipe", recipe.servings == servings_before, str(recipe.servings))

    switched = client.put(
        "/api/cuaderno/edition/",
        data=json.dumps({"edition": "esencial", "price_policy": "net", "target_food_cost_ratio": "0.30"}),
        content_type="application/json",
    )
    expect("edition_esencial", switched.status_code == 200 and switched.json().get("net_profit") is None, switched.content.decode()[:300])

    blocked = client.post(
        "/api/cuaderno/movements/",
        data=json.dumps({"entry": 1, "kind": "receipt", "quantity": "1", "idempotency_key": "should-403"}),
        content_type="application/json",
    )
    expect("esencial_blocks_stock", blocked.status_code == 403, blocked.status_code)

    upgraded = client.put(
        "/api/cuaderno/edition/",
        data=json.dumps({"edition": "integral", "price_policy": "gross"}),
        content_type="application/json",
    )
    expect("edition_integral", upgraded.status_code == 200 and upgraded.json()["edition"] == "integral", upgraded.content.decode()[:300])

    with scopes_disabled():
        unit, _ = Unit.objects.get_or_create(name="kg", space=space)
        food = Food.objects.filter(name="Harina G4", space=space).first()
        if food is None:
            food = Food.add_root(name="Harina G4", space=space)
        household, _ = Household.objects.get_or_create(name="Casa G4", space=space)
        location = InventoryLocation.objects.filter(name="Despensa G4", space=space).first()
        if location is None:
            location = InventoryLocation.objects.create(name="Despensa G4", household=household, created_by=demo, space=space)
        entry = InventoryEntry.objects.filter(food=food, space=space).first()
        if entry is None:
            entry = InventoryEntry.objects.create(
                inventory_location=location, amount=Decimal("0"), food=food, unit=unit, created_by=demo, space=space
            )
        else:
            entry.amount = Decimal("0")
            entry.save(update_fields=["amount", "updated_at"])
        StockMovement.objects.filter(entry=entry, reverses__isnull=False).delete()
        StockMovement.objects.filter(entry=entry).delete()

    order = client.post(
        "/api/cuaderno/orders/",
        data=json.dumps({"food": food.id, "unit": unit.id, "quantity": "6", "supplier_name": "Molino demo"}),
        content_type="application/json",
    )
    order_body = order.json() if order.status_code == 201 else order.content.decode()
    expect("order_does_not_move_stock", order.status_code == 201 and order_body.get("stock_unchanged") is True, order_body)

    def post_move(payload):
        return client.post("/api/cuaderno/movements/", data=json.dumps(payload), content_type="application/json")

    first = post_move({"entry": entry.id, "kind": "receipt", "quantity": "5", "idempotency_key": "g4-receipt-5"})
    second = post_move({"entry": entry.id, "kind": "receipt", "quantity": "5", "idempotency_key": "g4-receipt-5"})
    conflict = post_move({"entry": entry.id, "kind": "receipt", "quantity": "9", "idempotency_key": "g4-receipt-5"})
    entry.refresh_from_db()
    with scopes_disabled():
        movement_count = StockMovement.objects.filter(entry=entry, idempotency_key="g4-receipt-5").count()
    expect(
        "idempotent_receipt",
        first.status_code == 201 and second.status_code == 201 and first.json()["movement_id"] == second.json()["movement_id"] and movement_count == 1 and entry.amount == Decimal("5"),
        {"first": first.status_code, "second": second.status_code, "count": movement_count, "amount": format(entry.amount, "f")},
    )
    expect("idempotency_conflict", conflict.status_code == 409 and entry.amount == Decimal("5"), conflict.status_code)

    consume = post_move({"entry": entry.id, "kind": "consume", "quantity": "4", "idempotency_key": "g4-consume-4"})
    entry.refresh_from_db()
    expect("consume_to_one", consume.status_code == 201 and entry.amount == Decimal("1"), format(entry.amount, "f"))

    worker = r"""
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recipes.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django_scopes import scope, scopes_disabled
from cookbook.models import InventoryEntry
from cuaderno.services.ledger import apply_movement
from rest_framework.exceptions import ValidationError
index, entry_id = sys.argv[1], int(sys.argv[2])
import time
with scopes_disabled():
    row = InventoryEntry.objects.get(pk=entry_id)
    space, user = row.space, get_user_model().objects.get(username="demo")
for attempt in range(5):
    try:
        with scope(space=space):
            apply_movement(entry_id=row.id, space=space, user=user, kind="consume", quantity="1", idempotency_key=f"g4-race-{index}")
        print("ok")
        break
    except ValidationError:
        print("reject")
        break
    except Exception as exc:
        if "translate host" in str(exc) and attempt < 4:
            time.sleep(1)
            from django.db import connections
            connections.close_all()
            continue
        print(type(exc).__name__ + ": " + str(exc))
        break
"""
    import socket
    import subprocess
    from pathlib import Path

    script_path = Path("/tmp/cuaderno-race.py")
    script_path.write_text(worker, encoding="utf-8")
    db_host = os.environ.get("POSTGRES_HOST", "cuaderno-g0-t002-db")
    try:
        db_host = socket.gethostbyname(db_host)
    except OSError:
        pass
    env = {**os.environ, "PYTHONPATH": "/opt/recipes", "PYTHONUNBUFFERED": "1", "POSTGRES_HOST": db_host}
    procs = [
        subprocess.Popen(
            ["/opt/recipes/venv/bin/python", str(script_path), str(i), str(entry.id)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for i in range(2)
    ]
    outcomes = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        outcomes.append((out.strip().splitlines() or ["empty"])[-1] + ("" if proc.returncode == 0 else f" rc={proc.returncode} {err[-200:]}"))
    entry.refresh_from_db()
    oks = sum(1 for item in outcomes if item == "ok")
    rejects = sum(1 for item in outcomes if item == "reject")
    expect(
        "concurrent_consume",
        oks == 1 and rejects == 1 and entry.amount == Decimal("0"),
        {"outcomes": outcomes, "amount": format(entry.amount, "f")},
    )
    with scopes_disabled():
        entry.amount = Decimal("0")
        entry.save(update_fields=["amount", "updated_at"])

    waste = post_move({"entry": entry.id, "kind": "waste", "quantity": "1", "idempotency_key": "g4-waste-empty"})
    expect("waste_rejects_negative", waste.status_code == 400, waste.status_code)
    refill = post_move({"entry": entry.id, "kind": "receipt", "quantity": "4", "idempotency_key": "g4-refill"})
    movement_id = refill.json()["movement_id"]
    reversed_move = post_move({"reverse_of": movement_id, "idempotency_key": "g4-reverse-refill"})
    entry.refresh_from_db()
    expect("reverse_restores_balance", reversed_move.status_code == 201 and entry.amount == Decimal("0"), format(entry.amount, "f"))

    with scopes_disabled():
        old_prices = PriceVersion.objects.filter(space=space).count()
    service = client.post(
        "/api/cuaderno/services/",
        data=json.dumps({"title": "Servicio 45", "base_covers": "40", "extra": "10", "cancelled": "5", "recipe": 1}),
        content_type="application/json",
    )
    service_body = service.json() if service.status_code == 201 else service.content.decode()
    expect(
        "service_45_no_stock",
        service.status_code == 201 and Decimal(service_body.get("covers")) == Decimal("45") and service_body.get("stock_changed") is False and service_body.get("payment") is None,
        service_body,
    )
    production = client.post(
        "/api/cuaderno/production/",
        data=json.dumps({"usages": [{"component": "salsa", "quantity": "200"}, {"component": "salsa", "quantity": "100"}]}),
        content_type="application/json",
    )
    produced = production.json() if production.status_code == 200 else production.content.decode()
    expect("shared_sauce", production.status_code == 200 and Decimal(produced.get("needs", {}).get("salsa", "0")) == Decimal("300") and produced.get("stock_changed") is False, produced)
    cycle = client.post(
        "/api/cuaderno/production/",
        data=json.dumps({"start": "A", "edges": {"A": ["B"], "B": ["A"]}, "usages": []}),
        content_type="application/json",
    )
    expect("cycle_rejected", cycle.status_code == 400, cycle.content.decode()[:240])
    allergen = client.post(
        "/api/cuaderno/allergens/",
        data=json.dumps({"food": food.id, "name": "gluten", "state": "unknown"}),
        content_type="application/json",
    )
    allergen_body = allergen.json() if allergen.status_code == 201 else allergen.content.decode()
    expect("allergen_unknown", allergen.status_code == 201 and allergen_body.get("undeclared_means_absent") is False, allergen_body)
    packs = client.post(
        "/api/cuaderno/replenishment/",
        data=json.dumps({"required": "10", "usable_stock": "3", "pack_size": "4", "selling_price": ""}),
        content_type="application/json",
    )
    packs_body = packs.json() if packs.status_code == 200 else packs.content.decode()
    expect(
        "replenishment",
        packs.status_code == 200 and Decimal(packs_body.get("packs")) == Decimal("2") and packs_body.get("food_cost", {}).get("net_profit") is None,
        packs_body,
    )

    with scopes_disabled():
        Recipe.objects.create(name="Privada G5", servings=1, private=True, created_by=demo, space=space)
    exported = client.get("/api/cuaderno/exchange/")
    export_body = exported.json()
    names = [item["name"] for item in export_body.get("recipes", [])]
    expect("export_hides_private", exported.status_code == 200 and "Privada G5" not in names and "price" not in exported.content.decode(), names)
    remote = client.post("/api/cuaderno/exchange/", data=json.dumps({"url": "http://127.0.0.1/secret"}), content_type="application/json")
    expect("import_rejects_url", remote.status_code == 400, remote.status_code)
    imported = client.post(
        "/api/cuaderno/exchange/",
        data=json.dumps({"format": "cuaderno-recipes-v1", "recipes": [{"name": "Importada G2", "servings": "2", "ingredients": [{"food": "Sal G2", "quantity": "5", "unit": "g"}]}]}),
        content_type="application/json",
    )
    expect("import_creates_recipe", imported.status_code == 201 and imported.json().get("created"), imported.content.decode()[:240])

    other, created = User.objects.get_or_create(username="otro-g5", defaults={"email": "otro-g5@example.invalid"})
    if created:
        other.set_password("Otro-Cocina-2026!")
        other.save()
    with scopes_disabled():
        if not other.userspace_set.exists():
            create_space_for_user(other)
    other_client = Client()
    other_client.raise_request_exception = False
    other_client.force_login(other)
    leaked = other_client.get("/api/cuaderno/recipes/1/cost/")
    stolen = other_client.post(
        "/api/cuaderno/movements/",
        data=json.dumps({"entry": entry.id, "kind": "receipt", "quantity": "1", "idempotency_key": "idor"}),
        content_type="application/json",
    )
    expect("other_space_cannot_cost", leaked.status_code in (403, 404), leaked.status_code)
    expect("other_space_cannot_move", stolen.status_code in (403, 404), stolen.status_code)

    csrf = Client(enforce_csrf_checks=True)
    csrf.raise_request_exception = False
    csrf.force_login(demo)
    denied = csrf.post("/api/cuaderno/replenishment/", data=json.dumps({"required": "1", "usable_stock": "0", "pack_size": "1"}), content_type="application/json")
    csrf.get("/api-auth/login/")
    token = csrf.cookies.get("csrftoken")
    token = token.value if token else ""
    allowed = csrf.post(
        "/api/cuaderno/replenishment/",
        data=json.dumps({"required": "1", "usable_stock": "0", "pack_size": "1"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    expect("csrf_blocks_missing_token", denied.status_code == 403 and allowed.status_code == 200, {"denied": denied.status_code, "allowed": allowed.status_code})

    shopping = client.post("/api/shopping-list/", data=json.dumps({"name": "Lista G3"}), content_type="application/json")
    if shopping.status_code == 201:
        list_id = shopping.json()["id"]
        added = client.post(
            "/api/shopping-list-entry/",
            data=json.dumps({"food": {"id": food.id, "name": food.name}, "amount": "2", "checked": False, "shopping_lists": [{"id": list_id}]}),
            content_type="application/json",
        )
        if added.status_code == 201:
            entry_id = added.json()["id"]
            checked = client.patch(f"/api/shopping-list-entry/{entry_id}/", data=json.dumps({"checked": True}), content_type="application/json")
            undone = client.patch(f"/api/shopping-list-entry/{entry_id}/", data=json.dumps({"checked": False}), content_type="application/json")
            expect("shopping_check_undo", checked.status_code == 200 and undone.status_code == 200 and undone.json().get("checked") is False, undone.status_code)
        else:
            expect("shopping_check_undo", False, added.content.decode()[:400])
    else:
        expect("shopping_check_undo", False, shopping.content.decode()[:400])

    started = time.perf_counter()
    with scope(space=space):
        list(StockMovement.objects.filter(space=space).order_by("-created_at")[:20])
    expect("movement_index_query", True, {"seconds": round(time.perf_counter() - started, 4), "rows": "limit 20"})

    with scopes_disabled():
        price_count = PriceVersion.objects.filter(space=space).count()
    expect("prices_not_rewritten", price_count >= old_prices, {"before": old_prices, "after": price_count})
    again = client.get("/api/cuaderno/recipes/1/cost/?servings=1")
    expect("cost_still_complete", again.status_code == 200 and again.json().get("status") == "complete", again.json().get("display"))

    print(json.dumps({"failures": failures, "report": report}, default=str, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(2)
