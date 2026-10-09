"""Synthetic image contracts; run only against an isolated test PostgreSQL DB."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django_scopes import scopes_disabled
from PIL import Image
from rest_framework.test import APIClient

from cookbook.models import Food
from cuaderno.models import SpaceProfile
from cuaderno.tests.test_functional_extensions import PlanningFixture, tiny_png


def jpeg():
    output = BytesIO()
    Image.new("RGB", (3, 2), "red").save(output, format="JPEG")
    return SimpleUploadedFile("original.jpg", output.getvalue(), content_type="image/jpeg")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EntityMediaTests(PlanningFixture, TestCase):
    def food_url(self, food=None):
        return f"/api/cuaderno/foods/{(food or self.food).pk}/image/"

    def cover_url(self, template):
        return f'/api/cuaderno/planning/templates/{template["id"]}/image/'

    @override_settings(ROOT_URLCONF="cuaderno.urls", DEBUG=True)
    def test_food_photo_upload_content_replace_delete(self):
        client = self.client_for(self.user)
        self.assertEqual(self.assert_json(client.get(self.food_url())), {"image": None, "can_edit": True})
        first = self.assert_json(client.put(self.food_url(), {"image": tiny_png(), "caption": "Arroz"}, format="multipart"))
        from cuaderno.models import FoodImage
        row = FoodImage.objects.get(food=self.food)
        old = Path(self.media.name) / row.image.name
        self.assertNotIn(row.image.name, str(first))
        content = client.get(first["image"]["url"])
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content["Cache-Control"], "private, no-store")
        self.assertEqual(content["X-Content-Type-Options"], "nosniff")
        self.assertTrue(content["Content-Disposition"].startswith("inline;"))
        self.assertTrue(b"".join(content.streaming_content).startswith(b"\x89PNG"))
        self.assertTrue(content.closed)
        with self.captureOnCommitCallbacks(execute=True):
            second = self.assert_json(client.put(self.food_url(), {"image": jpeg()}, format="multipart"))
            self.assertTrue(old.exists())
        self.assertFalse(old.exists())
        self.assertNotEqual(first["image"]["url"], second["image"]["url"])
        row.refresh_from_db()
        new = Path(self.media.name) / row.image.name
        self.assertEqual(second["image"]["caption"], "")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(self.assert_json(client.delete(self.food_url()))["image"])
        self.assertFalse(new.exists())
        self.assertIsNone(self.assert_json(client.delete(self.food_url()))["image"])
        self.assertEqual(client.get(first["image"]["url"]).status_code, 404)

    def test_food_roles_editions_and_foreign_parent(self):
        with scopes_disabled():
            foreign = Food.objects.create(space=self.foreign_space, name="Foreign food")
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            self.profile.edition = edition; self.profile.save()
            for member in (self.guest, self.user, self.admin):
                client = self.client_for(member)
                self.assertEqual(self.assert_json(client.get(self.food_url()))["can_edit"], member != self.guest)
                self.assertEqual(client.put(self.food_url(), {"image": tiny_png()}, format="multipart").status_code,
                                 403 if member == self.guest else 200)
                self.assertEqual(client.get(self.food_url(foreign)).status_code, 404)
                self.assertEqual(client.delete(self.food_url()).status_code, 403 if member == self.guest else 200)
        self.assertIn(APIClient().get(self.food_url()).status_code, (403, 404))
        self.admin.is_staff = True; self.admin.is_superuser = True; self.admin.save()
        self.assertEqual(self.client_for(self.admin).get(self.food_url(foreign)).status_code, 404)

    def test_large_valid_upload_is_resized_preserving_aspect_ratio(self):
        from cuaderno.models import FoodImage
        output = BytesIO()
        Image.new("RGB", (4096, 2048), "blue").save(output, format="JPEG")
        result = self.assert_json(self.client_for(self.user).put(self.food_url(), {
            "image": SimpleUploadedFile("large.jpg", output.getvalue(), content_type="image/jpeg")}, format="multipart"))
        self.assertRegex(result["image"]["url"], r"\?v=[a-f0-9]{16}$")
        row = FoodImage.objects.get(food=self.food)
        with Image.open(Path(self.media.name) / row.image.name) as stored:
            self.assertEqual(stored.size, (2048, 1024))
            self.assertEqual(stored.format, "JPEG")

    def test_jpeg_exif_orientation_is_applied_before_metadata_removal(self):
        from cuaderno.models import FoodImage
        output = BytesIO()
        original = Image.new("RGB", (3, 2), "blue")
        exif = original.getexif()
        exif[274] = 6
        original.save(output, format="JPEG", exif=exif)
        self.assert_json(self.client_for(self.user).put(self.food_url(), {
            "image": SimpleUploadedFile("rotated.jpg", output.getvalue(), content_type="image/jpeg")}, format="multipart"))
        row = FoodImage.objects.get(food=self.food)
        with Image.open(Path(self.media.name) / row.image.name) as stored:
            self.assertEqual(stored.size, (2, 3))
            self.assertFalse(stored.getexif())

    def test_png_preserves_palette_transparency_and_removes_metadata(self):
        from PIL.PngImagePlugin import PngInfo
        from cuaderno.models import FoodImage
        image = Image.new("P", (2, 2))
        image.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        image.putdata([0, 1, 0, 1])
        metadata = PngInfo()
        metadata.add_text("private-location", "synthetic-private-location")
        output = BytesIO()
        image.save(output, format="PNG", transparency=0, pnginfo=metadata)
        raw = output.getvalue() + b"<script>synthetic active trailer</script>"
        self.assert_json(self.client_for(self.user).put(self.food_url(), {
            "image": SimpleUploadedFile("transparent.png", raw, content_type="image/png")}, format="multipart"))
        row = FoodImage.objects.get(food=self.food)
        path = Path(self.media.name) / row.image.name
        self.assertNotIn(b"synthetic-private-location", path.read_bytes())
        self.assertNotIn(b"<script>", path.read_bytes())
        with Image.open(path) as stored:
            self.assertNotIn("private-location", stored.info)
            rgba = stored.convert("RGBA")
            self.assertEqual(rgba.getpixel((0, 0))[3], 0)
            self.assertEqual(rgba.getpixel((1, 0))[3], 255)

    def test_image_model_save_rejects_foreign_parent_space(self):
        from django.core.exceptions import ValidationError
        from cuaderno.models import FoodImage, MenuTemplate, MenuTemplateImage
        template = MenuTemplate.objects.create(space=self.space, name="Own cover", weeks=1, created_by=self.user)
        for model, relation in ((FoodImage, {"food": self.food}), (MenuTemplateImage, {"template": template})):
            row = model(space=self.foreign_space, image="cuaderno/entity-media/" + "a" * 32 + ".png",
                        updated_by=self.user, **relation)
            with self.assertRaises(ValidationError):
                row.save()
            self.assertFalse(model.objects.filter(space=self.foreign_space).exists())

    def test_native_food_merge_api_all_photo_combinations_preserve_related_rows(self):
        from cookbook.models import Ingredient
        from cuaderno.models import FoodImage, PackageFormat
        client = self.client_for(self.user)
        for source_has_photo, target_has_photo in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(source_photo=source_has_photo, target_photo=target_has_photo):
                with scopes_disabled():
                    source = Food.add_root(space=self.space, name=f"Matrix source {source_has_photo}-{target_has_photo}")
                    target = Food.add_root(space=self.space, name=f"Matrix target {source_has_photo}-{target_has_photo}")
                    ingredient = Ingredient.objects.create(space=self.space, food=source, unit=self.kg, amount="3")
                    source_package = PackageFormat.objects.create(space=self.space, food=source, unit=self.kg,
                        label="Source package", quantity="5", is_reference=True)
                    target_package = PackageFormat.objects.create(space=self.space, food=target, unit=self.kg,
                        label="Target package", quantity="10", is_reference=True)
                source_image, target_image = None, None
                if source_has_photo:
                    self.assert_json(client.put(self.food_url(source), {"image": tiny_png(), "caption": "Source image"}, format="multipart"))
                    source_image = FoodImage.objects.get(food=source)
                if target_has_photo:
                    self.assert_json(client.put(self.food_url(target), {"image": jpeg(), "caption": "Target image"}, format="multipart"))
                    target_image = FoodImage.objects.get(food=target)
                chosen = target_image or source_image
                with self.captureOnCommitCallbacks(execute=True):
                    response = client.put(f"/api/food/{source.pk}/merge/{target.pk}/", {}, format="json")
                    self.assertEqual(response.status_code, 200, response.content[:2000])
                    if source_image:
                        self.assertTrue((Path(self.media.name) / source_image.image.name).exists())
                with scopes_disabled():
                    self.assertFalse(Food.objects.filter(pk=source.pk).exists())
                    self.assertTrue(Food.objects.filter(pk=target.pk).exists())
                    ingredient.refresh_from_db()
                    source_package.refresh_from_db()
                    target_package.refresh_from_db()
                    self.assertEqual(ingredient.food_id, target.pk)
                    self.assertEqual(source_package.food_id, target.pk)
                    self.assertEqual(target_package.food_id, target.pk)
                    self.assertFalse(source_package.is_reference)
                    self.assertTrue(target_package.is_reference)
                    self.assertEqual(PackageFormat.objects.filter(food=target).count(), 2)
                self.assertFalse(FoodImage.objects.filter(food_id=source.pk).exists())
                image = self.assert_json(client.get(self.food_url(target)))["image"]
                if chosen is None:
                    self.assertIsNone(image)
                    self.assertFalse(FoodImage.objects.filter(food=target).exists())
                else:
                    retained = FoodImage.objects.get(food=target)
                    self.assertEqual(retained.image.name, chosen.image.name)
                    self.assertEqual(image["caption"], chosen.caption)
                    self.assertTrue((Path(self.media.name) / retained.image.name).exists())
                if source_image and target_image:
                    self.assertFalse((Path(self.media.name) / source_image.image.name).exists())

    def test_native_food_merge_transfers_photo_to_empty_target(self):
        from cuaderno.models import FoodImage
        with scopes_disabled():
            source = Food.objects.create(space=self.space, name="Image merge source")
            target = Food.objects.create(space=self.space, name="Image merge target")
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(source), {"image": tiny_png(), "caption": "Source photo"}, format="multipart"))
        row = FoodImage.objects.get(food=source)
        name = row.image.name
        path = Path(self.media.name) / name
        with self.captureOnCommitCallbacks(execute=True):
            response = client.put(f"/api/food/{source.pk}/merge/{target.pk}/", {}, format="json")
            self.assertEqual(response.status_code, 200, response.content[:2000])
        row.refresh_from_db()
        self.assertEqual(row.food_id, target.pk)
        self.assertEqual(row.image.name, name)
        self.assertTrue(path.exists())
        moved = self.assert_json(client.get(self.food_url(target)))["image"]
        self.assertEqual(moved["caption"], "Source photo")
        self.assertEqual(client.get(saved["image"]["url"]).status_code, 404)
        response = client.get(moved["url"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
        self.assertTrue(response.closed)

    def test_native_food_merge_keeps_target_photo_and_cleans_source_file(self):
        from cuaderno.models import FoodImage
        with scopes_disabled():
            source = Food.objects.create(space=self.space, name="Second image merge source")
            target = Food.objects.create(space=self.space, name="Second image merge target")
        client = self.client_for(self.user)
        self.assert_json(client.put(self.food_url(source), {"image": tiny_png()}, format="multipart"))
        target_payload = self.assert_json(client.put(self.food_url(target), {"image": jpeg(), "caption": "Target photo"}, format="multipart"))
        source_path = Path(self.media.name) / FoodImage.objects.get(food=source).image.name
        target_path = Path(self.media.name) / FoodImage.objects.get(food=target).image.name
        with self.captureOnCommitCallbacks(execute=True):
            response = client.put(f"/api/food/{source.pk}/merge/{target.pk}/", {}, format="json")
            self.assertEqual(response.status_code, 200, response.content[:2000])
            self.assertTrue(source_path.exists())
        self.assertFalse(source_path.exists())
        self.assertTrue(target_path.exists())
        self.assertEqual(self.assert_json(client.get(self.food_url(target)))["image"], target_payload["image"])

    def test_private_recipe_food_and_descendant_images_follow_native_visibility(self):
        from cuaderno.models import FoodImage
        with scopes_disabled():
            private_food = Food.add_root(space=self.space, name="Private image branch", recipe=self.private)
            descendant = private_food.add_child(space=self.space, name="Private image descendant")
        owner = self.client_for(self.helper)
        images = {}
        for food in (private_food, descendant):
            images[food.pk] = self.assert_json(owner.put(self.food_url(food), {
                "image": tiny_png(), "caption": "Private branch image"}, format="multipart"))["image"]
        self.admin.is_staff = True; self.admin.is_superuser = True; self.admin.save()
        for member in (self.user, self.admin):
            client = self.client_for(member)
            for food in (private_food, descendant):
                with self.subTest(member=member.username, food=food.pk):
                    self.assertEqual(client.get(self.food_url(food)).status_code, 404)
                    self.assertEqual(client.get(images[food.pk]["url"]).status_code, 404)
                    with patch("cuaderno.api.entity_media.validated_raster", side_effect=AssertionError("must not decode hidden food")):
                        self.assertEqual(client.put(self.food_url(food), {"image": tiny_png()}, format="multipart").status_code, 404)
                    self.assertEqual(client.delete(self.food_url(food)).status_code, 404)
        guest = self.client_for(self.guest)
        for food in (private_food, descendant):
            self.assertEqual(guest.get(self.food_url(food)).status_code, 404)
            self.assertEqual(guest.get(images[food.pk]["url"]).status_code, 404)
            self.assertEqual(self.assert_json(owner.get(self.food_url(food)))["image"], images[food.pk])
            response = owner.get(images[food.pk]["url"])
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
            self.assertTrue(response.closed)
        self.assertEqual(FoodImage.objects.filter(food_id__in=[private_food.pk, descendant.pk]).count(), 2)
        for food in (private_food, descendant):
            self.assertIsNone(self.assert_json(owner.delete(self.food_url(food)))["image"])

    def test_invalid_upload_preserves_photo_and_no_extra_files(self):
        from cuaderno.models import FoodImage
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        for data in (
            {"image": SimpleUploadedFile("html.png", b"<html><script>1</script></html>")},
            {"image": SimpleUploadedFile("big.png", b"x" * (5 * 1024 * 1024 + 1))},
            {"image": tiny_png(), "caption": "x" * 241},
            {"image": tiny_png(), "url": "https://example.com/secret"},
            {"image": [tiny_png(), tiny_png()]},
            {"image": tiny_png(), "caption": ["one", "two"]},
        ):
            self.assertEqual(client.put(self.food_url(), data, format="multipart").status_code, 400)
        self.assertEqual(self.assert_json(client.get(self.food_url()))["image"], saved["image"])
        self.assertEqual(FoodImage.objects.filter(food=self.food).count(), 1)
        self.assertEqual(len(list(Path(self.media.name).rglob("*.*"))), 1)

    def test_unauthorized_lookup_precedes_decoder(self):
        with scopes_disabled():
            foreign = Food.objects.create(space=self.foreign_space, name="Foreign")
        with patch("cuaderno.api.entity_media.validated_raster", side_effect=AssertionError("must not decode")):
            self.assertEqual(self.client_for(self.user).put(self.food_url(foreign), {"image": tiny_png()}, format="multipart").status_code, 404)
            self.assertEqual(self.client_for(self.guest).put(self.food_url(), {"image": tiny_png()}, format="multipart").status_code, 403)

    def test_failure_after_storage_retains_previous_image(self):
        from cuaderno.models import FoodImage
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        original = FoodImage.objects.get(food=self.food).image.name
        with patch("cuaderno.api.entity_media.media_payload", side_effect=RuntimeError("synthetic DB response failure")):
            with self.assertRaises(RuntimeError):
                client.put(self.food_url(), {"image": jpeg()}, format="multipart")
        self.assertEqual(FoodImage.objects.get(food=self.food).image.name, original)
        self.assertEqual(self.assert_json(client.get(self.food_url()))["image"], saved["image"])
        self.assertEqual(len(list(Path(self.media.name).rglob("*.*"))), 1)

    def test_template_cover_revision_private_recipe_and_print(self):
        template = self.assert_json(self.template(), 201)
        url = self.cover_url(template)
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(url, {"image": tiny_png(), "caption": "Menú"}, format="multipart"))
        current = self.assert_json(client.get(f'/api/cuaderno/planning/templates/{template["id"]}/'))
        self.assertEqual(current["image"], saved["image"])
        self.assertNotEqual(current["revision"], template["revision"])
        old = {"name": template["name"], "weeks": template["weeks"], "revision": template["revision"], "entries": [{key: entry[key] for key in ("day_index", "meal_type", "course", "recipe", "title", "source_url", "servings")} for entry in template["entries"]]}
        self.assertEqual(client.put(f'/api/cuaderno/planning/templates/{template["id"]}/', old, format="json").status_code, 409)
        plan = self.native_plan()
        document = {"orientation": "portrait", "menus": [{"name": "Menú", "meal_plan_ids": [plan.pk], "template_id": template["id"]}]}
        printed = self.assert_json(client.post("/api/cuaderno/planning/print/", document, format="json"))
        self.assertEqual(printed["menus"][0]["image"], saved["image"])
        document["menus"][0]["template_id"] = True
        self.assertEqual(client.post("/api/cuaderno/planning/print/", document, format="json").status_code, 400)
        from cuaderno.models import MenuTemplateEntry
        MenuTemplateEntry.objects.filter(template_id=template["id"]).update(recipe=self.private)
        for endpoint in (url, saved["image"]["url"]):
            self.assertEqual(client.get(endpoint).status_code, 404)
        document["menus"][0]["template_id"] = template["id"]
        self.assertEqual(client.post("/api/cuaderno/planning/print/", document, format="json").status_code, 404)

    def test_foreign_template_cover_is_hidden_even_for_staff(self):
        from cuaderno.models import MenuTemplate
        foreign = MenuTemplate.objects.create(space=self.foreign_space, name="Foreign cover", weeks=1, created_by=self.helper)
        self.admin.is_staff = True; self.admin.is_superuser = True; self.admin.save()
        client = self.client_for(self.admin)
        url = self.cover_url({"id": foreign.pk})
        self.assertEqual(client.get(url).status_code, 404)
        with patch("cuaderno.api.entity_media.validated_raster", side_effect=AssertionError("must not decode")):
            self.assertEqual(client.put(url, {"image": tiny_png()}, format="multipart").status_code, 404)

    def test_native_food_delete_cleans_only_after_commit(self):
        from cuaderno.models import FoodImage
        with scopes_disabled():
            disposable = Food.objects.create(space=self.space, name="Disposable image food")
        client = self.client_for(self.user)
        self.assert_json(client.put(self.food_url(disposable), {"image": tiny_png()}, format="multipart"))
        row = FoodImage.objects.get(food=disposable)
        path = Path(self.media.name) / row.image.name
        with self.captureOnCommitCallbacks(execute=True):
            with scopes_disabled():
                disposable.delete()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_template_plan_and_role_gates(self):
        template = self.assert_json(self.template(), 201)
        for edition in (SpaceProfile.ESENCIAL, SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL):
            self.profile.edition = edition; self.profile.save()
            for member in (self.guest, self.user, self.admin):
                client = self.client_for(member)
                expected = 403 if edition == SpaceProfile.ESENCIAL else 200
                self.assertEqual(client.get(self.cover_url(template)).status_code, expected)
                self.assertEqual(client.put(self.cover_url(template), {"image": tiny_png()}, format="multipart").status_code,
                                 403 if edition == SpaceProfile.ESENCIAL or member == self.guest else 200)

    def test_content_denies_anonymous_and_foreign_corrupt_rows(self):
        from cuaderno.models import FoodImage
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        self.assertIn(APIClient().get(saved["image"]["url"]).status_code, (403, 404))
        FoodImage.objects.filter(food=self.food).update(space=self.foreign_space)
        self.assertIsNone(self.assert_json(client.get(self.food_url()))["image"])
        self.assertEqual(client.get(saved["image"]["url"]).status_code, 404)

    def test_content_rejects_arbitrary_storage_paths_before_open(self):
        from cuaderno.models import FoodImage
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        FoodImage.objects.filter(food=self.food).update(image="../../secret.png")
        with patch("django.core.files.storage.FileSystemStorage.open", side_effect=AssertionError("must not open")):
            self.assertEqual(client.get(saved["image"]["url"]).status_code, 404)

    def test_pixel_limit_and_animation_preserve_previous_photo(self):
        client = self.client_for(self.user)
        saved = self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        huge = BytesIO()
        Image.new("1", (5001, 5000)).save(huge, format="PNG")
        animation = BytesIO()
        Image.new("RGB", (2, 2), "red").save(animation, format="GIF", save_all=True,
                                               append_images=[Image.new("RGB", (2, 2), "blue")])
        for filename, data in (("huge.png", huge.getvalue()), ("animated.gif", animation.getvalue())):
            self.assertEqual(client.put(self.food_url(), {"image": SimpleUploadedFile(filename, data)}, format="multipart").status_code, 400)
        self.assertEqual(self.assert_json(client.get(self.food_url()))["image"], saved["image"])

    def test_delete_rollback_preserves_file_and_row(self):
        from cuaderno.models import FoodImage
        client = self.client_for(self.user)
        self.assert_json(client.put(self.food_url(), {"image": tiny_png()}, format="multipart"))
        row = FoodImage.objects.get(food=self.food)
        path = Path(self.media.name) / row.image.name
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                row.delete()
                raise RuntimeError("synthetic rollback")
        self.assertTrue(path.exists())
        self.assertTrue(FoodImage.objects.filter(food=self.food).exists())

    def test_oauth_scope_and_role_are_both_required(self):
        from django.utils import timezone
        from oauth2_provider.models import AccessToken
        client = APIClient()
        with scopes_disabled():
            read = AccessToken.objects.create(user=self.user, scope="read", expires=timezone.now() + timezone.timedelta(days=1), token="synthetic-food-read")
            write = AccessToken.objects.create(user=self.user, scope="write", expires=timezone.now() + timezone.timedelta(days=1), token="synthetic-food-write")
            guest = AccessToken.objects.create(user=self.guest, scope="read write", expires=timezone.now() + timezone.timedelta(days=1), token="synthetic-food-guest")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {read.token}")
        self.assertEqual(client.get(self.food_url()).status_code, 200)
        self.assertEqual(client.put(self.food_url(), {"image": tiny_png()}, format="multipart").status_code, 403)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {write.token}")
        self.assertEqual(client.get(self.food_url()).status_code, 403)
        self.assertEqual(client.put(self.food_url(), {"image": tiny_png()}, format="multipart").status_code, 200)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {guest.token}")
        self.assertEqual(client.delete(self.food_url()).status_code, 403)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EntityMediaConcurrencyTests(PlanningFixture, TransactionTestCase):
    def test_concurrent_replacements_leave_one_row_and_one_file(self):
        from threading import Barrier, Thread
        from django.db import close_old_connections, connections
        from cuaderno.models import FoodImage
        barrier, outcomes, failures = Barrier(2), [], []
        url = f"/api/cuaderno/foods/{self.food.pk}/image/"

        def replace(upload):
            close_old_connections()
            try:
                client = self.client_for(self.user)
                barrier.wait(timeout=10)
                outcomes.append(client.put(url, {"image": upload()}, format="multipart").status_code)
            except Exception as exc:
                failures.append(repr(exc))
            finally:
                connections.close_all()

        threads = [Thread(target=replace, args=(upload,)) for upload in (tiny_png, jpeg)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(outcomes, [200, 200])
        row = FoodImage.objects.get(food=self.food)
        self.assertEqual(FoodImage.objects.filter(food=self.food).count(), 1)
        files = list(Path(self.media.name).rglob("*.*"))
        self.assertEqual(files, [Path(self.media.name) / row.image.name])
