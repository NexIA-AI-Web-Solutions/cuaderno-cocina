"""Native view logging and yield reads must not invert PostgreSQL FK locks."""
import threading
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import Household, Recipe, Space, UserSpace, ViewLog
from cookbook.serializer import ViewLogSerializer
from cuaderno.models import SpaceProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeViewLogLockOrderTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        with scopes_disabled():
            self.space = Space.objects.create(name="Synthetic view-log concurrency")
            household = Household.objects.create(space=self.space, name="Synthetic concurrency kitchen")
            self.user = get_user_model().objects.create_user(username="view-log-lock-owner", password="synthetic-only")
            membership = UserSpace.objects.create(user=self.user, space=self.space, household=household, active=True)
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.space.created_by = self.user
            self.space.save(update_fields=["created_by"])
            self.profile = SpaceProfile.objects.create(space=self.space, edition=SpaceProfile.ESENCIAL)
            self.recipe = Recipe.objects.create(space=self.space, created_by=self.user, name="Synthetic concurrent recipe", private=False)
        self.client = self.client_for_user()

    def client_for_user(self):
        client = APIClient()
        client.force_login(self.user)
        client.raise_request_exception = False
        return client

    @skipUnlessDBFeature("has_select_for_update")
    def test_actual_native_post_and_ingredient_yield_get_complete_for_all_editions(self):
        self.assertEqual(connection.vendor, "postgresql", "This regression requires real PostgreSQL FK locks.")
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            with self.subTest(edition=edition), scopes_disabled():
                self.profile.edition = edition
                self.profile.save(update_fields=["edition"])
                ViewLog.objects.filter(recipe=self.recipe).delete()
                self.assert_concurrent_native_requests()

    def assert_concurrent_native_requests(self):
        # Pause the real GET only AFTER its Space lock succeeds. The POST then
        # performs its genuine SQL. Observe PostgreSQL's blocking relationship
        # before allowing GET to acquire Recipe; no exception or lock is faked.
        space_locked = threading.Event()
        release_reader = threading.Event()
        writer_ready = threading.Event()
        results, backend_pids, writer_sql = {}, {}, []
        clients = {"reader": self.client_for_user(), "writer": self.client_for_user()}
        deadline = time.monotonic() + 8

        def worker(role):
            db = connections["default"]
            try:
                db.close()
                def observe_sql(execute, sql, params, many, context):
                    if role not in backend_pids:
                        # Capture the connection used by the request itself:
                        # request_started can close a connection opened earlier.
                        backend_pids[role] = db.connection.get_backend_pid()
                        execute("SET lock_timeout = '5s'", None, False, context)
                        execute("SET statement_timeout = '6s'", None, False, context)
                        if role == "writer":
                            writer_ready.set()
                    is_space_lock = sql.lstrip().upper().startswith("SELECT") and '"cookbook_space"' in sql and "FOR UPDATE" in sql
                    if role == "writer":
                        if is_space_lock:
                            writer_sql.append("space_lock")
                        elif '"cookbook_recipe"' in sql and "FOR UPDATE" in sql:
                            writer_sql.append("recipe_lock")
                        elif sql.lstrip().upper().startswith("INSERT INTO \"COOKBOOK_VIEWLOG\""):
                            writer_sql.append("view_log_insert")
                    result = execute(sql, params, many, context)
                    if role == "reader" and is_space_lock:
                        space_locked.set()
                        if not release_reader.wait(max(0, deadline - time.monotonic())):
                            raise AssertionError("Timed out coordinating the real Space lock.")
                    return result

                with db.execute_wrapper(observe_sql):
                    if role == "reader":
                        response = clients[role].get(f"/api/cuaderno/recipes/{self.recipe.pk}/ingredient-yields/")
                    else:
                        response = clients[role].post("/api/view-log/", {"recipe": self.recipe.pk}, format="json")
                results[role] = {"status": response.status_code}
                if response.status_code < 400:
                    results[role]["id"] = response.data.get("id", response.data.get("recipe_id"))
            except Exception as exc:
                results[role] = {"exception": type(exc).__name__}
            finally:
                db.close()

        threads = {role: threading.Thread(target=worker, args=(role,), name=f"synthetic-view-log-{role}", daemon=True) for role in clients}
        blocked_by_reader = False
        try:
            threads["reader"].start()
            self.assertTrue(space_locked.wait(max(0, deadline - time.monotonic())), results)
            threads["writer"].start()
            self.assertTrue(writer_ready.wait(max(0, deadline - time.monotonic())), results)
            # This checks an actual waiter, rather than relying on a race or
            # sleeping for a guessed time before releasing the GET.
            with connection.cursor() as cursor:
                while time.monotonic() < deadline:
                    cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [backend_pids["reader"], backend_pids["writer"]])
                    if cursor.fetchone()[0]:
                        blocked_by_reader = True
                        break
                    if "writer" in results:
                        break
                    writer_ready.clear()
                    writer_ready.wait(min(0.01, max(0, deadline - time.monotonic())))
        finally:
            release_reader.set()
            for thread in threads.values():
                if thread.ident is not None:
                    thread.join(max(0, deadline - time.monotonic()))
        self.assertFalse(any(thread.is_alive() for thread in threads.values()), "Concurrent native requests exceeded the bounded deadline.")
        self.assertTrue(blocked_by_reader, "PostgreSQL never observed the POST waiting on the GET's real Space lock.")
        self.assertEqual(results.get("reader", {}).get("status"), 200, results)
        self.assertEqual(results.get("writer", {}).get("status"), 201, results)
        self.assertEqual(writer_sql, ["space_lock", "recipe_lock", "view_log_insert"])
        with scopes_disabled():
            row = ViewLog.objects.get(recipe=self.recipe)
            self.assertEqual((row.created_by_id, row.space_id), (self.user.pk, self.space.pk))

    def test_recent_duplicate_keeps_native_201_and_existing_log_id(self):
        first = self.client.post("/api/view-log/", {"recipe": self.recipe.pk}, format="json")
        second = self.client.post("/api/view-log/", {"recipe": self.recipe.pk}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.data["id"], second.data["id"])
        with scopes_disabled():
            self.assertEqual(ViewLog.objects.filter(recipe=self.recipe).count(), 1)

    def test_cross_space_recipe_remains_invalid_without_any_log(self):
        with scopes_disabled():
            other_space = Space.objects.create(name="Synthetic other view-log space")
            other_recipe = Recipe.objects.create(space=other_space, created_by=self.user, name="Synthetic other recipe")
        response = self.client.post("/api/view-log/", {"recipe": other_recipe.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        with scopes_disabled():
            self.assertFalse(ViewLog.objects.exists())

    def test_recipe_removed_after_validation_returns_helpful_spanish_400(self):
        original_create = ViewLogSerializer.create

        def remove_then_create(serializer, validated_data):
            with scopes_disabled():
                validated_data["recipe"].delete()
            return original_create(serializer, validated_data)

        with patch.object(ViewLogSerializer, "create", remove_then_create):
            response = self.client.post("/api/view-log/", {"recipe": self.recipe.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("receta", str(response.data).lower())
        self.assertIn("actualiza", str(response.data).lower())
        with scopes_disabled():
            self.assertFalse(ViewLog.objects.exists())
