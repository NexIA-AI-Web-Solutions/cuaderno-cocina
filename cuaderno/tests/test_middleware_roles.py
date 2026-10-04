"""Request-local authorization remains fresh while avoiding repeated group SQL."""
from datetime import datetime
from decimal import Decimal

from cookbook.models import Space, UserSpace
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django_scopes import scopes_disabled

from cookbook.helper.permission_helper import has_group_permission
from cookbook.helper.scope_middleware import ScopeMiddleware
from cuaderno.tests import test_integration as fixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MiddlewareRoleTests(TestCase):
    setUp = fixtures.CuadernoIntegrationTests.setUp
    _user = fixtures.CuadernoIntegrationTests._user
    _client = fixtures.CuadernoIntegrationTests._client

    def request(self):
        request = RequestFactory().get('/api/cuaderno/edition/')
        request.user = self.user
        return request

    def test_role_snapshot_is_one_query_and_revocation_is_visible_next_request(self):
        def response(request):
            with self.assertNumQueries(0):
                self.assertEqual(has_group_permission(request, ['user']), self.expected)
                self.assertTrue(has_group_permission(request, ['guest']))
            return HttpResponse()
        middleware = ScopeMiddleware(response)
        self.expected = True
        with self.assertNumQueries(1):
            middleware(self.request())
        with scopes_disabled():
            membership = self.user.userspace_set.get(active=True)
            membership.groups.set([Group.objects.get_or_create(name='guest')[0]])
        self.expected = False
        with self.assertNumQueries(1):
            middleware(self.request())

    def test_multiple_active_memberships_fail_closed_with_one_snapshot_query(self):
            with scopes_disabled():
                second_space = Space.objects.create(
                    name="Second active role snapshot", created_by=self.user,
                )
                second = UserSpace.objects.create(
                    user=self.user, space=second_space, active=True,
                )
                second.groups.add(Group.objects.get_or_create(name="admin")[0])

            observed = {}

            def response(request):
                observed["roles"] = request._group_permission_snapshot[1]
                observed["other_active"] = request.user_space.other_active
                with self.assertNumQueries(0):
                    self.assertFalse(has_group_permission(request, ["guest"]))
                    self.assertFalse(has_group_permission(request, ["user"]))
                    self.assertFalse(has_group_permission(request, ["admin"]))
                return HttpResponse(status=204)

            with self.assertNumQueries(1):
                result = ScopeMiddleware(response)(self.request())

            self.assertEqual(result.status_code, 204)
            self.assertEqual(observed, {"roles": (), "other_active": True})

    def test_raw_membership_snapshot_hydrates_native_types_and_relations(self):
        with scopes_disabled():
            expected = self.user.userspace_set.select_related("space").get(active=True)
            expected.space.ai_credits_balance = Decimal("17.2500")
            expected.space.message = "Metadatos ñ"
            expected.space.save(update_fields=["ai_credits_balance", "message"])
            expected.groups.add(Group.objects.get_or_create(name="admin")[0])

        with self.assertNumQueries(1):
            rows = ScopeMiddleware._memberships(self.user, active=True, limit=2)
        self.assertEqual(len(rows), 1)
        membership = rows[0]
        with self.assertNumQueries(0):
            self.assertEqual(membership.space.pk, expected.space_id)
            self.assertEqual(membership.space.message, "Metadatos ñ")
            self.assertEqual(membership.space.ai_credits_balance, Decimal("17.2500"))
            self.assertIsInstance(membership.created_at, datetime)
            self.assertIsInstance(membership.space.created_at, datetime)
        self.assertIs(membership._state.adding, False)
        self.assertEqual(membership._state.db, expected._state.db)
        self.assertEqual(membership.role_names, tuple(sorted(membership.role_names)))
        self.assertIn("admin", membership.role_names)

    def test_raw_membership_snapshot_filters_active_and_caps_two_rows(self):
        with scopes_disabled():
            second = Space.objects.create(name="Raw membership inactive", created_by=self.user)
            third = Space.objects.create(name="Raw membership active", created_by=self.user)
            inactive = UserSpace.objects.create(user=self.user, space=second, active=False)
            active = UserSpace.objects.create(user=self.user, space=third, active=True)
            inactive.groups.add(Group.objects.get_or_create(name="guest")[0])
            active.groups.add(Group.objects.get_or_create(name="admin")[0])

        with self.assertNumQueries(1):
            active_rows = ScopeMiddleware._memberships(self.user, active=True, limit=2)
        self.assertEqual(len(active_rows), 2)
        self.assertTrue(all(row.active for row in active_rows))
        self.assertEqual([row.pk for row in active_rows], sorted(row.pk for row in active_rows))
        with self.assertNumQueries(1):
            inactive_rows = ScopeMiddleware._memberships(self.user, active=False, limit=2)
        self.assertEqual([row.pk for row in inactive_rows], [inactive.pk])
