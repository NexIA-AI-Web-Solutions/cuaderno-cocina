"""Regressions for native endpoints, using only synthetic local data."""
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from cookbook.models import ExportLog, Food, ImportLog, Recipe, Space, Step, Unit, UserFile, UserSpace
from cookbook.views.api import import_files
from cuaderno.models import PackageFormat, PriceVersion


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.TemporaryDirectory(prefix="cuaderno-security-")
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        with scopes_disabled():
            self.space = Space.objects.create(name="Synthetic security")
            self.owner = self.make_user("security-owner")
            self.other = self.make_user("security-other")
            self.private = Recipe.objects.create(space=self.space, name="Private synthetic", private=True, created_by=self.owner)
            self.file = UserFile.objects.create(
                space=self.space, created_by=self.owner, name="synthetic",
                file=SimpleUploadedFile("synthetic.txt", b"synthetic private attachment"),
            )
            step = Step.objects.create(space=self.space, file=self.file)
            self.private.steps.add(step)

    def make_user(self, name):
        user = get_user_model().objects.create_user(username=name, password="synthetic-only")
        membership = UserSpace.objects.create(user=user, space=self.space, active=True)
        membership.groups.add(Group.objects.get_or_create(name="user")[0])
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_cached_export_is_available_only_to_its_owner(self):
        with scopes_disabled():
            log = ExportLog.objects.create(space=self.space, created_by=self.owner, type="DEFAULT")
        cache.set(f"export_file_{log.pk}", {"file": b"private synthetic export", "filename": "synthetic.zip"})
        self.assertEqual(self.client_for(self.other).get(f"/export-file/{log.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.owner).get(f"/export-file/{log.pk}/").status_code, 200)

    def test_private_attachment_download_and_media_enforce_same_acl(self):
        client = self.client_for(self.other)
        self.assertEqual(client.get(f"/api/download-file/{self.file.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/media/{self.file.file.name}").status_code, 404)
        self.assertEqual(self.client_for(self.owner).get(f"/api/download-file/{self.file.pk}/").status_code, 200)
        with scopes_disabled():
            self.private.shared.add(self.other)
        self.assertEqual(client.get(f"/api/download-file/{self.file.pk}/").status_code, 200)

    def test_import_logs_are_scoped_to_creator(self):
        with scopes_disabled():
            hidden = ImportLog.objects.create(space=self.space, created_by=self.owner, type="DEFAULT", msg="Private synthetic recipe")
            own = ImportLog.objects.create(space=self.space, created_by=self.other, type="DEFAULT", msg="Own synthetic recipe")
        client = self.client_for(self.other)
        self.assertEqual(client.get(f"/api/import-log/{hidden.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/import-log/{own.pk}/").status_code, 200)
        listing = client.get("/api/import-log/")
        self.assertNotIn(b"Private synthetic recipe", listing.content)
        self.assertEqual(client.patch(f"/api/import-log/{hidden.pk}/", {"msg": "overwrite"}, format="json").status_code, 404)

    def test_user_file_metadata_and_writes_do_not_bypass_private_recipe_acl(self):
        client = self.client_for(self.other)
        self.assertEqual(client.get(f"/api/user-file/{self.file.pk}/").status_code, 404)
        listing = client.get("/api/user-file/")
        self.assertNotIn(self.file.pk, [item["id"] for item in listing.data["results"]])
        self.assertEqual(client.patch(f"/api/user-file/{self.file.pk}/", {"name": "overwrite"}, format="multipart").status_code, 404)
        self.assertEqual(client.delete(f"/api/user-file/{self.file.pk}/").status_code, 404)
        with scopes_disabled():
            self.file.refresh_from_db()
            self.assertEqual(self.file.name, "synthetic")
            self.private.shared.add(self.other)
        self.assertEqual(client.get(f"/api/user-file/{self.file.pk}/").status_code, 200)
        self.assertEqual(client.patch(f"/api/user-file/{self.file.pk}/", {"name": "overwrite shared"}, format="multipart").status_code, 404)
        self.assertEqual(self.client_for(self.owner).patch(f"/api/user-file/{self.file.pk}/", {"name": "Owner edit"}, format="multipart").status_code, 200)

    @override_settings(CUADERNO_IMPORT_MAX_BYTES=8, CUADERNO_IMPORT_MAX_FILES=2)
    def test_both_import_entrypoints_reject_aggregate_size_before_log_or_thread(self):
        def payload():
            return {"type": "DEFAULT", "files": [SimpleUploadedFile("a.json", b"12345"), SimpleUploadedFile("b.json", b"12345")]}
        with patch("cookbook.views.api.threading.Thread") as thread:
            self.assertEqual(self.client_for(self.owner).post("/api/import/", payload(), format="multipart").status_code, 413)
            request = APIRequestFactory().post("/synthetic-legacy-import/", payload(), format="multipart")
            request.space = self.space
            force_authenticate(request, user=self.owner)
            with scopes_disabled():
                self.assertEqual(import_files(request).status_code, 413)
                self.assertFalse(ImportLog.objects.exists())
            thread.assert_not_called()

    def test_packages_use_current_prices_without_query_per_package(self):
        now = timezone.now()
        with scopes_disabled():
            food = Food.objects.create(space=self.space, name="Synthetic food")
            unit = Unit.objects.create(space=self.space, name="kg")
            packages = [PackageFormat.objects.create(space=self.space, food=food, unit=unit, label=f"Pack {i}", quantity=1, is_reference=(i == 0)) for i in range(12)]
            PriceVersion.objects.create(space=self.space, package=packages[0], created_by=self.owner, amount=Decimal("2"), valid_from=now - timedelta(days=1))
            PriceVersion.objects.create(space=self.space, package=packages[0], created_by=self.owner, amount=Decimal("99"), valid_from=now + timedelta(days=1))
        client = self.client_for(self.owner)
        client.get("/api/cuaderno/packages/")
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/api/cuaderno/packages/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 9)
        by_id = {row["id"]: row for row in response.data}
        self.assertEqual(Decimal(by_id[packages[0].pk]["current_price"]["amount"]), Decimal("2"))
        self.assertIsNone(by_id[packages[1].pk]["current_price"])
