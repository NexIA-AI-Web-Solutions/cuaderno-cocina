"""Upgrade an untouched Tandoor pin in a NEW isolated synthetic PostgreSQL."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PIN_IMAGE = "cuaderno-g0-t002-app:f77a459f"
PIN_IMAGE_ID = "sha256:68946d4df1351cf5b30c7c606243856d65681439d6db4436baed9298d88cea8b"

PIN_FIXTURE = '''
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django_scopes import scopes_disabled
from cookbook.models import Space, UserSpace, Household, InventoryLocation, InventoryEntry, Food, Unit, Recipe, Step, Ingredient
with scopes_disabled():
    space = Space.objects.create(name="Synthetic pin upgrade")
    user = get_user_model().objects.create_user(username="synthetic-upgrade", password="Upgrade-Synthetic-Only!")
    household = Household.objects.create(space=space, name="Synthetic team")
    membership = UserSpace.objects.create(user=user, space=space, household=household, active=True)
    membership.groups.add(Group.objects.get_or_create(name="admin")[0])
    unit = Unit.objects.create(space=space, name="L")
    food = Food.add_root(space=space, name="Synthetic oil")
    location = InventoryLocation.objects.create(space=space, household=household, created_by=user, name="Synthetic store")
    InventoryEntry.objects.create(space=space, food=food, unit=unit, inventory_location=location, created_by=user, amount=Decimal("5.125"))
    recipe = Recipe.objects.create(space=space, created_by=user, name="Synthetic pin recipe", private=True, servings=4)
    step = Step.objects.create(
        space=space,
        name="Synthetic canonical preparation",
        instruction="Synthetic original step",
    )
    step.ingredients.add(Ingredient.objects.create(space=space, food=food, unit=unit, amount=Decimal("0.4")))
    recipe.steps.add(step)
print("PIN_FIXTURE_OK")
'''

UPGRADE_ASSERTIONS = '''
import hashlib
import json
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.utils import timezone
from django_scopes import scopes_disabled
from cookbook.models import Space, UserSpace, Household, InventoryEntry, Food, Unit, Recipe, Step, Ingredient
from cuaderno.models import PackageFormat, PriceVersion, ServicePreparationItem, SpaceProfile
settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]
assert connection.settings_dict["NAME"].startswith("cuaderno_upgrade_")
with scopes_disabled():
    space = Space.objects.get(name="Synthetic pin upgrade")
    user = get_user_model().objects.get(username="synthetic-upgrade")
    assert user.check_password("Upgrade-Synthetic-Only!")
    membership = UserSpace.objects.get(space=space, user=user, active=True)
    assert membership.household.name == "Synthetic team"
    assert set(membership.groups.values_list("name", flat=True)) == {"admin"}
    recipe = Recipe.objects.get(space=space, name="Synthetic pin recipe")
    assert recipe.private and recipe.created_by_id == user.pk and recipe.servings == 4
    recipe_updated_at = recipe.updated_at
    step = recipe.steps.get()
    assert step.name == "Synthetic canonical preparation"
    assert step.instruction == "Synthetic original step"
    ingredient = step.ingredients.get()
    assert ingredient.amount == Decimal("0.4")
    assert ingredient.quantity_basis == "gross" and ingredient.yield_ratio is None
    entry = InventoryEntry.objects.get(space=space)
    assert entry.amount == Decimal("5.125") and entry.inventory_location.household_id == membership.household_id
    assert ingredient.food_id == entry.food_id and ingredient.unit_id == entry.unit_id
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='cuaderno' AND name='0015_stockminimum'")
        assert cursor.fetchone()
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='cuaderno' AND name='0016_servicepreparationitem'")
        assert cursor.fetchone()
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='cookbook' AND name='0243_ingredient_yield_policy'")
        assert cursor.fetchone()
    assert ServicePreparationItem._meta.db_table in connection.introspection.table_names()
    assert ServicePreparationItem.objects.count() == 0
    package = PackageFormat.objects.create(space=space, food=entry.food, unit=entry.unit, label="Synthetic 5L", quantity=5)
    PriceVersion.objects.create(space=space, package=package, amount=32, valid_from=timezone.now(), created_by=user)
client = Client()
assert client.login(username=user.username, password="Upgrade-Synthetic-Only!")
cost = client.get(f"/api/cuaderno/recipes/{recipe.pk}/cost/")
assert cost.status_code == 200, cost.content
assert Decimal(cost.json()["total"]) == Decimal("2.56"), cost.content
assert client.get("/api/cuaderno/edition/").json()["edition"] == "esencial"
assert Client().get(f"/api/cuaderno/recipes/{recipe.pk}/cost/").status_code != 200

edition = client.put(
    "/api/cuaderno/edition/",
    data=json.dumps({"edition": "profesional", "price_policy": "net"}),
    content_type="application/json",
)
assert edition.status_code == 200, edition.content
assert edition.json()["edition"] == "profesional"

finance_url = f"/api/cuaderno/recipes/{recipe.pk}/finance/?servings=4"
finance_before = client.get(finance_url)
assert finance_before.status_code == 200, finance_before.content
financial_hash = hashlib.sha256(json.dumps(
    finance_before.json()["finance"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest()
assert len(financial_hash) == 64

service = client.post(
    "/api/cuaderno/services/",
    data=json.dumps({
        "title": "Synthetic private preparation",
        "covers": "4",
        "service_date": timezone.localdate().isoformat(),
        "recipe": recipe.pk,
    }),
    content_type="application/json",
)
assert service.status_code == 201, service.content
service_payload = service.json()
assert service_payload["state"] == "draft" and service_payload["stock_changed"] is False
service_id = service_payload["id"]
confirmed = client.post(
    f"/api/cuaderno/services/{service_id}/",
    data=json.dumps({"action": "confirm"}),
    content_type="application/json",
)
assert confirmed.status_code == 200, confirmed.content
assert confirmed.json()["state"] == "confirmed"
assert confirmed.json()["stock_changed"] is False
assert confirmed.json()["household"] == membership.household_id
assert confirmed.json()["snapshot"]["recipe_id"] == recipe.pk

preparation_url = f"/api/cuaderno/services/{service_id}/preparation/"
preparation = client.get(preparation_url)
assert preparation.status_code == 200, preparation.content
initial = preparation.json()
assert initial["service_id"] == service_id and initial["state"] == "confirmed" and initial["can_edit"] is True
assert len(initial["revision"]) == 64 and len(initial["items"]) == 1
item = initial["items"][0]
assert item["source_step_id"] == step.pk and item["recipe_id"] == recipe.pk and item["position"] == 0
assert item["name"] == "Synthetic canonical preparation"
assert item["instruction"] == "Synthetic original step"
assert item["checked"] is False and item["checked_at"] is None and item["updated_by"] is None

checked_response = client.put(
    preparation_url,
    data=json.dumps({"item": item["id"], "checked": True, "revision": initial["revision"]}),
    content_type="application/json",
)
assert checked_response.status_code == 200, checked_response.content
checked = checked_response.json()
assert checked["revision"] != initial["revision"]
assert checked["items"][0]["checked"] is True
assert checked["items"][0]["checked_at"] is not None
assert checked["items"][0]["updated_by"] == user.pk

stale = client.put(
    preparation_url,
    data=json.dumps({"item": item["id"], "checked": False, "revision": initial["revision"]}),
    content_type="application/json",
)
assert stale.status_code == 409, stale.content
assert client.get(preparation_url).json() == checked
noop = client.put(
    preparation_url,
    data=json.dumps({"item": item["id"], "checked": True, "revision": checked["revision"]}),
    content_type="application/json",
)
assert noop.status_code == 200 and noop.json() == checked, noop.content

with scopes_disabled():
    recipe.refresh_from_db()
    step.refresh_from_db()
    ingredient.refresh_from_db()
    entry.refresh_from_db()
    assert recipe.private and recipe.created_by_id == user.pk and recipe.servings == 4
    assert recipe.updated_at == recipe_updated_at
    assert step.name == "Synthetic canonical preparation" and step.instruction == "Synthetic original step"
    assert ingredient.amount == Decimal("0.4") and ingredient.food_id == entry.food_id and ingredient.unit_id == entry.unit_id
    assert entry.amount == Decimal("5.125") and entry.inventory_location.household_id == membership.household_id
finance_after = client.get(finance_url)
assert finance_after.status_code == 200, finance_after.content
assert hashlib.sha256(json.dumps(
    finance_after.json()["finance"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest() == financial_hash
print("CUADERNO_UPGRADE_OK: native users/roles/Spaces/Household/private recipe/Step/amounts/stock and finance hash preserved; migration 0016 empty then persistent preparation check/stale/noop verified")
'''


def main():
    if os.environ.get("CUADERNO_ENV") not in {"local", "test", "development"}:
        raise ValueError("Solo un entorno local aislado; nunca datos reales.")
    password = uuid.uuid4().hex

    def run(argv, *, check=True):
        result = subprocess.run(argv, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
        print(result.stdout.replace(password, "[REDACTED]"), end="")
        if check and result.returncode:
            raise RuntimeError(f"Comando fallido (exit={result.returncode}); recursos sintéticos retenidos.")
        return result

    pin = run(["docker", "image", "inspect", PIN_IMAGE, "--format", "{{.Id}}"])
    if pin.stdout.strip() != PIN_IMAGE_ID:
        raise ValueError("Imagen pin no coincide con baseline intacto.")
    release = run(["docker", "image", "inspect", "cuaderno-cocina:local", "--format", "{{.Id}}"])
    release_image = release.stdout.strip()
    if not release_image.startswith("sha256:") or len(release_image) != 71:
        raise ValueError("Identidad de imagen release no válida.")
    suffix = uuid.uuid4().hex[:12]
    namespace = f"cuaderno-upgrade-{suffix}"
    database = f"cuaderno_upgrade_{suffix}"
    db_container = f"{namespace}-db"
    run(["docker", "network", "create", namespace])
    run(["docker", "run", "-d", "--name", db_container, "--network", namespace,
         "-e", "POSTGRES_USER=upgrade_runner", "-e", f"POSTGRES_PASSWORD={password}",
         "-e", f"POSTGRES_DB={database}", "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"])
    for _ in range(60):
        ready = run(["docker", "exec", db_container, "pg_isready", "-U", "upgrade_runner", "-d", database], check=False)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("PostgreSQL sintético no listo.")
    environment = ["-e", "DATABASE_URL=", "-e", "DB_ENGINE=django.db.backends.postgresql", "-e", f"POSTGRES_HOST={db_container}",
                   "-e", "POSTGRES_USER=upgrade_runner", "-e", f"POSTGRES_PASSWORD={password}",
                   "-e", f"POSTGRES_DB={database}", "-e", "SECRET_KEY=isolated-upgrade-synthetic-secret",
                   "-e", "DISABLE_EXTERNAL_CONNECTORS=1"]
    preflight = (
        "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','recipes.settings'); "
        "from django.conf import settings; database=settings.DATABASES['default']; "
        "assert database['ENGINE']=='django.db.backends.postgresql'; "
        f"assert database['HOST']=={db_container!r}; assert database['NAME']=={database!r}; "
        "print('UPGRADE_PREFLIGHT_OK: exact isolated host/database verified before migrations')"
    )
    for phase, image, source in (("pin", PIN_IMAGE_ID, PIN_FIXTURE), ("release", release_image, UPGRADE_ASSERTIONS)):
        container = f"{namespace}-{phase}"
        run(["docker", "run", "--name", f"{container}-preflight", "--network", namespace, *environment,
             "--entrypoint", "/opt/recipes/venv/bin/python", image, "-c", preflight])
        run(["docker", "create", "--name", container, "--network", namespace, *environment,
             "--entrypoint", "/opt/recipes/venv/bin/python", image, "manage.py", "migrate", "--noinput"])
        run(["docker", "start", "-a", container])
        # A separate shell container uses the same newly created, exclusively synthetic database.
        run(["docker", "run", "--name", f"{container}-assert", "--network", namespace, *environment,
             "--entrypoint", "/opt/recipes/venv/bin/python", image, "manage.py", "shell", "-c", source])
    print(f"Retained isolated upgrade: network={namespace}, DB={database}, container={db_container}. No volumes removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
