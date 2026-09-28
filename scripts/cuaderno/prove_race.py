"""Two processes consume the last unit. One must win and the balance must stay at zero."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recipes.settings")
import django

django.setup()

from django.contrib.auth import get_user_model
from django_scopes import scopes_disabled

from cookbook.models import InventoryEntry
from cuaderno.models import StockMovement

WORKER = r"""
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
with scopes_disabled():
    row = InventoryEntry.objects.get(pk=entry_id)
    space = row.space
    user = get_user_model().objects.get(username="demo")
try:
    with scope(space=space):
        apply_movement(entry_id=row.id, space=space, user=user, kind="consume", quantity="1", idempotency_key=f"g4-race-{index}")
    print("ok")
except ValidationError:
    print("reject")
except Exception as exc:
    print(type(exc).__name__ + ": " + str(exc))
    sys.exit(1)
"""


def main() -> int:
    with scopes_disabled():
        entry = InventoryEntry.objects.get(pk=1)
        entry.amount = Decimal("1")
        entry.save(update_fields=["amount", "updated_at"])
        StockMovement.objects.filter(idempotency_key__startswith="g4-race-").delete()
    path = Path("/tmp/cuaderno-race.py")
    path.write_text(WORKER, encoding="utf-8")
    host = socket.gethostbyname(os.environ.get("POSTGRES_HOST", "cuaderno-g0-t002-db"))
    env = {**os.environ, "PYTHONPATH": "/opt/recipes", "PYTHONUNBUFFERED": "1", "POSTGRES_HOST": host}
    procs = [
        subprocess.Popen(
            ["/opt/recipes/venv/bin/python", str(path), str(i), "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for i in range(2)
    ]
    outcomes = []
    for proc in procs:
        out, err = proc.communicate(timeout=180)
        line = (out.strip().splitlines() or ["empty"])[-1]
        outcomes.append(line if proc.returncode == 0 else f"{line} rc={proc.returncode} {err[-300:]}")
    entry.refresh_from_db()
    print({"outcomes": outcomes, "amount": format(entry.amount, "f"), "db_host": host})
    ok = outcomes.count("ok") == 1 and outcomes.count("reject") == 1 and entry.amount == Decimal("0")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
