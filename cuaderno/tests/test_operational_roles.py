"""Spanish aliases describe native groups, not a parallel or global read-only RBAC."""

from types import SimpleNamespace

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django_scopes import scopes_disabled
from rest_framework.test import APIClient

from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import RecipeBook, Space, UserSpace
from cuaderno.models import PackageFormat, ServicePlan, SpaceProfile, StockMovement
from cuaderno.services.roles import operational_role
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OperationalRoleTests(ServiceFixtureMixin, TestCase):
    edition_url = "/api/cuaderno/edition/"

    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.guest = self.make_user("role-consulta", "guest", self.household)
            self.profile.edition = SpaceProfile.INTEGRAL
            self.profile.save(update_fields=["edition"])

    def test_spanish_aliases_and_capabilities_match_highest_native_group(self):
        with scopes_disabled():
            UserSpace.objects.get(user=self.admin, space=self.space).groups.add(
                Group.objects.get(name="user"), Group.objects.get(name="guest"),
            )
        for actor, code, label, operate, manage in (
            (self.guest, "guest", "Consulta", False, False),
            (self.user, "user", "Cocina", True, False),
            (self.admin, "admin", "Responsable", True, True),
        ):
            with self.subTest(group=code):
                response = self.client_for(actor).get(self.edition_url)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data.get("operational_role"), {
                    "code": code, "label": label, "space": self.space.pk,
                    "can_operate_cuaderno": operate, "can_manage_edition": manage,
                    "native_permissions_preserved": True,
                })
                response = self.client_for(actor).put(self.edition_url, {"edition": "integral"}, format="json")
                self.assertEqual(response.status_code, 200 if manage else 403, response.data)

    def test_consulta_can_read_costs_but_cannot_write_operational_documents(self):
        client = self.client_for(self.guest)
        for url in (
            f"/api/cuaderno/recipes/{self.recipe.pk}/cost/",
            f"/api/cuaderno/recipes/{self.recipe.pk}/finance/",
            f"/api/cuaderno/recipes/{self.recipe.pk}/ingredient-yields/",
            f"/api/cuaderno/allergens/?recipe={self.recipe.pk}",
        ):
            with self.subTest(read=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
        for url in (
            "/api/cuaderno/packages/", "/api/cuaderno/movements/", "/api/cuaderno/services/",
        ):
            with self.subTest(write=url):
                response = client.post(url, {}, format="json")
                self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(client.get("/api/cuaderno/packages/").status_code, 403)
        with scopes_disabled():
            self.assertEqual(PackageFormat.objects.count(), 1)
            self.assertEqual(ServicePlan.objects.count(), 0)
            self.assertEqual(StockMovement.objects.count(), 0)

    def test_consulta_keeps_native_ownership_writes_without_becoming_operational_user(self):
        client = self.client_for(self.guest)
        response = client.post(
            reverse("api:recipebook-list"), {"name": "Cuaderno propio", "shared": []}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        with scopes_disabled():
            book = RecipeBook.objects.get(pk=response.data["id"])
            self.assertEqual(book.created_by_id, self.guest.pk)
        response = client.patch(
            reverse("api:recipebook-detail", args=[book.pk]), {"name": "Propiedad conservada"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        with scopes_disabled():
            book.refresh_from_db()
            self.assertEqual(book.name, "Propiedad conservada")
        self.assertEqual(client.post("/api/cuaderno/services/", {}, format="json").status_code, 403)

    def test_native_admin_does_not_override_private_recipe_visibility(self):
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.save(update_fields=["private"])
        for actor in (self.guest, self.helper, self.admin):
            with self.subTest(actor=actor.username):
                response = self.client_for(actor).get(f"/api/cuaderno/recipes/{self.recipe.pk}/cost/")
                self.assertEqual(response.status_code, 404, response.data)
                self.assertNotIn(self.recipe.name, str(response.data))
        self.assertEqual(self.client_for(self.user).get(f"/api/cuaderno/recipes/{self.recipe.pk}/cost/").status_code, 200)

    def test_space_switch_and_group_downgrade_refresh_role_and_actual_write_permission(self):
        with scopes_disabled():
            foreign = Space.objects.create(name="Role other Space", created_by=self.admin)
            SpaceProfile.objects.create(space=foreign, edition=SpaceProfile.INTEGRAL)
            membership = UserSpace.objects.create(user=self.admin, space=foreign, active=False)
            membership.groups.add(Group.objects.get_or_create(name="guest")[0])
        client = self.client_for(self.admin)
        self.assertEqual(client.get(self.edition_url).data.get("operational_role", {}).get("label"), "Responsable")
        self.assertEqual(client.get(f"/api/switch-active-space/{foreign.pk}/").status_code, 200)
        response = client.get(self.edition_url)
        self.assertEqual(response.data.get("operational_role", {}).get("label"), "Consulta")
        self.assertEqual(response.data.get("operational_role", {}).get("space"), foreign.pk)
        self.assertEqual(client.put(self.edition_url, {"edition": "esencial"}, format="json").status_code, 403)
        self.assertEqual(client.get(f"/api/cuaderno/recipes/{self.recipe.pk}/cost/").status_code, 404)
        self.assertEqual(client.get(f"/api/switch-active-space/{self.space.pk}/").status_code, 200)
        with scopes_disabled():
            UserSpace.objects.get(user=self.admin, space=self.space).groups.set([Group.objects.get(name="guest")])
        self.assertEqual(client.get(self.edition_url).data.get("operational_role", {}).get("label"), "Consulta")
        self.assertEqual(client.put(self.edition_url, {"edition": "esencial"}, format="json").status_code, 403)

    def test_edition_put_includes_the_same_current_role_metadata(self):
        response = self.client_for(self.admin).put(self.edition_url, {"edition": "integral"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["operational_role"]["code"], "admin")
        self.assertEqual(response.data["operational_role"]["label"], "Responsable")
        self.assertIs(response.data["operational_role"]["can_manage_edition"], True)

    def test_role_metadata_reuses_native_request_snapshot_without_extra_queries(self):
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.admin, space=self.space)
            request = SimpleNamespace(user=self.admin, space=self.space, user_space=membership)
            self.assertTrue(has_group_permission(request, ["guest"]))
            with self.assertNumQueries(0):
                self.assertEqual(operational_role(request)["label"], "Responsable")

    def test_anonymous_cannot_read_role_or_edition(self):
        response = APIClient().get(self.edition_url)
        self.assertEqual(response.status_code, 403)
