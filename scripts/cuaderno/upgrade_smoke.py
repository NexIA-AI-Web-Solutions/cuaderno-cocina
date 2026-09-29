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
    step = Step.objects.create(space=space, instruction="Synthetic original step")
    step.ingredients.add(Ingredient.objects.create(space=space, food=food, unit=unit, amount=Decimal("0.4")))
    recipe.steps.add(step)
print("PIN_FIXTURE_OK")
'''

UPGRADE_ASSERTIONS = '''
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.utils import timezone
from django_scopes import scopes_disabled
from cookbook.models import Space, UserSpace, Household, InventoryEntry, Food, Unit, Recipe, Step, Ingredient
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
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
    assert recipe.steps.get().instruction == "Synthetic original step"
    ingredient = recipe.steps.get().ingredients.get()
    assert ingredient.amount == Decimal("0.4")
    entry = InventoryEntry.objects.get(space=space)
    assert entry.amount == Decimal("5.125") and entry.inventory_location.household_id == membership.household_id
    assert ingredient.food_id == entry.food_id and ingredient.unit_id == entry.unit_id
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM django_migrations WHERE app='cuaderno' AND name='0013_offer_free_equivalence'")
        assert cursor.fetchone()
    package = PackageFormat.objects.create(space=space, food=entry.food, unit=entry.unit, label="Synthetic 5L", quantity=5)
    PriceVersion.objects.create(space=space, package=package, amount=32, valid_from=timezone.now(), created_by=user)
client = Client()
assert client.login(username=user.username, password="Upgrade-Synthetic-Only!")
cost = client.get(f"/api/cuaderno/recipes/{recipe.pk}/cost/")
assert cost.status_code == 200, cost.content
assert Decimal(cost.json()["total"]) == Decimal("2.56"), cost.content
assert client.get("/api/cuaderno/edition/").json()["edition"] == "esencial"
assert Client().get(f"/api/cuaderno/recipes/{recipe.pk}/cost/").status_code != 200
print("CUADERNO_UPGRADE_OK: native users/roles/Spaces/Household/recipe/private/steps/amounts/stock preserved; cost 2.56 EUR; new migrations applied")
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
