"""Synthetic PostgreSQL persistence/API contracts; never use a production database."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import tempfile
from threading import Barrier, Event, Thread
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from PIL import Image
from rest_framework.test import APIClient

from cookbook.models import MealPlan, MealType, Recipe, ShareLink, ShoppingListEntry, ShoppingListRecipe, Space
from cuaderno.models import (
    CalendarEntry, MealCourse, MealPlanCourse, MenuTemplate, MenuTemplateEntry, RecipeDietDeclaration,
    RecipeFavorite, RecipeGalleryImage, RecipeVariant, ServicePlan, SpaceProfile,
)
from cuaderno.tests.test_services import ServiceFixtureMixin


def tiny_png():
    output = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return SimpleUploadedFile("test.png", output.getvalue(), content_type="image/png")


class ExtrasFixture(ServiceFixtureMixin):
    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.guest = self.make_user("extras-guest", "guest", self.household)
            self.private = Recipe.objects.create(space=self.space, name="Private source", private=True, created_by=self.helper)
            self.foreign_space = Space.objects.create(name="Foreign extensions")
            self.foreign_recipe = Recipe.objects.create(space=self.foreign_space, name="Foreign recipe", created_by=self.helper)
        self.media = tempfile.TemporaryDirectory(prefix="cuaderno-extras-test-")
        self.addCleanup(self.media.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.media.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)

    def extras_url(self, recipe=None):
        return f"/api/cuaderno/recipes/{(recipe or self.recipe).pk}/extras/"

    def gallery_url(self, recipe=None):
        return f"/api/cuaderno/recipes/{(recipe or self.recipe).pk}/gallery/"

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.content[:2000])
        self.assertTrue(response.get("Content-Type", "").startswith("application/json"))
        return response.data


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecipeExtrasTests(ExtrasFixture, TestCase):
    def test_all_editions_have_eight_unknown_manual_diets(self):
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            self.profile.edition = edition; self.profile.save()
            payload = self.assert_json(self.client_for(self.guest).get(self.extras_url()))
            self.assertEqual(len(payload["diets"]), 8)
            self.assertEqual({x["status"] for x in payload["diets"]}, {"unknown"})
            self.assertFalse(payload["can_edit"])

    def test_guest_owns_favorite_without_receiving_recipe_write_access(self):
        client = self.client_for(self.guest)
        url = f"/api/cuaderno/recipes/{self.recipe.pk}/favorite/"
        for _ in range(2):
            self.assertTrue(self.assert_json(client.put(url, {"favorite": True}, format="json"))["is_favorite"])
        self.assertEqual(RecipeFavorite.objects.filter(user=self.guest, recipe=self.recipe).count(), 1)
        self.assertEqual(RecipeFavorite.objects.filter(user=self.user).count(), 0)
        revision = self.assert_json(client.get(self.extras_url()))["revision"]
        self.assertEqual(client.put(self.extras_url(), {"revision": revision, "diets": []}, format="json").status_code, 403)
        self.assertEqual(client.put(url, {"favorite": True, "user": self.user.pk}, format="json").status_code, 400)

    def test_favorites_hide_recipe_after_share_revocation(self):
        with scopes_disabled():
            self.private.shared.add(self.guest)
        client = self.client_for(self.guest)
        url = f"/api/cuaderno/recipes/{self.private.pk}/favorite/"
        self.assert_json(client.put(url, {"favorite": True}, format="json"))
        self.assertEqual(self.assert_json(client.get("/api/cuaderno/favorites/"))["count"], 1)
        with scopes_disabled():
            self.private.shared.remove(self.guest)
        self.assertEqual(self.assert_json(client.get("/api/cuaderno/favorites/"))["count"], 0)
        self.assertEqual(client.put(url, {"favorite": False}, format="json").status_code, 404)

    def test_diet_changes_persist_and_stale_revision_cannot_overwrite(self):
        client = self.client_for(self.user)
        revision = self.assert_json(client.get(self.extras_url()))["revision"]
        payload = {"revision": revision, "diets": [{"slug": "celiacos", "status": "unsuitable", "note": "Declaración manual"}]}
        saved = self.assert_json(client.put(self.extras_url(), payload, format="json"))
        self.assertEqual(saved["diets"][0]["status"], "unsuitable")
        self.assertEqual(RecipeDietDeclaration.objects.get(recipe=self.recipe, slug="celiacos").updated_by, self.user)
        self.assertEqual(client.put(self.extras_url(), payload, format="json").status_code, 409)
        self.assertEqual(client.put(self.extras_url(), {"diets": []}, format="json").status_code, 428)

    def test_invisible_variant_rolls_back_diet_changes_in_same_request(self):
        client = self.client_for(self.user)
        revision = self.assert_json(client.get(self.extras_url()))["revision"]
        result = client.put(self.extras_url(), {"revision": revision, "variant_of": self.private.pk,
                            "diets": [{"slug": "diabetes", "status": "suitable"}]}, format="json")
        self.assertEqual(result.status_code, 404)
        self.assertFalse(RecipeDietDeclaration.objects.filter(recipe=self.recipe).exists())
        self.assertFalse(RecipeVariant.objects.filter(recipe=self.recipe).exists())

    def test_variant_cycle_and_foreign_reference_are_rejected(self):
        with scopes_disabled():
            source = Recipe.objects.create(space=self.space, name="Source", created_by=self.user)
            RecipeVariant.objects.create(space=self.space, recipe=source, source_recipe=self.recipe, created_by=self.user)
        client = self.client_for(self.user)
        revision = self.assert_json(client.get(self.extras_url()))["revision"]
        for target, status in ((source.pk, 400), (self.recipe.pk, 400), (self.foreign_recipe.pk, 404)):
            self.assertEqual(client.put(self.extras_url(), {"revision": revision, "variant_of": target}, format="json").status_code, status)

    def test_variant_lineage_hides_private_source_after_revocation(self):
        with scopes_disabled():
            self.private.shared.add(self.user)
            RecipeVariant.objects.create(space=self.space, recipe=self.recipe, source_recipe=self.private, created_by=self.user)
        client = self.client_for(self.user)
        self.assertEqual(self.assert_json(client.get(self.extras_url()))["variant_of"]["id"], self.private.pk)
        with scopes_disabled():
            self.private.shared.remove(self.user)
        value = self.assert_json(client.get(self.extras_url()))
        self.assertIsNone(value["variant_of"])
        self.assertNotIn("Private source", str(value))

    def test_gallery_upload_decodes_and_uses_authorized_uuid_media(self):
        client = self.client_for(self.user)
        payload = self.assert_json(client.post(self.gallery_url(), {"image": tiny_png(), "caption": "Vista"}, format="multipart"), 201)
        row = RecipeGalleryImage.objects.get(recipe=self.recipe)
        self.assertRegex(row.image.name, r"^recipes/gallery/[a-f0-9]{32}\.png$")
        response = client.get(payload["gallery"][0]["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response.close()
        self.assertEqual(APIClient().get(payload["gallery"][0]["url"]).status_code, 404)

    def test_gallery_rejects_active_and_malformed_uploads_without_rows(self):
        client = self.client_for(self.user)
        for content in (b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>', b"not a png"):
            response = client.post(self.gallery_url(), {"image": SimpleUploadedFile("fake.png", content, content_type="image/png")}, format="multipart")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(RecipeGalleryImage.objects.exists())
        self.assertFalse(list(Path(self.media.name).rglob("*.*")))

    def test_gallery_failure_after_storage_rolls_back_row_and_file(self):
        with patch("cuaderno.api.recipe_extras.extras_payload", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.client_for(self.user).post(self.gallery_url(), {"image": tiny_png()}, format="multipart")
        self.assertFalse(RecipeGalleryImage.objects.exists())
        self.assertFalse(list(Path(self.media.name).rglob("*.png")))

    def test_gallery_cap_and_unauthorized_upload(self):
        for index in range(20):
            RecipeGalleryImage.objects.create(space=self.space, recipe=self.recipe, created_by=self.user,
                                               position=index, image=f"recipes/gallery/seed{index}.png")
        self.assertEqual(self.client_for(self.user).post(self.gallery_url(), {"image": tiny_png()}, format="multipart").status_code, 400)
        self.assertEqual(self.client_for(self.guest).post(self.gallery_url(), {"image": tiny_png()}, format="multipart").status_code, 403)
        self.assertEqual(self.client_for(self.user).post(self.gallery_url(self.private), {"image": tiny_png()}, format="multipart").status_code, 404)

    def test_gallery_share_capability_authorizes_only_its_recipe(self):
        with scopes_disabled():
            own_share = ShareLink.objects.create(space=self.space, recipe=self.private, created_by=self.helper)
            other_share = ShareLink.objects.create(space=self.space, recipe=self.recipe, created_by=self.user)
        payload = self.assert_json(self.client_for(self.helper).post(self.gallery_url(self.private), {"image": tiny_png()}, format="multipart"), 201)
        url = payload["gallery"][0]["url"]
        self.assertEqual(APIClient().get(url, {"share": str(other_share.uuid)}).status_code, 404)
        response = APIClient().get(url, {"share": str(own_share.uuid)})
        self.assertEqual(response.status_code, 200); response.close()
        image_id = payload["gallery"][0]["id"]
        self.assert_json(self.client_for(self.helper).delete(f"{self.gallery_url(self.private)}{image_id}/"))
        self.assertEqual(APIClient().get(url, {"share": str(own_share.uuid)}).status_code, 404)

    def test_native_recipe_delete_removes_gallery_only_after_commit(self):
        with scopes_disabled():
            disposable = Recipe.objects.create(space=self.space, name="Disposable", created_by=self.user)
        self.assert_json(self.client_for(self.user).post(self.gallery_url(disposable), {"image": tiny_png()}, format="multipart"), 201)
        row = RecipeGalleryImage.objects.get(recipe=disposable)
        path = Path(self.media.name) / row.image.name
        with self.captureOnCommitCallbacks(execute=True):
            with scopes_disabled():
                disposable.delete()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_rolled_back_gallery_delete_keeps_file_and_row(self):
        self.assert_json(self.client_for(self.user).post(self.gallery_url(), {"image": tiny_png()}, format="multipart"), 201)
        row = RecipeGalleryImage.objects.get(recipe=self.recipe)
        path = Path(self.media.name) / row.image.name
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                row.delete()
                raise RuntimeError("rollback synthetic delete")
        self.assertTrue(path.exists())
        self.assertEqual(RecipeGalleryImage.objects.filter(recipe=self.recipe).count(), 1)


class PlanningFixture(ExtrasFixture):
    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.meal_type = MealType.objects.create(space=self.space, name="Comida", created_by=self.user)
            self.foreign_type = MealType.objects.create(space=self.foreign_space, name="Foreign meal", created_by=self.helper)
        self.course = MealCourse.objects.create(space=self.space, meal_type=self.meal_type, name="Principal")

    def native_plan(self, *, user=None, recipe=None, day=7):
        with scopes_disabled():
            when = timezone.make_aware(datetime(2026, 10, day, 12))
            return MealPlan.objects.create(space=self.space, created_by=user or self.user,
                                          recipe=recipe or self.recipe, meal_type=self.meal_type,
                                          from_date=when, to_date=when, servings=Decimal("12.5"))

    def template(self, **entry_overrides):
        entry = {"day_index": 34, "meal_type": self.meal_type.pk, "course": self.course.pk,
                 "recipe": self.recipe.pk, "title": "", "source_url": "https://example.com/recipe", "servings": "12.5"}
        entry.update(entry_overrides)
        return self.client_for(self.user).post("/api/cuaderno/planning/templates/", {
            "name": "Cinco semanas", "weeks": 5, "entries": [entry]}, format="json")

    def apply(self, template, **overrides):
        data = {"revision": template["revision"], "start_date": "2026-10-01", "overwrite": False}
        data.update(overrides)
        return self.client_for(self.user).post(f'/api/cuaderno/planning/templates/{template["id"]}/apply/', data, format="json")

    def planning(self, user=None, **query):
        return self.client_for(user or self.user).get("/api/cuaderno/planning/", {
            "from_date": "2026-10-01", "to_date": "2026-11-04", **query})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PlanningExtensionTests(PlanningFixture, TestCase):
    def test_template_fifth_week_instantiates_native_rows_exactly(self):
        template = self.assert_json(self.template(), 201)
        applied = self.assert_json(self.apply(template), 201)
        with scopes_disabled():
            plan = MealPlan.objects.get(pk=applied["created_ids"][0])
            self.assertEqual(timezone.localdate(plan.from_date).isoformat(), "2026-11-04")
            self.assertEqual(plan.servings, Decimal("12.5"))
            self.assertEqual(plan.recipe_id, self.recipe.pk)
            self.assertEqual(plan.meal_type_id, self.meal_type.pk)
        self.assertEqual(MealPlanCourse.objects.get(meal_plan=plan).course, self.course)
        self.assertEqual(self.apply(template).status_code, 409)

    def test_overwrite_only_replaces_same_template_requester_and_date(self):
        template = self.assert_json(self.template(), 201)
        unrelated = self.native_plan(user=self.helper)
        first = self.assert_json(self.apply(template), 201)
        second = self.assert_json(self.apply(template, overwrite=True), 201)
        self.assertEqual(second["replaced_ids"], first["created_ids"])
        with scopes_disabled():
            self.assertTrue(MealPlan.objects.filter(pk=unrelated.pk).exists())
            self.assertFalse(MealPlan.objects.filter(pk__in=first["created_ids"]).exists())

    def test_overwrite_preserves_shopping_dependencies(self):
        template = self.assert_json(self.template(), 201)
        first = self.assert_json(self.apply(template), 201)
        with scopes_disabled():
            ShoppingListRecipe.objects.create(space=self.space, created_by=self.user, recipe=self.recipe,
                                               mealplan_id=first["created_ids"][0], servings=12)
        self.assertEqual(self.apply(template, overwrite=True).status_code, 409)
        with scopes_disabled():
            self.assertTrue(MealPlan.objects.filter(pk__in=first["created_ids"]).exists())
            self.assertEqual(ShoppingListRecipe.objects.count(), 1)

    def test_overwrite_preserves_service_dependencies(self):
        template = self.assert_json(self.template(), 201)
        first = self.assert_json(self.apply(template), 201)
        ServicePlan.objects.create(space=self.space, created_by=self.user, title="Preserve service", covers=12,
                                   meal_plan_id=first["created_ids"][0])
        self.assertEqual(self.apply(template, overwrite=True).status_code, 409)

    def test_template_foreign_private_and_mismatched_course_fail_atomically(self):
        other_type = None
        with scopes_disabled():
            other_type = MealType.objects.create(space=self.space, name="Cena", created_by=self.user)
        wrong_course = MealCourse.objects.create(space=self.space, meal_type=other_type, name="Wrong course")
        for overrides, status in (({"recipe": self.private.pk}, 404), ({"recipe": self.foreign_recipe.pk}, 404),
                                  ({"meal_type": self.foreign_type.pk}, 404), ({"course": wrong_course.pk}, 400)):
            self.assertEqual(self.template(**overrides).status_code, status)
        self.assertEqual(MenuTemplate.objects.count(), 0)

    def test_template_hidden_after_recipe_visibility_is_revoked(self):
        with scopes_disabled():
            self.private.shared.add(self.user)
        template = self.assert_json(self.template(recipe=self.private.pk), 201)
        with scopes_disabled():
            self.private.shared.remove(self.user)
        listing = self.assert_json(self.client_for(self.user).get("/api/cuaderno/planning/templates/"))
        self.assertEqual(listing["count"], 0)
        self.assertEqual(self.apply(template).status_code, 404)

    def test_planning_preserves_native_household_and_recipe_visibility(self):
        own = self.native_plan()
        family = self.native_plan(user=self.helper)
        hidden_household = self.native_plan(user=self.outsider)
        hidden_recipe = self.native_plan(recipe=self.private)
        ids = {row["id"] for row in self.assert_json(self.planning())["meal_plans"]}
        self.assertEqual(ids, {own.pk, family.pk})
        self.assertNotIn(hidden_household.pk, ids); self.assertNotIn(hidden_recipe.pk, ids)

    def test_manual_diet_filter_preserves_unknown(self):
        plan = self.native_plan()
        self.assertEqual(self.assert_json(self.planning(diet="celiacos"))["meal_plans"][0]["diet_status"], "unknown")
        self.assertEqual(self.assert_json(self.planning(diet="celiacos", diet_status="suitable"))["meal_plans"], [])
        RecipeDietDeclaration.objects.create(space=self.space, recipe=self.recipe, slug="celiacos",
                                              status="unsuitable", updated_by=self.user)
        rows = self.assert_json(self.planning(diet="celiacos", diet_status="unsuitable"))["meal_plans"]
        self.assertEqual([r["id"] for r in rows], [plan.pk])

    def test_calendar_absences_are_admin_only_and_not_in_guest_payload(self):
        body = {"kind": "absence", "title": "Ausencia", "member_name": "Persona sintética", "note": "Privado",
                "start_date": "2026-10-07", "end_date": "2026-10-08"}
        url = "/api/cuaderno/planning/events/"
        self.assertEqual(self.client_for(self.user).post(url, body, format="json").status_code, 403)
        saved = self.assert_json(self.client_for(self.admin).post(url, body, format="json"), 201)
        for user in (self.user, self.guest):
            payload = self.assert_json(self.planning(user))
            self.assertEqual(payload["events"], [])
            self.assertNotIn("Persona sintética", str(payload))
            self.assertEqual(self.client_for(user).delete(f'{url}{saved["id"]}/').status_code, 404 if user == self.user else 403)
        self.assertEqual(len(self.assert_json(self.planning(self.admin))["events"]), 1)

    def test_edition_and_guest_operator_guards(self):
        self.profile.edition = SpaceProfile.ESENCIAL; self.profile.save()
        self.assertEqual(self.planning().status_code, 403)
        self.assertEqual(self.template().status_code, 403)
        self.profile.edition = SpaceProfile.PROFESIONAL; self.profile.save()
        self.assert_json(self.planning(self.guest))
        self.assertEqual(self.client_for(self.guest).post("/api/cuaderno/planning/courses/", {
            "name": "Otro", "meal_type": self.meal_type.pk}, format="json").status_code, 403)

    def test_print_orientation_merge_and_hidden_plan_guards(self):
        own = self.native_plan()
        hidden = self.native_plan(user=self.outsider)
        body = {"orientation": "landscape", "menus": [{"name": "Menú", "meal_plan_ids": [own.pk]}]}
        client = self.client_for(self.guest)
        result = self.assert_json(client.post("/api/cuaderno/planning/print/", body, format="json"))
        self.assertEqual(result["orientation"], "landscape"); self.assertFalse(result["merged"])
        self.assertIsNone(result["diet"]); self.assertIsNone(result["diet_label"])
        body["diet"] = "sinlactosa"
        result = self.assert_json(client.post("/api/cuaderno/planning/print/", body, format="json"))
        self.assertEqual(result["diet"], "sinlactosa"); self.assertEqual(result["diet_label"], "Sin lactosa")
        body["menus"].append({"name": "Segundo", "meal_plan_ids": [own.pk]})
        self.assertEqual(client.post("/api/cuaderno/planning/print/", body, format="json").status_code, 403)
        self.profile.edition = SpaceProfile.INTEGRAL; self.profile.save()
        self.assertTrue(self.assert_json(client.post("/api/cuaderno/planning/print/", body, format="json"))["merged"])
        body["menus"][1]["meal_plan_ids"] = [hidden.pk]
        self.assertEqual(client.post("/api/cuaderno/planning/print/", body, format="json").status_code, 404)

    def test_wrong_http_methods_are_405_not_server_errors(self):
        client = self.client_for(self.user)
        self.assertEqual(client.put("/api/cuaderno/planning/courses/", {}, format="json").status_code, 405)
        self.assertEqual(client.post(f"/api/cuaderno/planning/courses/{self.course.pk}/", {}, format="json").status_code, 405)
        self.assertEqual(client.delete(self.gallery_url()).status_code, 405)

    def test_print_invalid_diet_types_are_400_not_500(self):
        plan = self.native_plan()
        for diet in ([], {}, 1, True, "not-a-diet"):
            response = self.client_for(self.user).post("/api/cuaderno/planning/print/", {
                "orientation": "portrait", "menus": [{"name": "Menú", "meal_plan_ids": [plan.pk]}],
                "diet": diet}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_three_editions_and_three_roles_enforce_server_capabilities(self):
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            self.profile.edition = edition; self.profile.save()
            for member in (self.guest, self.user, self.admin):
                with self.subTest(edition=edition, member=member.username):
                    client = self.client_for(member)
                    self.assert_json(client.get(self.extras_url()))
                    favorite = client.put(f"/api/cuaderno/recipes/{self.recipe.pk}/favorite/", {"favorite": True}, format="json")
                    self.assert_json(favorite)
                    self.assertEqual(self.planning(member).status_code, 403 if edition == SpaceProfile.ESENCIAL else 200)
                    response = client.post("/api/cuaderno/planning/courses/", {
                        "name": f"{edition}-{member.pk}", "meal_type": self.meal_type.pk}, format="json")
                    self.assertEqual(response.status_code, 403 if edition == SpaceProfile.ESENCIAL or member == self.guest else 201)

    def test_stale_course_and_calendar_edit_cannot_overwrite(self):
        client = self.client_for(self.user)
        course = next(row for row in self.assert_json(self.planning())["courses"] if row["id"] == self.course.pk)
        data = {"revision": course["revision"], "name": "Segundo", "meal_type": self.meal_type.pk, "position": 1}
        url = f"/api/cuaderno/planning/courses/{self.course.pk}/"
        self.assert_json(client.put(url, data, format="json"))
        self.assertEqual(client.put(url, data, format="json").status_code, 409)
        self.assertEqual(client.delete(url, {"revision": course["revision"]}).status_code, 428)
        self.assertEqual(client.delete(url + "?revision=" + course["revision"]).status_code, 409)
        event_data = {"kind": "event", "title": "Evento", "start_date": "2026-10-07", "end_date": "2026-10-07"}
        saved = self.assert_json(client.post("/api/cuaderno/planning/events/", event_data, format="json"), 201)
        event_data.update(revision=saved["revision"], title="Cambio")
        url = f'/api/cuaderno/planning/events/{saved["id"]}/'
        self.assert_json(client.put(url, event_data, format="json"))
        self.assertEqual(client.put(url, event_data, format="json").status_code, 409)

    def test_template_calendar_overflow_is_validation_error_with_no_partial_rows(self):
        template = self.assert_json(self.template(), 201)
        self.assertEqual(self.apply(template, start_date="9999-12-31").status_code, 400)
        with scopes_disabled():
            self.assertEqual(MealPlan.objects.count(), 0)

    def test_native_space_delete_removes_only_own_extensions(self):
        # A fresh Space avoids unrelated pre-existing protected stock histories.
        with scopes_disabled():
            disposable = Space.objects.create(name="Disposable extension space")
            recipe = Recipe.objects.create(space=disposable, name="Own disposable recipe", created_by=self.user)
            meal_type = MealType.objects.create(space=disposable, name="Own meal", created_by=self.user)
            when = timezone.make_aware(datetime(2026, 10, 7, 12))
            plan = MealPlan.objects.create(space=disposable, created_by=self.user, meal_type=meal_type,
                                          recipe=recipe, from_date=when, to_date=when)
            course = MealCourse.objects.create(space=disposable, meal_type=meal_type, name="Own course")
            template = MenuTemplate.objects.create(space=disposable, name="Own template", weeks=1, created_by=self.user)
            MenuTemplateEntry.objects.create(space=disposable, template=template, day_index=0,
                                               meal_type=meal_type, course=course, recipe=recipe, servings=1)
            MealPlanCourse.objects.create(space=disposable, meal_plan=plan, course=course, source_template=template)
            RecipeFavorite.objects.create(space=disposable, recipe=recipe, user=self.user)
            RecipeDietDeclaration.objects.create(space=disposable, recipe=recipe, slug="fibra", updated_by=self.user)
            RecipeGalleryImage.objects.create(space=disposable, recipe=recipe, created_by=self.user,
                                               image="recipes/gallery/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png")
            CalendarEntry.objects.create(space=disposable, kind="event", title="Own event", start_date="2026-10-07",
                                          end_date="2026-10-07", created_by=self.user)
            disposable_id = disposable.pk
            before_foreign = list(Recipe.objects.filter(space=self.foreign_space).values())
            disposable.safe_delete()
            self.assertEqual(list(Recipe.objects.filter(space=self.foreign_space).values()), before_foreign)
            self.assertFalse(Space.objects.filter(pk=disposable_id).exists())
            self.assertTrue(Space.objects.filter(pk=self.space.pk).exists())
        for model in (MenuTemplate, MenuTemplateEntry, MealPlanCourse, MealCourse, RecipeFavorite,
                      RecipeDietDeclaration, RecipeGalleryImage, CalendarEntry):
            self.assertEqual(model.objects.filter(space_id=disposable_id).count(), 0)

    def test_native_space_delete_rolls_back_extensions_when_history_is_protected(self):
        template = self.assert_json(self.template(), 201)
        before = list(MenuTemplateEntry.objects.filter(template_id=template["id"]).values())
        # This fixture's PriceVersion/PackageFormat protect Food/Unit history.
        with scopes_disabled(), self.assertRaises(ProtectedError):
            self.space.safe_delete()
        self.assertTrue(MenuTemplate.objects.filter(pk=template["id"]).exists())
        self.assertEqual(list(MenuTemplateEntry.objects.filter(template_id=template["id"]).values()), before)
        self.assertTrue(MealCourse.objects.filter(pk=self.course.pk).exists())

    def test_native_meal_type_change_clears_incompatible_course_without_hiding_plan(self):
        template = self.assert_json(self.template(), 201)
        applied = self.assert_json(self.apply(template), 201)
        plan_id = applied["created_ids"][0]
        with scopes_disabled():
            dinner = MealType.objects.create(space=self.space, name="Cena", created_by=self.user)
        response = self.client_for(self.user).patch(f"/api/meal-plan/{plan_id}/", {
            "meal_type": {"id": dinner.pk, "name": dinner.name}, "servings": "12.5"}, format="json")
        self.assertEqual(response.status_code, 200, response.content[:2000])
        extra = MealPlanCourse.objects.get(meal_plan_id=plan_id)
        self.assertIsNone(extra.course_id)
        self.assertEqual(extra.source_template_id, template["id"])
        rows = self.assert_json(self.planning())["meal_plans"]
        self.assertEqual([row["id"] for row in rows], [plan_id])
        self.assertIsNone(rows[0]["course"])

    def test_space_delete_preserves_foreign_protected_planning_reference(self):
        foreign_template = MenuTemplate.objects.create(space=self.foreign_space, name="Foreign preserved", weeks=1, created_by=self.helper)
        foreign_entry = MenuTemplateEntry.objects.create(space=self.foreign_space, template=foreign_template,
                                                          day_index=0, meal_type=self.foreign_type,
                                                          course=self.course, recipe=self.foreign_recipe, servings=1)
        # Such cross-Space data cannot be created through the API. If imported
        # by another writer, deletion still fails closed without erasing it.
        with scopes_disabled(), self.assertRaises(ProtectedError):
            self.space.safe_delete()
        self.assertTrue(MenuTemplateEntry.objects.filter(pk=foreign_entry.pk).exists())
        self.assertTrue(MenuTemplate.objects.filter(pk=foreign_template.pk).exists())
        self.assertTrue(MealCourse.objects.filter(pk=self.course.pk).exists())

    def test_native_delete_reports_protected_template_references_without_losing_data(self):
        saved = self.assert_json(self.template(), 201)
        client = self.client_for(self.user)
        self.assertEqual(client.delete(f"/api/recipe/{self.recipe.pk}/").status_code, 409)
        self.assertEqual(client.delete(f"/api/meal-type/{self.meal_type.pk}/").status_code, 409)
        self.assertTrue(MenuTemplate.objects.filter(pk=saved["id"]).exists())
        with scopes_disabled():
            self.assertTrue(Recipe.objects.filter(pk=self.recipe.pk).exists())
            self.assertTrue(MealType.objects.filter(pk=self.meal_type.pk).exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeShoppingReferenceTests(PlanningFixture, TestCase):
    def inaccessible_plan_ids(self):
        private = self.native_plan(user=self.helper, recipe=self.private)
        other_household = self.native_plan(user=self.outsider)
        with scopes_disabled():
            foreign = MealPlan.objects.create(space=self.foreign_space, created_by=self.helper,
                                               recipe=self.foreign_recipe, meal_type=self.foreign_type,
                                               from_date=private.from_date, to_date=private.to_date, servings=1)
        return [private.pk, other_household.pk, foreign.pk]

    def test_native_shopping_recipe_create_rejects_inaccessible_and_stale_plans(self):
        client = self.client_for(self.user)
        hidden = self.inaccessible_plan_ids()
        cases = [(plan_id, 404) for plan_id in hidden[:2]] + [(hidden[2], 400), (2147483647, 400), ({"id": 1}, 400)]
        for target, expected in cases:
            with self.subTest(target=target):
                response = client.post("/api/shopping-list-recipe/", {
                    "recipe": self.recipe.pk, "mealplan": target, "servings": "12.5"}, format="json")
                self.assertEqual(response.status_code, expected, response.content[:2000])
        with scopes_disabled():
            self.assertFalse(ShoppingListRecipe.objects.exists())
        visible = self.native_plan()
        saved = self.assert_json(client.post("/api/shopping-list-recipe/", {
            "recipe": self.recipe.pk, "mealplan": visible.pk, "servings": "12.5"}, format="json"), 201)
        with scopes_disabled():
            self.assertEqual(ShoppingListRecipe.objects.get(pk=saved["id"]).mealplan_id, visible.pk)

    def test_native_shopping_recipe_update_cannot_replace_reference_with_invisible_or_stale_plan(self):
        visible = self.native_plan()
        with scopes_disabled():
            row = ShoppingListRecipe.objects.create(space=self.space, created_by=self.user,
                                                      recipe=self.recipe, mealplan=visible, servings=Decimal("12.5"))
        client = self.client_for(self.user)
        hidden = self.inaccessible_plan_ids()
        for target, expected in [(hidden[0], 404), (hidden[1], 404), (hidden[2], 400), (2147483647, 400), ([], 400)]:
            with self.subTest(target=target):
                response = client.patch(f"/api/shopping-list-recipe/{row.pk}/", {
                    "mealplan": target, "servings": "99"}, format="json")
                self.assertEqual(response.status_code, expected, response.content[:2000])
                with scopes_disabled():
                    row.refresh_from_db()
                self.assertEqual(row.mealplan_id, visible.pk)
                self.assertEqual(row.servings, Decimal("12.5"))

    def test_recipe_shopping_rejects_stale_invisible_and_malformed_plan_without_fallback(self):
        client = self.client_for(self.user)
        targets = [(pk, 404) for pk in self.inaccessible_plan_ids()] + [(2147483647, 404)]
        targets += [(value, 400) for value in ({}, {"id": True}, [], "1", 0, -1)]
        for target, expected in targets:
            with self.subTest(target=target):
                response = client.put(f"/api/recipe/{self.recipe.pk}/shopping/", {
                    "mealplan": target, "servings": 12.5}, format="json")
                self.assertEqual(response.status_code, expected, response.content[:2000])
        with scopes_disabled():
            self.assertFalse(ShoppingListRecipe.objects.exists())
            self.assertFalse(ShoppingListEntry.objects.exists())

    def test_native_entry_plan_id_is_validated_before_nested_rows_are_saved(self):
        client = self.client_for(self.user)
        targets = [(pk, 404) for pk in self.inaccessible_plan_ids()] + [(2147483647, 404), ({"id": 1}, 400), ([], 400)]
        for target, expected in targets:
            with self.subTest(target=target):
                response = client.post("/api/shopping-list-entry/", {
                    "food": {"id": self.food.pk, "name": self.food.name}, "amount": "2", "mealplan_id": target}, format="json")
                self.assertEqual(response.status_code, expected, response.content[:2000])
        with scopes_disabled():
            self.assertFalse(ShoppingListRecipe.objects.exists())
            self.assertFalse(ShoppingListEntry.objects.exists())
        visible = self.native_plan()
        saved = self.assert_json(client.post("/api/shopping-list-entry/", {
            "food": {"id": self.food.pk, "name": self.food.name}, "amount": "2", "mealplan_id": visible.pk}, format="json"), 201)
        with scopes_disabled():
            self.assertEqual(ShoppingListEntry.objects.get(pk=saved["id"]).list_recipe.mealplan_id, visible.pk)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GalleryConcurrencyTests(ExtrasFixture, TransactionTestCase):
    def test_two_uploads_at_nineteen_images_cannot_exceed_twenty(self):
        for index in range(19):
            RecipeGalleryImage.objects.create(space=self.space, recipe=self.recipe, created_by=self.user,
                                               position=index, image=f"recipes/gallery/seed{index}.png")
        barrier, outcomes, failures = Barrier(2), [], []

        def upload():
            close_old_connections()
            try:
                client = self.client_for(self.user)
                barrier.wait(timeout=10)
                outcomes.append(client.post(self.gallery_url(), {"image": tiny_png()}, format="multipart").status_code)
            except Exception as exc:
                failures.append(repr(exc))
            finally:
                connections.close_all()

        threads = [Thread(target=upload) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(sorted(outcomes), [201, 400])
        self.assertEqual(RecipeGalleryImage.objects.filter(recipe=self.recipe).count(), 20)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativePlanningConcurrencyTests(PlanningFixture, TransactionTestCase):
    def test_native_update_joins_space_lock_before_template_overwrite(self):
        from cuaderno.services.functional_access import lock_space
        template = self.assert_json(self.template(), 201)
        applied = self.assert_json(self.apply(template), 201)
        plan_id = applied["created_ids"][0]
        entered, finished, outcomes, failures = Event(), Event(), [], []

        def observed_lock(request):
            if request.path.startswith("/api/meal-plan/"):
                entered.set()
            return lock_space(request)

        def native_update():
            close_old_connections()
            try:
                client = self.client_for(self.user)
                response = client.patch(f"/api/meal-plan/{plan_id}/", {"title": "Native edit", "servings": "12.5"}, format="json")
                outcomes.append(response.status_code)
            except Exception as exc:
                failures.append(repr(exc))
            finally:
                finished.set(); connections.close_all()

        with patch("cuaderno.services.functional_access.lock_space", side_effect=observed_lock):
            with transaction.atomic(), scopes_disabled():
                Space.objects.select_for_update().get(pk=self.space.pk)
                thread = Thread(target=native_update); thread.start()
                self.assertTrue(entered.wait(10), "Native calendar mutation must use the actual shared lock helper.")
                self.assertFalse(finished.wait(0.1), "Native writer escaped the held PostgreSQL Space lock.")
                # The same connection owns the real Space lock and replaces
                # only its own template rows before the native writer resumes.
                replacement = self.assert_json(self.apply(template, overwrite=True), 201)
            thread.join(timeout=30)
        self.assertFalse(thread.is_alive()); self.assertEqual(failures, [])
        self.assertEqual(outcomes, [404])
        with scopes_disabled():
            self.assertFalse(MealPlan.objects.filter(pk=plan_id).exists())
            self.assertEqual(MealPlan.objects.filter(pk__in=replacement["created_ids"]).count(), 1)


    def test_native_shopping_create_waits_for_space_lock_and_rejects_replaced_plan(self):
        from cuaderno.services.functional_access import lock_space
        template = self.assert_json(self.template(), 201)
        plan_id = self.assert_json(self.apply(template), 201)["created_ids"][0]
        entered, finished, outcomes, failures = Event(), Event(), [], []

        def observed_lock(request):
            if request.path == "/api/shopping-list-recipe/":
                entered.set()
            return lock_space(request)

        def native_create():
            close_old_connections()
            try:
                response = self.client_for(self.user).post("/api/shopping-list-recipe/", {
                    "recipe": self.recipe.pk, "mealplan": plan_id, "servings": "12.5"}, format="json")
                outcomes.append(response.status_code)
            except Exception as exc:
                failures.append(repr(exc))
            finally:
                finished.set(); connections.close_all()

        thread = Thread(target=native_create)
        with patch("cuaderno.services.functional_access.lock_space", side_effect=observed_lock):
            try:
                with transaction.atomic(), scopes_disabled():
                    Space.objects.select_for_update().get(pk=self.space.pk)
                    thread.start()
                    self.assertTrue(entered.wait(10), "Native shopping creation must use the shared lock helper.")
                    self.assertFalse(finished.wait(0.1), "Native shopping writer escaped the held PostgreSQL Space lock.")
                    replacement = self.assert_json(self.apply(template, overwrite=True), 201)
            finally:
                if thread.ident is not None:
                    thread.join(timeout=30)
        self.assertFalse(thread.is_alive()); self.assertEqual(failures, [])
        # Relation validation runs after the lock resumes and sees the deleted
        # old plan: a clean serializer400, with no dangling shopping reference.
        self.assertEqual(outcomes, [400])
        with scopes_disabled():
            self.assertFalse(ShoppingListRecipe.objects.exists())
            self.assertFalse(MealPlan.objects.filter(pk=plan_id).exists())
            self.assertEqual(MealPlan.objects.filter(pk__in=replacement["created_ids"]).count(), 1)
