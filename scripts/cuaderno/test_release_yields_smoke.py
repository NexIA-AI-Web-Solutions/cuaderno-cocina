import unittest

from scripts.cuaderno.release_http_smoke import SmokeFailure
from scripts.cuaderno.release_yields_smoke import (
    _assert_same_snapshots,
    _confirmed_services,
    _restore_original,
    _yield_fixture,
)


REVISION = "a" * 64


def yield_payload(**line_changes):
    line = {
        "id": 31,
        "food_name": "Aceite DEMO",
        "amount": "400.0000000000000000",
        "unit": "mL",
        "quantity_basis": "gross",
        "yield_ratio": None,
        "is_subrecipe": False,
    }
    line.update(line_changes)
    return {
        "recipe_id": 21,
        "edition": "profesional",
        "revision": REVISION,
        "can_edit": True,
        "ingredients": [line],
    }


class ReleaseYieldsSmokeUnitTests(unittest.TestCase):
    def test_fixture_requires_exact_unique_salsa_oil_line_and_sha_revision(self):
        revision, line = _yield_fixture(yield_payload(), recipe_id=21, edition="profesional", can_edit=True)
        self.assertEqual(revision, REVISION)
        self.assertEqual(line["id"], 31)

        invalid_payloads = (
            yield_payload(food_name="Other food"),
            yield_payload(amount="401"),
            yield_payload(unit="L"),
            yield_payload(is_subrecipe=True),
            yield_payload(quantity_basis="net_usable", yield_ratio="0.8"),
            {**yield_payload(), "revision": "A" * 64},
            {**yield_payload(), "revision": "a" * 63},
            {**yield_payload(), "ingredients": yield_payload()["ingredients"] * 2},
            {**yield_payload(), "recipe_id": 22},
            {**yield_payload(), "edition": "integral"},
            {**yield_payload(), "can_edit": False},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(SmokeFailure):
                _yield_fixture(payload, recipe_id=21, edition="profesional", can_edit=True)

    def test_fixture_accepts_only_the_requested_policy(self):
        _, gross = _yield_fixture(
            yield_payload(), recipe_id=21, edition="profesional", can_edit=True,
            expected_basis="gross", expected_ratio=None,
        )
        self.assertEqual(gross["quantity_basis"], "gross")
        net_payload = yield_payload(quantity_basis="net_usable", yield_ratio="0.8000000000000000")
        _, net = _yield_fixture(
            net_payload, recipe_id=21, edition="profesional", can_edit=True,
            expected_basis="net_usable", expected_ratio="0.8",
        )
        self.assertEqual(net["quantity_basis"], "net_usable")
        with self.assertRaises(SmokeFailure):
            _yield_fixture(
                net_payload, recipe_id=21, edition="profesional", can_edit=True,
                expected_basis="net_usable", expected_ratio=None,
            )

    def test_confirmed_service_snapshot_is_complete_and_keeps_frozen_timestamps(self):
        payload = [
            {"id": 1, "state": "draft", "snapshot": {}},
            {"id": 2, "state": "confirmed", "snapshot": {"confirmed_at": "frozen-one"}},
            {"id": 3, "state": "produced", "snapshot": {"confirmed_at": "frozen-two"}},
        ]
        self.assertEqual(
            _confirmed_services(payload),
            [{"id": 2, "state": "confirmed", "snapshot": {"confirmed_at": "frozen-one"}}],
        )
        with self.assertRaises(SmokeFailure):
            _confirmed_services([{"id": index, "state": "confirmed"} for index in range(100)])
        with self.assertRaises(SmokeFailure):
            _confirmed_services({"results": []})

    def test_snapshot_comparison_discards_only_wrapper_timestamp(self):
        before = {
            "stock": {"count": 1, "results": [{"id": 1, "updated_at": "frozen"}]},
            "services": [{"id": 2, "snapshot": {"created_at": "frozen"}}],
        }
        _assert_same_snapshots(before, {
            "stock": {"timestamp": "transport-later", **before["stock"]},
            "services": before["services"],
        })
        for changed in (
            {"stock": {"count": 1, "results": [{"id": 1, "updated_at": "changed"}]},
             "services": before["services"]},
            {"stock": before["stock"],
             "services": [{"id": 2, "snapshot": {"created_at": "changed"}}]},
        ):
            with self.subTest(changed=changed), self.assertRaises(SmokeFailure):
                _assert_same_snapshots(before, changed)

    def test_recovery_refuses_to_overwrite_an_unknown_policy(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("La recuperación no debe sobrescribir un estado ajeno.")
                return yield_payload(quantity_basis="net_usable", yield_ratio="0.7")

        session = Session()
        with self.assertRaises(SmokeFailure):
            _restore_original(
                session, "/yield/", 21, "profesional", expected_revision="b" * 64,
            )
        self.assertEqual([(method, path) for method, path, _ in session.calls], [("GET", "/yield/")])

    def test_recovery_refuses_same_policy_written_under_another_revision(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("No debe sobrescribir una edición concurrente.")
                return {
                    **yield_payload(quantity_basis="net_usable", yield_ratio="0.8"),
                    "revision": "c" * 64,
                }

        session = Session()
        with self.assertRaises(SmokeFailure):
            _restore_original(
                session, "/yield/", 21, "profesional", expected_revision="b" * 64,
            )
        self.assertEqual([(method, path) for method, path, _ in session.calls], [("GET", "/yield/")])

    def test_recovery_without_our_checkpoint_never_overwrites_net_policy(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("Sin checkpoint propio, la recuperación debe quedar manual.")
                return {
                    **yield_payload(quantity_basis="net_usable", yield_ratio="0.8"),
                    "revision": "b" * 64,
                }

        session = Session()
        with self.assertRaisesRegex(SmokeFailure, "no pertenece a este smoke"):
            _restore_original(
                session, "/yield/", 21, "profesional", expected_revision=None,
            )
        self.assertEqual([(method, path) for method, path, _ in session.calls], [("GET", "/yield/")])

    def test_recovery_uses_our_known_revision_and_validates_restored_fixture(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method == "GET":
                    return {
                        **yield_payload(quantity_basis="net_usable", yield_ratio="0.8"),
                        "revision": "b" * 64,
                    }
                self.assertEqual(kwargs["payload"]["revision"], "b" * 64)
                self.assertEqual(kwargs["payload"]["quantity_basis"], "gross")
                self.assertIsNone(kwargs["payload"]["yield_ratio"])
                return {**yield_payload(), "revision": "c" * 64}

        session = Session()
        restored = _restore_original(
            session, "/yield/", 21, "profesional", expected_revision="b" * 64,
        )
        self.assertEqual(restored, "c" * 64)
        self.assertEqual([method for method, _, _ in session.calls], ["GET", "PUT"])

    def test_recovery_accepts_an_already_restored_fixture_without_writing(self):
        class Session:
            def __init__(self):
                self.calls = []

            def json(inner_self, method, path, **kwargs):
                inner_self.calls.append((method, path, kwargs))
                if method != "GET":
                    raise AssertionError("Una política ya restaurada no necesita PUT.")
                return yield_payload()

        session = Session()
        restored = _restore_original(
            session, "/yield/", 21, "profesional", expected_revision=None,
        )
        self.assertEqual(restored, REVISION)
        self.assertEqual([method for method, _, _ in session.calls], ["GET"])


if __name__ == "__main__":
    unittest.main()
