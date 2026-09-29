import io
import json
import stat
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from django.core.exceptions import ValidationError

from cookbook.helper.HelperFunctions import safe_request
from cookbook.integration.integration import Integration
from cookbook.integration.nextcloud_cookbook import NextcloudCookbook
from cookbook.integration.pestle import Pestle


class StreamingResponse:
    def __init__(self, chunks, *, content_length=None, ok=True):
        self._chunks = list(chunks)
        self._content = False
        self._content_consumed = False
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.ok = ok
        self.status_code = 200
        self.closed = False

    def iter_content(self, chunk_size=1):
        yield from self._chunks

    @property
    def content(self):
        if self._content is False:
            return b"".join(self._chunks)
        return self._content

    def json(self):
        return json.loads(self.content)

    def close(self):
        self.closed = True


class SafeRequestTests(TestCase):
    def manager_for(self, response):
        manager = MagicMock()
        manager.send_request.return_value = response
        return manager

    def test_safe_request_buffers_a_bounded_response_closes_stream_and_preserves_json(self):
        response = StreamingResponse([b'{"ok":', b"true}"])
        manager = self.manager_for(response)
        with patch("cookbook.helper.HelperFunctions.Manager", return_value=manager):
            result = safe_request("GET", "https://example.test/data", max_response_bytes=32)
        self.assertIs(result, response)
        self.assertEqual(result.content, b'{"ok":true}')
        self.assertEqual(result.json(), {"ok": True})
        self.assertTrue(result.closed)
        self.assertTrue(result._content_consumed)
        self.assertTrue(manager.send_request.call_args.kwargs["stream"])

    def test_safe_request_rejects_content_length_and_stream_over_limit_and_always_closes(self):
        declared = StreamingResponse([b"small"], content_length=9)
        streamed = StreamingResponse([b"1234", b"56"])
        for response in (declared, streamed):
            manager = self.manager_for(response)
            with self.subTest(headers=response.headers), patch(
                "cookbook.helper.HelperFunctions.Manager", return_value=manager
            ):
                with self.assertRaises(ValidationError):
                    safe_request("GET", "https://example.test/large", max_response_bytes=5, response_chunk_size=4)
                self.assertTrue(response.closed)


class PestleImportTests(TestCase):
    def test_pestle_remote_image_uses_hardened_bounded_request_not_requests_get(self):
        response = StreamingResponse([b""])
        manager = MagicMock()
        manager.send_request.return_value = response
        recipe = SimpleNamespace(steps=MagicMock(), nutrition=None, save=MagicMock())
        importer = object.__new__(Pestle)
        importer.request = SimpleNamespace(
            user=SimpleNamespace(userpreference=SimpleNamespace(show_step_ingredients=True)),
            space=object(),
        )
        payload = {
            "name": "Receta sintética",
            "recipeInstructions": [],
            "image": [{"url": "http://127.0.0.1:9/private"}],
        }
        with patch("cookbook.integration.pestle.Recipe.objects.create", return_value=recipe), patch(
            "requests.get", side_effect=AssertionError("bypass SSRF")
        ), patch("cookbook.helper.HelperFunctions.Manager", return_value=manager):
            self.assertIs(importer.get_recipe_from_file(payload), recipe)
        self.assertTrue(manager.send_request.called)
        config = manager.send_request.call_args
        self.assertEqual(config.args[:2], ("GET", payload["image"][0]["url"]))


class ZipValidationTests(TestCase):
    def importer(self):
        return object.__new__(Integration)

    def archive(self, entries):
        stream = io.BytesIO()
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            for name, payload, attrs in entries:
                if attrs is None:
                    archive.writestr(name, payload)
                else:
                    info = ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = attrs
                    archive.writestr(info, payload)
        stream.seek(0)
        return stream

    def test_zip_rejects_traversal_absolute_backslash_and_symlink_members(self):
        malicious = [
            ("../escape.json", b"{}", None),
            ("/absolute.json", b"{}", None),
            ("folder\\escape.json", b"{}", None),
            ("link.json", b"target", (stat.S_IFLNK | 0o777) << 16),
        ]
        for entry in malicious:
            with self.subTest(name=entry[0]), self.assertRaises(Exception):
                self.importer().get_zip_file(self.archive([entry]))

    def test_zip_rejects_extreme_compression_ratio_but_accepts_small_regular_archive(self):
        with self.assertRaises(Exception):
            self.importer().get_zip_file(self.archive([("bomb.json", b"A" * 100_000, None)]))
        archive = self.importer().get_zip_file(self.archive([("recipes/one.json", b'{"name":"Uno"}', None)]))
        self.assertEqual(self.importer().safe_read(archive, "recipes/one.json"), b'{"name":"Uno"}')


class NextcloudExportTests(TestCase):
    def test_export_sanitizes_recipe_name_to_one_relative_zip_component(self):
        space = object()
        importer = object.__new__(NextcloudCookbook)
        importer.request = SimpleNamespace(space=space)
        importer.get_file_from_recipe = lambda recipe: ("recipe.json", "{}")

        class MissingImage:
            @property
            def file(self):
                raise ValueError("sin imagen")

        recipe = SimpleNamespace(pk=1, internal=True, space=space, name="../../escape\\nested", image=MissingImage())
        log = SimpleNamespace(exported_recipes=0, msg="", save=lambda: None)
        _, payload = importer.get_files_from_recipes([recipe], log, {})[0]
        with ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
        self.assertEqual(names, ["escape-nested/recipe.json"])
        self.assertTrue(all(not name.startswith("/") and ".." not in name.split("/") for name in names))
