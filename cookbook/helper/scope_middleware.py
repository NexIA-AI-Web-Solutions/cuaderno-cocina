import re

from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import connections
from django.db.models import Q
from django.urls import reverse
from django_scopes import scope, scopes_disabled
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.exceptions import AuthenticationFailed


from cookbook.helper.permission_helper import create_space_for_user
from cookbook.helper.membership_snapshot import memberships_one_sql
from cookbook.models import UserSpace
from cookbook.views import views
from recipes import settings


class ScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _memberships(user, *, active=None, limit=2):
        """Return at most two fresh memberships and their groups in one query."""
        if connections[user._state.db or "default"].vendor == "postgresql":
            return memberships_one_sql(user, active=active, limit=limit)
        rows = user.userspace_set.select_related("space")
        if active is not None:
            rows = rows.filter(active=active)
        rows = rows.annotate(
            role_names=ArrayAgg(
                "groups__name",
                distinct=True,
                filter=Q(groups__name__isnull=False),
                order_by="groups__name",
            ),
        ).order_by("pk")
        return list(rows[:limit])

    @staticmethod
    def _bind_roles(request, user, membership, *, multiple_active=False):
        known = {"guest", "user", "admin"}
        roles = tuple(role for role in (membership.role_names or ()) if role in known)
        if multiple_active:
            roles = ()
        # Preserve the old fail-closed branch in __call__ without an Exists.
        membership.other_active = multiple_active
        request._group_permission_snapshot = (
            (user.pk, membership.space_id, membership.pk,
             membership.user_id, membership.space_id),
            roles,
        )
        return roles

    def __call__(self, request):
        prefix = settings.SCRIPT_NAME or ''

        # need to disable scopes for writing requests into userpref and enable for loading ?
        if request.path.startswith(prefix + '/api/user-preference/'):
            with scopes_disabled():
                return self.get_response(request)

        # Disable scopes for recipe detail requests with share link
        # This allows users from different spaces to access shared recipes
        # Security is maintained by CustomRecipePermission which validates the share link
        if (request.GET.get('share')
                and re.match(rf'^{re.escape(prefix)}/api/recipe/\d+/?$', request.path)
                and request.method in ('GET', 'HEAD', 'OPTIONS')):
            with scopes_disabled():
                request.space = None
                return self.get_response(request)

        if request.user.is_authenticated:

            if request.path.startswith(prefix + '/admin/'):
                with scopes_disabled():
                    return self.get_response(request)

            if request.path.startswith(prefix + '/signup/') or request.path.startswith(prefix + '/invite/'):
                return self.get_response(request)

            if request.path.startswith(prefix + '/accounts/'):
                return self.get_response(request)

            if request.path.startswith(prefix + '/switch-space/'):
                return self.get_response(request)

            if request.path.startswith(prefix + '/invite/'):
                return self.get_response(request)

            active_memberships = self._memberships(request.user, active=True, limit=2)
            user_space = active_memberships[0] if active_memberships else None
            multiple_active = len(active_memberships) > 1

            if user_space is None:
                # One query replaces the prior count() plus first() pair.
                memberships = self._memberships(request.user, limit=1)
                user_space = memberships[0] if memberships else None
                if user_space is not None:
                    user_space.active = True
                    user_space.save(update_fields=["active"])

            if user_space is None:
                if "signup_token" in request.session:
                    return HttpResponseRedirect(reverse("view_invite", args=[request.session.pop("signup_token", "")]))
                user_space = create_space_for_user(request.user)
                user_space = self._memberships(request.user, active=True, limit=1)[0]

            roles = self._bind_roles(
                request, request.user, user_space, multiple_active=multiple_active,
            )
            if not roles and not user_space.other_active and reverse("account_logout") not in request.path:
                if request.path.startswith(prefix + '/api/'):
                    return JsonResponse({'detail': 'No tienes permisos en este espacio.'}, status=403)
                return views.no_groups(request)

            request.space = user_space.space
            request.user_space = user_space
            with scope(space=request.space):
                return self.get_response(request)
        else:
            if request.path.startswith(prefix + '/api/'):
                try:
                    if auth := OAuth2Authentication().authenticate(request):
                        active_memberships = self._memberships(auth[0], active=True, limit=2)
                        user_space = active_memberships[0] if active_memberships else None
                        if user_space:
                            self._bind_roles(
                                request, auth[0], user_space,
                                multiple_active=len(active_memberships) > 1,
                            )
                            request.space = user_space.space
                            request.user_space = user_space
                            with scope(space=request.space):
                                return self.get_response(request)
                except AuthenticationFailed:
                    pass

            with scopes_disabled():
                request.space = None
                return self.get_response(request)
