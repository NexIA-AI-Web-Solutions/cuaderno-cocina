"""Regression contract for native group caches across Spaces and membership edits."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.helper.permission_helper import has_group_permission, switch_user_active_space
from cookbook.models import SearchFields, Space, UserSpace
from cuaderno.models import SpaceProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GroupCacheIsolationTests(TestCase):
    edition_url = "/api/cuaderno/edition/"

    def setUp(self):
        cache.clear()
        with scopes_disabled():
            SearchFields.objects.get_or_create(name="Name", defaults={"field": "name"})
            self.admin_group = Group.objects.get_or_create(name="admin")[0]
            self.guest_group = Group.objects.get_or_create(name="guest")[0]
            self.user_group = Group.objects.get_or_create(name="user")[0]
            self.space_a = Space.objects.create(name="Cache Space A")
            self.space_b = Space.objects.create(name="Cache Space B")
            self.user = get_user_model().objects.create_user(
                username="group-cache-user", password="synthetic-only",
            )
            self.member_a = UserSpace.objects.create(
                user=self.user, space=self.space_a, active=True,
            )
            self.member_a.groups.add(self.admin_group)
            self.member_b = UserSpace.objects.create(
                user=self.user, space=self.space_b, active=False,
            )
            self.member_b.groups.add(self.guest_group)
            self.space_a.created_by = self.user
            self.space_b.created_by = self.user
            self.space_a.save(update_fields=["created_by"])
            self.space_b.save(update_fields=["created_by"])
            self.profile_a = SpaceProfile.objects.create(
                space=self.space_a, edition=SpaceProfile.INTEGRAL, price_policy=SpaceProfile.NET,
            )
            self.profile_b = SpaceProfile.objects.create(
                space=self.space_b, edition=SpaceProfile.INTEGRAL, price_policy=SpaceProfile.NET,
            )
        self.client = APIClient()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def put_policy(self, policy):
        return self.client.put(
            self.edition_url,
            {"edition": "integral", "price_policy": policy},
            format="json",
        )

    def switch_api(self, space):
        return self.client.get(f"/api/switch-active-space/{space.pk}/")

    def request_snapshot(self, *, user=None, space=None, membership=None):
        return SimpleNamespace(
            user=user or self.user,
            space=space or self.space_a,
            user_space=membership or self.member_a,
        )

    def test_cached_admin_in_space_a_never_authorizes_guest_write_after_api_switch_to_b(self):
        self.assertEqual(self.client.get(self.edition_url).status_code, 200)
        self.assertEqual(self.put_policy(SpaceProfile.GROSS).status_code, 200)
        self.assertEqual(self.switch_api(self.space_b).status_code, 200)

        denied = self.put_policy(SpaceProfile.GROSS)

        self.assertEqual(denied.status_code, 403, getattr(denied, "data", denied.content))
        self.profile_b.refresh_from_db()
        self.assertEqual(self.profile_b.price_policy, SpaceProfile.NET)

    def test_cached_guest_in_space_b_does_not_block_admin_immediately_after_switching_to_a(self):
        self.assertEqual(switch_user_active_space(self.user, self.space_b), self.member_b)
        self.assertEqual(self.client.get(self.edition_url).status_code, 200)
        self.assertEqual(self.put_policy(SpaceProfile.GROSS).status_code, 403)
        self.assertEqual(self.switch_api(self.space_a).status_code, 200)

        allowed = self.put_policy(SpaceProfile.GROSS)

        self.assertEqual(allowed.status_code, 200, getattr(allowed, "data", allowed.content))
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.price_policy, SpaceProfile.GROSS)

    def test_groups_set_downgrade_in_active_space_invalidates_cached_admin_immediately(self):
        self.assertEqual(self.put_policy(SpaceProfile.GROSS).status_code, 200)
        self.member_a.groups.set([self.guest_group])

        denied = self.put_policy(SpaceProfile.NET)

        self.assertEqual(denied.status_code, 403, getattr(denied, "data", denied.content))
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.price_policy, SpaceProfile.GROSS)

    def test_groups_clear_then_add_downgrade_also_invalidates_cached_admin(self):
        self.assertEqual(self.put_policy(SpaceProfile.GROSS).status_code, 200)
        self.member_a.groups.clear()
        self.assertIs(
            has_group_permission(self.request_snapshot(), ["admin"]),
            False,
        )
        self.member_a.groups.add(self.guest_group)

        denied = self.put_policy(SpaceProfile.NET)

        self.assertEqual(denied.status_code, 403, getattr(denied, "data", denied.content))
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.price_policy, SpaceProfile.GROSS)

    def test_switch_api_rejects_space_without_membership_and_keeps_active_space(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Cache Foreign Space")
            foreign_profile = SpaceProfile.objects.create(
                space=foreign, edition=SpaceProfile.INTEGRAL, price_policy=SpaceProfile.NET,
            )

        denied = self.switch_api(foreign)

        self.assertEqual(denied.status_code, 404, getattr(denied, "data", denied.content))
        self.member_a.refresh_from_db()
        self.assertIs(self.member_a.active, True)
        foreign_profile.refresh_from_db()
        self.assertEqual(foreign_profile.price_policy, SpaceProfile.NET)

    def test_multiple_active_memberships_fail_closed_for_admin_write(self):
        self.assertEqual(self.put_policy(SpaceProfile.GROSS).status_code, 200)
        self.member_b.active = True
        self.member_b.save(update_fields=["active"])

        denied = self.put_policy(SpaceProfile.NET)

        self.assertEqual(denied.status_code, 403, getattr(denied, "data", denied.content))
        self.profile_a.refresh_from_db()
        self.profile_b.refresh_from_db()
        self.assertEqual(self.profile_a.price_policy, SpaceProfile.GROSS)
        self.assertEqual(self.profile_b.price_policy, SpaceProfile.NET)

    def test_legacy_user_only_cache_key_cannot_grant_admin_in_guest_space(self):
        self.assertEqual(switch_user_active_space(self.user, self.space_b), self.member_b)
        cache.set(f"GROUP_CACHE_{self.user.pk}", ["admin"], timeout=30)

        denied = self.put_policy(SpaceProfile.GROSS)

        self.assertEqual(denied.status_code, 403, getattr(denied, "data", denied.content))
        self.profile_b.refresh_from_db()
        self.assertEqual(self.profile_b.price_policy, SpaceProfile.NET)

    def test_in_flight_space_a_snapshot_cannot_grant_admin_to_new_space_b_request(self):
        old_request = self.request_snapshot()
        self.assertIs(has_group_permission(old_request, ["admin"]), True)
        self.assertEqual(switch_user_active_space(self.user, self.space_b), self.member_b)
        new_request = self.request_snapshot(space=self.space_b, membership=self.member_b)

        self.assertIs(has_group_permission(new_request, ["admin"]), False)

    def test_direct_through_table_revocation_cannot_survive_into_a_new_request(self):
        request = self.request_snapshot()
        self.assertIs(has_group_permission(request, ["admin"]), True)
        through = UserSpace.groups.through
        through.objects.filter(
            userspace_id=self.member_a.pk, group_id=self.admin_group.pk,
        ).delete()
        through.objects.create(
            userspace_id=self.member_a.pk, group_id=self.guest_group.pk,
        )

        fresh_request = self.request_snapshot()

        self.assertIs(has_group_permission(fresh_request, ["admin"]), False)

    def test_request_space_and_membership_mismatch_fails_closed(self):
        mismatched = self.request_snapshot(space=self.space_b, membership=self.member_a)

        self.assertIs(has_group_permission(mismatched, ["admin"]), False)

    def test_forged_membership_owned_by_another_user_fails_closed(self):
        with scopes_disabled():
            other = get_user_model().objects.create_user(
                username="group-cache-other", password="synthetic-only",
            )
            other_member = UserSpace.objects.create(
                user=other, space=self.space_a, active=True,
            )
            other_member.groups.add(self.admin_group)
        forged = self.request_snapshot(user=other, membership=self.member_a)

        self.assertIs(has_group_permission(forged, ["admin"]), False)

    def test_no_cache_reloads_same_request_after_group_downgrade(self):
        request = self.request_snapshot()
        self.assertIs(has_group_permission(request, ["admin"]), True)
        self.member_a.groups.set([self.guest_group])

        self.assertIs(has_group_permission(request, ["admin"], no_cache=True), False)

    def test_repeated_group_checks_use_one_query_for_the_same_request_snapshot(self):
        request = self.request_snapshot()

        with self.assertNumQueries(1):
            self.assertIs(has_group_permission(request, ["guest"]), True)
            self.assertIs(has_group_permission(request, ["admin"]), True)

    def test_legacy_request_with_only_user_uses_its_unique_active_membership(self):
        legacy_request = SimpleNamespace(user=self.user)

        self.assertIs(has_group_permission(legacy_request, ["admin"]), True)

    def test_anonymous_request_denies_without_querying_memberships(self):
        anonymous_request = SimpleNamespace(user=AnonymousUser())

        with self.assertNumQueries(0):
            self.assertIs(has_group_permission(anonymous_request, ["guest"]), False)

    def test_one_membership_with_three_group_rows_remains_unique_in_one_query(self):
        self.member_a.groups.add(self.user_group, self.guest_group)
        request = self.request_snapshot()

        with self.assertNumQueries(1):
            self.assertIs(has_group_permission(request, ["admin"]), True)

    def test_mutated_request_snapshot_after_helper_switch_reloads_groups_once(self):
        request = self.request_snapshot()
        self.assertIs(has_group_permission(request, ["admin"]), True)
        self.assertEqual(switch_user_active_space(self.user, self.space_b), self.member_b)
        request.space = self.space_b
        request.user_space = self.member_b

        with self.assertNumQueries(1):
            self.assertIs(has_group_permission(request, ["admin"]), False)
