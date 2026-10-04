"""Security regression tests for local backup media validation."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
if __package__:
    from .delivery_backup import media_manifest
    from . import restore_smoke
    import importlib
    import sys
    scripts_directory = str(Path(__file__).resolve().parent)
    sys.path.insert(0, scripts_directory)
    try:
        local_up = importlib.import_module("local_up")
    finally:
        sys.path.remove(scripts_directory)
else:
    from delivery_backup import media_manifest
    import local_up
    import restore_smoke


class MediaValidationTest(unittest.TestCase):
    def archive(self, names, kind=tarfile.REGTYPE):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "media.tar"
        with tarfile.open(path, "w") as archive:
            for name in names:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "outside"
                info.size = 4 if kind == tarfile.REGTYPE else 0
                archive.addfile(info, io.BytesIO(b"demo") if info.size else None)
        return path

    def test_regular_file_content_hash(self):
        self.assertEqual(media_manifest(self.archive(["recipes/demo.txt"])), {
            "recipes/demo.txt": {"bytes": 4, "sha256": "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea"}})

    def test_traversal_and_windows_paths_rejected(self):
        for name in ("../secret", "/etc/passwd", "C:/private", "folder\\secret"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                media_manifest(self.archive([name]))

    def test_links_and_devices_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                media_manifest(self.archive(["file"], kind))

    def test_duplicate_media_rejected(self):
        with self.assertRaises(ValueError):
            media_manifest(self.archive(["same", "./same"]))


class SourceIdentityTest(unittest.TestCase):
    def test_source_identity_distinguishes_dirty_snapshots_at_the_same_commit(self):
        commit = "a" * 40
        first = local_up.build_identity(commit, "b" * 64)
        second = local_up.build_identity(commit, "c" * 64)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith(commit))
        self.assertIn("worktree", first)

    def test_untrusted_build_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            local_up.build_identity('unsafe";command', "b" * 64)


class RestoreFingerprintSchemaTest(unittest.TestCase):
    def test_preparation_fingerprint_checks_frozen_items_authors_and_legacy_readonly(self):
        document = {
            "service_id": 7, "state": "confirmed", "can_edit": True, "revision": "a" * 64,
            "items": [{
                "id": 9, "source_step_id": 2, "position": 0, "recipe_id": 3,
                "name": "Preparar", "instruction": "Instrucción DEMO congelada",
                "checked": True, "checked_at": "2026-09-30T00:00:00+00:00", "updated_by": 4,
            }],
        }
        self.assertEqual(restore_smoke.validate_preparation(document, 7, "confirmed"), document)
        for invalid in (
            {**document, "service_id": True}, {**document, "state": "produced"},
            {**document, "revision": "A" * 64}, {**document, "items": {}},
            {**document, "items": [{**document["items"][0], "checked": "true"}]},
            {**document, "items": [{**document["items"][0], "updated_by": None}]},
            {**document, "items": [{**document["items"][0], "checked_at": "2026-09-30T00:00:00"}]},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                restore_smoke.validate_preparation(invalid, 7, "confirmed")
        legacy = {**document, "can_edit": False, "items": []}
        self.assertEqual(restore_smoke.validate_preparation(legacy, 7, "confirmed"), legacy)
        with self.assertRaises(ValueError):
            restore_smoke.validate_preparation({**legacy, "can_edit": True}, 7, "confirmed")
        with self.assertRaises(ValueError):
            restore_smoke.validate_preparation({**document, "state": "draft", "can_edit": False}, 7, "draft")

    def test_extended_documents_each_change_the_restore_fingerprint(self):
        payload = {
            "ingredient_yields": [{"recipe": 1, "document": {"ingredients": []}}],
            "stock_minimums": [{"space": 1, "document": {"items": []}}],
            "replenishments": [{"space": 1, "document": {"items": []}}],
            "preparations": [{"service": 1, "document": {"items": []}}],
        }
        original = restore_smoke.payload_sha256(payload)
        for key in ("ingredient_yields", "stock_minimums", "replenishments", "preparations"):
            changed = {name: list(rows) for name, rows in payload.items()}
            changed[key] = [*changed[key], {"changed": True}]
            with self.subTest(key=key):
                self.assertNotEqual(restore_smoke.payload_sha256(changed), original)

    def test_stock_minimum_envelope_requires_household_locations_and_audit_metadata(self):
        document = {
            "edition": "integral",
            "household": {"id": 7, "name": "Cocina sintética"},
            "locations": [{"id": 8, "name": "Seco"}],
            "items": [{
                "id": 9,
                "household": 7,
                "food": 10,
                "food_name": "Harina",
                "unit": 11,
                "unit_name": "kg",
                "quantity": "2",
                "location": 8,
                "location_name": "Seco",
                "updated_by": 12,
                "updated_at": "2026-09-30T00:00:00+00:00",
            }],
        }
        self.assertIs(restore_smoke.validate_stock_minimums(document), document)
        for section, field in (("household", "name"), ("locations", "name"), ("items", "updated_at")):
            broken = {
                **document,
                "household": dict(document["household"]),
                "locations": [dict(document["locations"][0])],
                "items": [dict(document["items"][0])],
            }
            if section == "household":
                del broken[section][field]
            else:
                del broken[section][0][field]
            with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                restore_smoke.validate_stock_minimums(broken)

    def test_yield_and_replenishment_envelopes_are_not_optional(self):
        yields = {
            "recipe_id": 4,
            "edition": "esencial",
            "can_edit": False,
            "ingredients": [{
                "id": 5,
                "food_name": "Patata",
                "amount": "1",
                "unit": "kg",
                "quantity_basis": "gross",
                "yield_ratio": None,
                "is_subrecipe": False,
            }],
        }
        self.assertIs(restore_smoke.validate_ingredient_yields(yields, 4, "esencial"), yields)
        self.assertEqual(restore_smoke.validate_replenishment({"items": []}), {"items": []})
        editable_esencial = {**yields, "can_edit": True}
        with self.assertRaises(ValueError):
            restore_smoke.validate_ingredient_yields(editable_esencial, 4, "esencial")
        with self.assertRaises(ValueError):
            restore_smoke.validate_ingredient_yields({"ingredients": []}, 4, "esencial")
        with self.assertRaises(ValueError):
            restore_smoke.validate_replenishment({})


if __name__ == "__main__":
    unittest.main()
