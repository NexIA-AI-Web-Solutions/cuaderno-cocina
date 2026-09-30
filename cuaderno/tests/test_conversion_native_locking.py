"""Native UnitConversion writes serialize with portable exchange's Space lock."""

from decimal import Decimal
from threading import Event, Thread
from time import monotonic

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.models import SearchFields, Space, Unit, UnitConversion, UserSpace


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeConversionSpaceLockTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql", "Este contrato requiere locks reales de PostgreSQL.")
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.user = get_user_model().objects.create_user(
                username="native-conversion-lock-owner",
                password="synthetic-only",
            )
            self.space = Space.objects.create(name="Native conversion lock", created_by=self.user)
            membership = UserSpace.objects.create(user=self.user, space=self.space, active=True)
            membership.groups.add(Group.objects.get_or_create(name="user")[0])
            self.base_unit = Unit.objects.create(space=self.space, name="lock-g", base_unit="g")
            self.converted_unit = Unit.objects.create(space=self.space, name="lock-ml", base_unit="ml")

            # Same labels in another Space prove nested serializer resolution
            # remains scoped while the target Space row is the lock authority.
            self.other_space = Space.objects.create(name="Native conversion other", created_by=self.user)
            Unit.objects.create(space=self.other_space, name="lock-g", base_unit="g")
            Unit.objects.create(space=self.other_space, name="lock-ml", base_unit="ml")

        # Session creation is deliberately outside the worker thread. The
        # worker only owns the request/database connection used for the write.
        self.client = APIClient()
        self.client.force_login(self.user)

    @staticmethod
    def _backend_pid():
        connection.ensure_connection()
        raw_connection = connection.connection
        info = getattr(raw_connection, "info", None)
        pid = getattr(info, "backend_pid", None)
        if pid is None:
            pid = raw_connection.get_backend_pid()
        return pid

    def _wait_for_postgres_lock(self, pid, holder_pid, done):
        deadline = monotonic() + 3
        samples = []
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    """
                    SELECT wait_event_type, wait_event, state, query, pg_blocking_pids(pid)
                      FROM pg_stat_activity
                     WHERE pid = %s
                       AND datname = current_database()
                       AND backend_type = 'client backend'
                    """,
                    [pid],
                )
                row = cursor.fetchone()
            samples.append(row)
            # An INSERT's incidental foreign-key lock is too late: imports
            # need the Space lock before validation and object lookup.
            if (row and row[0] == "Lock" and holder_pid in row[4]
                    and "FOR UPDATE" in row[3].upper() and "cookbook_space" in row[3]):
                return True, not done.is_set(), samples
            if done.wait(0.02):
                break
        return False, not done.is_set(), samples

    def _request_while_space_locked(self, method, path, payload=None, before_release=None):
        started = Event()
        done = Event()
        outcome = {}

        def worker():
            close_old_connections()
            try:
                outcome["pid"] = self._backend_pid()
                started.set()
                request = getattr(self.client, method)
                if payload is None:
                    outcome["response"] = request(path)
                else:
                    outcome["response"] = request(path, payload, format="json")
            except Exception as exc:  # Thread failures become deterministic assertions.
                outcome["error"] = exc
            finally:
                connections.close_all()
                done.set()

        thread = Thread(target=worker, name=f"native-conversion-{method}", daemon=True)
        observed_lock = False
        unfinished_at_lock = False
        samples = []
        with transaction.atomic(), scopes_disabled():
            Space.objects.select_for_update().get(pk=self.space.pk)
            holder_pid = self._backend_pid()
            thread.start()
            self.assertTrue(started.wait(3), "El worker no abrió su conexión PostgreSQL.")
            observed_lock, unfinished_at_lock, samples = self._wait_for_postgres_lock(outcome["pid"], holder_pid, done)
            if before_release is not None:
                before_release()

        thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "La petición siguió viva después de liberar el Space lock.")
        self.assertNotIn("error", outcome, repr(outcome.get("error")))
        self.assertTrue(observed_lock, f"La escritura no esperó un lock PostgreSQL: {samples[-5:]}")
        self.assertTrue(unfinished_at_lock, "La escritura terminó antes de liberar el Space lock.")
        return outcome["response"]

    def _payload(self):
        return {
            "base_amount": "100",
            "base_unit": {
                "id": self.base_unit.pk,
                "name": self.base_unit.name,
                "base_unit": self.base_unit.base_unit,
            },
            "converted_amount": "100",
            "converted_unit": {
                "id": self.converted_unit.pk,
                "name": self.converted_unit.name,
                "base_unit": self.converted_unit.base_unit,
            },
        }

    def _conversion(self):
        with scopes_disabled():
            return UnitConversion.objects.create(
                space=self.space,
                created_by=self.user,
                food=None,
                base_amount=Decimal("100"),
                base_unit=self.base_unit,
                converted_amount=Decimal("100"),
                converted_unit=self.converted_unit,
            )

    def test_native_create_waits_for_the_space_lock_then_persists(self):
        response = self._request_while_space_locked(
            "post",
            "/api/unit-conversion/",
            self._payload(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        with scopes_disabled():
            row = UnitConversion.objects.get(space=self.space)
            self.assertEqual(row.base_amount, Decimal("100"))
            self.assertEqual(row.converted_amount, Decimal("100"))
            self.assertFalse(UnitConversion.objects.filter(space=self.other_space).exists())

    def test_native_patch_waits_and_reloads_after_a_locked_change(self):
        conversion = self._conversion()

        def change_while_locked():
            UnitConversion.objects.filter(pk=conversion.pk).update(base_amount=Decimal("125"))

        response = self._request_while_space_locked(
            "patch",
            f"/api/unit-conversion/{conversion.pk}/",
            {"converted_amount": "250"},
            before_release=change_while_locked,
        )
        self.assertEqual(response.status_code, 200, response.content)
        with scopes_disabled():
            conversion.refresh_from_db()
            self.assertEqual(conversion.base_amount, Decimal("125"))
            self.assertEqual(conversion.converted_amount, Decimal("250"))
            self.assertFalse(UnitConversion.objects.filter(space=self.other_space).exists())

    def test_native_delete_waits_for_the_space_lock_then_deletes_fresh_row(self):
        conversion = self._conversion()

        def change_while_locked():
            UnitConversion.objects.filter(pk=conversion.pk).update(base_amount=Decimal("125"))

        response = self._request_while_space_locked(
            "delete",
            f"/api/unit-conversion/{conversion.pk}/",
            before_release=change_while_locked,
        )
        self.assertEqual(response.status_code, 204, response.content)
        with scopes_disabled():
            self.assertFalse(UnitConversion.objects.filter(pk=conversion.pk).exists())
            self.assertFalse(UnitConversion.objects.filter(space=self.other_space).exists())

    def test_native_delete_reloads_after_the_locked_row_was_already_deleted(self):
        conversion = self._conversion()
        conversion_id = conversion.pk

        def delete_while_locked():
            UnitConversion.objects.filter(pk=conversion_id).delete()

        response = self._request_while_space_locked(
            "delete", f"/api/unit-conversion/{conversion_id}/",
            before_release=delete_while_locked,
        )
        self.assertEqual(response.status_code, 404, response.content)
        with scopes_disabled():
            self.assertFalse(UnitConversion.objects.filter(pk=conversion_id).exists())
