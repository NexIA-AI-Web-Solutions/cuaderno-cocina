"""Measured PostgreSQL acceptance benchmark for the documented Cuaderno dataset.

Run this module on its own. It intentionally creates a large synthetic fixture in
the Django test database and prints one machine-readable result line prefixed by
``CUADERNO_PERFORMANCE``. Timings use the in-process DRF test client, so they do
not claim browser, Internet, LCP, INP, iPad, or production-host performance.
"""

from __future__ import annotations

import cProfile
import hashlib
import json
import math
import os
import platform
import pstats
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from time import perf_counter, process_time

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import (
    Food,
    Household,
    Ingredient,
    InventoryEntry,
    InventoryLocation,
    MealPlan,
    MealType,
    Recipe,
    SearchFields,
    Space,
    Step,
    Unit,
    UserSpace,
)
from cookbook.version_info import TANDOOR_REF, TANDOOR_VERSION
from cuaderno.models import PackageFormat, PriceVersion, ServicePlan, SpaceProfile, StockMovement


RECIPE_COUNT = 3_000
FOOD_COUNT = 1_500
INGREDIENTS_PER_RECIPE = 15
USER_COUNT = 10
MOVEMENT_COUNT = 100_000
SERVICE_LIST_COUNT = 100
FIXTURE_CHUNK = 5_000
TIMING_REPETITIONS = 7
QUERY_REPETITIONS = 3
CONCURRENT_USERS = 5
CONCURRENT_REPETITIONS = 3


def _percentiles(samples):
    ordered = sorted(samples)
    if not ordered:
        return {"p50_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}

    def nearest_rank(percent):
        return ordered[max(0, math.ceil(percent * len(ordered)) - 1)]

    return {
        "p50_ms": round(nearest_rank(0.50), 3),
        "p95_ms": round(nearest_rank(0.95), 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
    }


def _memory_limit_bytes():
    path = "/sys/fs/cgroup/memory.max"
    try:
        value = open(path, encoding="ascii").read().strip()  # noqa: SIM115 - tiny read-only probe
        return None if value == "max" else int(value)
    except (OSError, ValueError):
        return None


def _rss_facts():
    """Read Linux process memory without adding a measurement dependency."""
    result = {"rss_bytes": None, "rss_peak_bytes": None}
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    result["rss_bytes"] = int(line.split()[1]) * 1024
                elif line.startswith("VmHWM:"):
                    result["rss_peak_bytes"] = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return result


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CuadernoPerformanceAcceptanceTests(TransactionTestCase):
    """One isolated benchmark; TransactionTestCase exposes committed rows to threads."""

    reset_sequences = False
    databases = {"default"}

    def setUp(self):
        if connection.vendor != "postgresql":
            self.fail("La aceptación de rendimiento exige PostgreSQL real; no se sustituye por SQLite.")
        database_name = str(connection.settings_dict.get("NAME") or "")
        if not database_name.lower().startswith("test_"):
            self.fail(f"El benchmark se niega a usar una BD no temporal: {database_name!r}")

        with connection.cursor() as cursor:
            cursor.execute("SHOW jit")
            jit = cursor.fetchone()[0]
        self.assertEqual(jit, "off", "El benchmark exige las opciones de producción TEST_DB_OPTIONS={'options': '-c jit=off'}.")
        started = perf_counter()
        cache.clear()
        with scopes_disabled():
            # TransactionTestCase flushes rows created by data migrations.  Re-seed
            # the native value before user-related lazy SearchPreference creation,
            # especially when this benchmark is run repeatedly with --keepdb.
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.space = Space.objects.create(name="Rendimiento sintético Cuaderno")
            self.household = Household.objects.create(space=self.space, name="Equipo benchmark")
            self.users = self._create_users()
            self.space.created_by = self.users[0]
            self.space.save(update_fields=["created_by"])
            SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.INTEGRAL)
            self.unit = Unit.objects.create(space=self.space, name="kg", base_unit="kg")
            self.foods = self._create_foods()
            self.recipes, self.steps = self._create_recipes_and_steps()
            self._create_ingredients()
            self._create_prices()
            self.entry = self._create_inventory_projection()
            self._create_movements()
            self._create_services()
        self.fixture_ms = round((perf_counter() - started) * 1000, 3)
        self.clients = [self._client_for(user) for user in self.users[:CONCURRENT_USERS]]

    def _create_users(self):
        group, _ = Group.objects.get_or_create(name="user")
        users = []
        for index in range(USER_COUNT):
            user = get_user_model().objects.create_user(username=f"perf-user-{index}")
            membership = UserSpace.objects.create(
                user=user,
                space=self.space,
                household=self.household,
                active=True,
            )
            membership.groups.add(group)
            users.append(user)
        return users

    def _create_foods(self):
        # Food is a Treebeard model: add_root preserves path/depth/numchild.
        return [Food.add_root(space=self.space, name=f"Alimento {index:04d}") for index in range(FOOD_COUNT)]

    def _create_recipes_and_steps(self):
        recipes = Recipe.objects.bulk_create(
            [
                Recipe(
                    space=self.space,
                    name=f"Receta {index:04d}",
                    servings=10,
                    created_by=self.users[index % USER_COUNT],
                )
                for index in range(RECIPE_COUNT)
            ],
            batch_size=FIXTURE_CHUNK,
        )
        steps = Step.objects.bulk_create(
            [Step(space=self.space, name=f"Paso {index:04d}", order=0) for index in range(RECIPE_COUNT)],
            batch_size=FIXTURE_CHUNK,
        )
        Recipe.steps.through.objects.bulk_create(
            [Recipe.steps.through(recipe_id=recipe.pk, step_id=step.pk) for recipe, step in zip(recipes, steps)],
            batch_size=FIXTURE_CHUNK,
        )
        return recipes, steps

    def _create_ingredients(self):
        for offset in range(0, RECIPE_COUNT, 200):
            recipe_slice = self.recipes[offset : offset + 200]
            step_slice = self.steps[offset : offset + 200]
            ingredients = []
            owners = []
            for recipe, step in zip(recipe_slice, step_slice):
                for ingredient_index in range(INGREDIENTS_PER_RECIPE):
                    food = self.foods[(recipe.pk + ingredient_index) % FOOD_COUNT]
                    ingredients.append(
                        Ingredient(
                            space=self.space,
                            food=food,
                            unit=self.unit,
                            amount=Decimal("0.125"),
                            order=ingredient_index,
                        )
                    )
                    owners.append(step.pk)
            Ingredient.objects.bulk_create(ingredients, batch_size=FIXTURE_CHUNK)
            Step.ingredients.through.objects.bulk_create(
                [
                    Step.ingredients.through(step_id=step_id, ingredient_id=ingredient.pk)
                    for step_id, ingredient in zip(owners, ingredients)
                ],
                batch_size=FIXTURE_CHUNK,
            )

    def _create_prices(self):
        packages = PackageFormat.objects.bulk_create(
            [
                PackageFormat(
                    space=self.space,
                    food=food,
                    unit=self.unit,
                    label="Saco 5 kg",
                    quantity=Decimal("5"),
                    is_reference=True,
                )
                for food in self.foods
            ],
            batch_size=FIXTURE_CHUNK,
        )
        now = timezone.now()
        PriceVersion.objects.bulk_create(
            [
                PriceVersion(
                    space=self.space,
                    package=package,
                    amount=Decimal("12.50"),
                    valid_from=now,
                    created_by=self.users[0],
                )
                for package in packages
            ],
            batch_size=FIXTURE_CHUNK,
        )

    def _create_inventory_projection(self):
        location = InventoryLocation.objects.create(
            space=self.space,
            household=self.household,
            name="Almacén benchmark",
            created_by=self.users[0],
        )
        return InventoryEntry.objects.create(
            space=self.space,
            inventory_location=location,
            food=self.foods[0],
            unit=self.unit,
            amount=Decimal(MOVEMENT_COUNT),
            created_by=self.users[0],
        )

    def _create_movements(self):
        for offset in range(0, MOVEMENT_COUNT, FIXTURE_CHUNK):
            upper = min(offset + FIXTURE_CHUNK, MOVEMENT_COUNT)
            StockMovement.objects.bulk_create(
                [
                    StockMovement(
                        space=self.space,
                        entry=self.entry,
                        kind=StockMovement.RECEIPT,
                        quantity=Decimal("1"),
                        idempotency_key=f"performance-receipt-{index}",
                        fingerprint=f"{index:064x}",
                        balance_after=Decimal(index + 1),
                        metadata_snapshot={"fixture": "performance", "sequence": index + 1},
                        created_by=self.users[0],
                    )
                    for index in range(offset, upper)
                ],
                batch_size=FIXTURE_CHUNK,
            )

    def _create_services(self):
        meal_type = MealType.objects.create(
            space=self.space,
            name="Servicio benchmark",
            created_by=self.users[0],
            default=False,
        )
        now = timezone.now()
        meals = MealPlan.objects.bulk_create(
            [
                MealPlan(
                    space=self.space,
                    recipe=self.recipes[index],
                    servings=10,
                    title=f"Servicio {index:03d}",
                    created_by=self.users[0],
                    meal_type=meal_type,
                    from_date=now,
                    to_date=now,
                )
                for index in range(SERVICE_LIST_COUNT)
            ],
            batch_size=FIXTURE_CHUNK,
        )
        ServicePlan.objects.bulk_create(
            [
                ServicePlan(
                    space=self.space,
                    household=self.household,
                    meal_plan=meal,
                    title=meal.title,
                    covers=10,
                    created_by=self.users[0],
                    service_date=timezone.localdate(),
                )
                for meal in meals
            ],
            batch_size=FIXTURE_CHUNK,
        )

    @staticmethod
    def _client_for(user):
        client = APIClient()
        client.force_login(user)
        client.raise_request_exception = False
        return client

    @staticmethod
    def _response_items(response):
        data = getattr(response, "data", None)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict) and isinstance(data.get("lines"), list):
            return len(data["lines"])
        return 1

    def _timed_get(self, client, path):
        started = perf_counter()
        response = client.get(path)
        elapsed_ms = (perf_counter() - started) * 1000
        return response, elapsed_ms

    def _measure_endpoint(self, client, path):
        # Warm caches and lazy imports outside recorded repetitions.
        warmup = client.get(path)
        samples = []
        item_counts = []
        statuses = []
        for _ in range(TIMING_REPETITIONS):
            response, elapsed_ms = self._timed_get(client, path)
            statuses.append(response.status_code)
            samples.append(elapsed_ms)
            item_counts.append(self._response_items(response))
        query_counts = []
        query_item_counts = []
        for _ in range(QUERY_REPETITIONS):
            with CaptureQueriesContext(connection) as captured:
                response = client.get(path)
            statuses.append(response.status_code)
            query_counts.append(len(captured))
            query_item_counts.append(self._response_items(response))
        return {
            **_percentiles(samples),
            "raw_samples_ms": [round(sample, 3) for sample in samples],
            "samples": len(samples),
            "items": item_counts[-1],
            "warmup_items": self._response_items(warmup),
            "timed_item_counts": item_counts,
            "query_item_counts": query_item_counts,
            "warmup_status": warmup.status_code,
            "statuses": sorted(set(statuses)),
            "query_counts": query_counts,
            "query_count_min": min(query_counts),
            "query_count_max": max(query_counts),
        }

    def _measure_concurrent(self, path):
        samples = []
        statuses = []
        item_counts = []
        errors = []

        def worker(client, barrier):
            close_old_connections()
            try:
                barrier.wait(timeout=60)
                response, elapsed_ms = self._timed_get(client, path)
                return response.status_code, elapsed_ms, self._response_items(response)
            finally:
                connections.close_all()

        for _ in range(CONCURRENT_REPETITIONS):
            barrier = Barrier(CONCURRENT_USERS)
            with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as executor:
                futures = [executor.submit(worker, client, barrier) for client in self.clients]
                for future in futures:
                    try:
                        status, elapsed_ms, item_count = future.result(timeout=120)
                        statuses.append(status)
                        samples.append(elapsed_ms)
                        item_counts.append(item_count)
                    except Exception as exc:  # Report before the assertion fails.
                        errors.append(type(exc).__name__)
        return {
            **_percentiles(samples),
            "raw_samples_ms": [round(sample, 3) for sample in samples],
            "samples": len(samples),
            "users": CONCURRENT_USERS,
            "repetitions": CONCURRENT_REPETITIONS,
            "items": item_counts[-1] if item_counts else None,
            "item_counts": item_counts,
            "statuses": sorted(set(statuses)),
            "errors": errors,
        }

    @staticmethod
    def _profile_rows(profile):
        stats = pstats.Stats(profile)
        rows = []
        for (filename, line, function), values in sorted(
            stats.stats.items(), key=lambda item: item[1][3], reverse=True,
        )[:30]:
            primitive_calls, total_calls, total_time, cumulative_time, _callers = values
            rows.append({
                "file": filename,
                "line": line,
                "function": function,
                "primitive_calls": primitive_calls,
                "total_calls": total_calls,
                "total_time_ms": round(total_time * 1000, 3),
                "cumulative_time_ms": round(cumulative_time * 1000, 3),
            })
        return rows

    def _profile_request(self, client, path):
        profile = cProfile.Profile()
        rss_before = _rss_facts()
        wall_started = perf_counter()
        cpu_started = process_time()
        with CaptureQueriesContext(connection) as captured:
            profile.enable()
            try:
                response = client.get(path)
                payload_bytes = len(response.content)
            finally:
                profile.disable()
        cpu_ms = (process_time() - cpu_started) * 1000
        wall_ms = (perf_counter() - wall_started) * 1000
        queries = [dict(query) for query in captured.captured_queries]
        sql_ms = sum(float(query.get("time") or 0) * 1000 for query in queries)
        return {
            "status": response.status_code,
            "items": self._response_items(response),
            "wall_ms": round(wall_ms, 3),
            "process_cpu_ms": round(cpu_ms, 3),
            "sql_ms": round(sql_ms, 3),
            "sql_count": len(queries),
            "payload_bytes": payload_bytes,
            "is_rendered": getattr(response, "is_rendered", None),
            "rss_before": rss_before,
            "rss_after": _rss_facts(),
            "top_cumulative": self._profile_rows(profile),
        }, queries

    @staticmethod
    def _representative_sql(profile_queries):
        specifications = {
            "packages_rows": ("packages_1500", 'from "cuaderno_packageformat"'),
            "packages_latest_prices": ("packages_1500", 'from "cuaderno_priceversion"'),
            "services_candidates": ("services_100", 'from "cuaderno_serviceplan"'),
            "services_visible_recipe_acl": ("services_100", 'from "cookbook_recipe"'),
            "movements_household_order": ("movements_100_of_100000", 'from "cuaderno_stockmovement"'),
        }
        selected = {}
        for label, (endpoint, marker) in specifications.items():
            matches = [
                query["sql"] for query in profile_queries[endpoint]
                if isinstance(query.get("sql"), str)
                and marker in query["sql"].lower()
                and query["sql"].lstrip().lower().startswith(("select", "with"))
            ]
            if not matches:
                raise AssertionError(f"No se capturó SQL representativo para {label}.")
            # Prefer the longest SELECT: it retains ACL/order/price predicates rather
            # than selecting an incidental existence check on the same relation.
            selected[label] = max(matches, key=len)
        return selected

    @staticmethod
    def _explain_representative_sql(selected):
        plans = {}
        # EXPLAIN ANALYZE executes each captured SELECT. The explicit read-only
        # transaction prevents this diagnostic lane from becoming a write path.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                for label, sql in selected.items():
                    cursor.execute("EXPLAIN (ANALYZE TRUE, BUFFERS TRUE, FORMAT JSON) " + sql)
                    plan = cursor.fetchone()[0]
                    plans[label] = {
                        "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                        "plan": plan,
                    }
        return plans

    def _diagnostic_report(self, endpoints):
        profiles = {}
        captured = {}
        for name, path in endpoints.items():
            profiles[name], captured[name] = self._profile_request(self.clients[0], path)
        selected = self._representative_sql(captured)
        return {
            "schema_version": 1,
            "acceptance_samples_excluded": True,
            "instrumented_requests": 1,
            "profiles": profiles,
            "explain": self._explain_representative_sql(selected),
        }

    def _database_facts(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT version(), current_setting('server_version'), current_setting('jit')")
            version, short_version, jit = cursor.fetchone()
            cursor.execute("SELECT pg_database_size(current_database())")
            database_size = cursor.fetchone()[0]
            table_sizes = {}
            for table in (
                "cookbook_recipe",
                "cookbook_ingredient",
                "cookbook_food",
                "cuaderno_stockmovement",
            ):
                cursor.execute("SELECT pg_total_relation_size(%s)", [table])
                table_sizes[table] = cursor.fetchone()[0]
        return {
            "vendor": connection.vendor,
            "jit": jit,
            "connection_options": connection.settings_dict.get("OPTIONS", {}).get("options", ""),
            "server_version": short_version,
            "version": version,
            "database_size_bytes": database_size,
            "table_size_bytes": table_sizes,
        }

    def _assert_dataset(self):
        with scopes_disabled():
            counts = {
                "recipes": Recipe.objects.filter(space=self.space).count(),
                "foods": Food.objects.filter(space=self.space).count(),
                "ingredients": Ingredient.objects.filter(space=self.space).count(),
                "users": UserSpace.objects.filter(space=self.space).count(),
                "stock_movements": StockMovement.objects.filter(space=self.space).count(),
                "inventory_entries": InventoryEntry.objects.filter(space=self.space).count(),
                "packages": PackageFormat.objects.filter(space=self.space).count(),
                "services": ServicePlan.objects.filter(space=self.space).count(),
            }
            last_balance = (
                StockMovement.objects.filter(space=self.space, entry=self.entry)
                .order_by("-id")
                .values_list("balance_after", flat=True)
                .first()
            )
            self.entry.refresh_from_db()
        self.assertEqual(counts["recipes"], RECIPE_COUNT)
        self.assertEqual(counts["foods"], FOOD_COUNT)
        self.assertEqual(counts["ingredients"], RECIPE_COUNT * INGREDIENTS_PER_RECIPE)
        self.assertEqual(counts["users"], USER_COUNT)
        self.assertEqual(counts["stock_movements"], MOVEMENT_COUNT)
        self.assertEqual(counts["inventory_entries"], 1)
        self.assertEqual(counts["packages"], FOOD_COUNT)
        self.assertEqual(counts["services"], SERVICE_LIST_COUNT)
        self.assertEqual(self.entry.amount, Decimal(MOVEMENT_COUNT))
        self.assertEqual(last_balance, self.entry.amount)
        counts["ingredients_per_recipe_mean"] = counts["ingredients"] / counts["recipes"]
        counts["ledger_projection_coherent"] = True
        return counts

    def test_documented_postgresql_dataset_meets_api_budgets(self):
        dataset = self._assert_dataset()
        endpoints = {
            "cost_recipe_15_lines": f"/api/cuaderno/recipes/{self.recipes[-1].pk}/cost/?servings=10",
            "services_100": "/api/cuaderno/services/",
            "movements_100_of_100000": "/api/cuaderno/movements/",
            "packages_1500": "/api/cuaderno/packages/",
        }
        expected_items = {
            "cost_recipe_15_lines": 15,
            "services_100": SERVICE_LIST_COUNT,
            "movements_100_of_100000": 100,
            "packages_1500": FOOD_COUNT,
        }
        sequential = {name: self._measure_endpoint(self.clients[0], path) for name, path in endpoints.items()}
        concurrent = {
            name: self._measure_concurrent(endpoints[name])
            for name in ("services_100", "movements_100_of_100000", "packages_1500")
        }
        report = {
            "schema_version": 1,
            "measured_at": timezone.now().isoformat(),
            "method": {
                "client": "DRF APIClient in-process",
                "network": "sin red externa; incluye middleware, ORM y renderizado de respuesta",
                "sequential_warm_cache": True,
                "concurrent_connection_policy": "new threads/connections per round; no complete per-user warmup",
                "timing_repetitions": TIMING_REPETITIONS,
                "query_repetitions": QUERY_REPETITIONS,
                "concurrent_users": CONCURRENT_USERS,
                "concurrent_repetitions": CONCURRENT_REPETITIONS,
            },
            "budgets_ms": {"cost_recipe_p95": 300, "list_api_p95": 500},
            "dataset": dataset,
            "fixture_build_ms": self.fixture_ms,
            "runtime": {
                "python": sys.version.split()[0],
                "django": django.get_version(),
                "tandoor_version": TANDOOR_VERSION or "unknown-worktree",
                "source_ref": TANDOOR_REF or "unknown-worktree",
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "memory_limit_bytes": _memory_limit_bytes(),
            },
            "database": self._database_facts(),
            "sequential": sequential,
            "concurrent": concurrent,
            "claims_excluded": ["LCP", "INP", "iPad físico", "latencia de Internet", "hardware comercial"],
        }
        print("CUADERNO_PERFORMANCE " + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
        diagnostic = self._diagnostic_report(endpoints) if os.environ.get("CUADERNO_PROFILE") == "1" else None
        if diagnostic is not None:
            print("CUADERNO_DIAGNOSTIC " + json.dumps(diagnostic, sort_keys=True, separators=(",", ":")))

        for name, metrics in sequential.items():
            with self.subTest(endpoint=name, check="query_count_stability"):
                self.assertEqual(metrics["warmup_status"], 200)
                self.assertEqual(metrics["statuses"], [200])
                self.assertEqual(metrics["warmup_items"], expected_items[name])
                self.assertEqual(metrics["timed_item_counts"], [expected_items[name]] * TIMING_REPETITIONS)
                self.assertEqual(metrics["query_item_counts"], [expected_items[name]] * QUERY_REPETITIONS)
                self.assertLessEqual(metrics["query_count_max"] - metrics["query_count_min"], 1)
        with self.subTest(endpoint="cost_recipe_15_lines", mode="sequential"):
            self.assertLessEqual(sequential["cost_recipe_15_lines"]["p95_ms"], 300)
        for name in ("services_100", "movements_100_of_100000", "packages_1500"):
            with self.subTest(endpoint=name, mode="sequential"):
                self.assertLessEqual(sequential[name]["p95_ms"], 500)
            with self.subTest(endpoint=name, mode="five_concurrent_users"):
                self.assertEqual(concurrent[name]["errors"], [])
                self.assertEqual(concurrent[name]["statuses"], [200])
                self.assertEqual(concurrent[name]["samples"], CONCURRENT_USERS * CONCURRENT_REPETITIONS)
                self.assertEqual(
                    concurrent[name]["item_counts"],
                    [expected_items[name]] * CONCURRENT_USERS * CONCURRENT_REPETITIONS,
                )
                self.assertLessEqual(concurrent[name]["p95_ms"], 500)
