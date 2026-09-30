from __future__ import annotations

import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

if __package__:
    from . import release_read_contracts as subject
else:
    import release_read_contracts as subject


def role_payload(**changes):
    role = {
        "code": "admin",
        "label": "Responsable",
        "space": 17,
        "can_operate_cuaderno": True,
        "can_manage_edition": True,
        "native_permissions_preserved": True,
    }
    role.update(changes)
    return {"edition": "integral", "operational_role": role}


def allergen_payload(scope_type="food"):
    return {
        "scope": {"type": scope_type, "id": 23, "name": "Aceite DEMO" if scope_type == "food" else "Salsa DEMO"},
        "assessment": "declared",
        "undeclared_means_absent": False,
        "unknown_ingredients": False,
        "foods": [
            {"id": 23, "name": "Aceite DEMO", "declarations": [
                {"id": 31, "name": "Frutos secos", "state": "declared"},
            ]},
        ],
    }


class FakeSession:
    def __init__(self, foreign_package_id=41, foreign_food_id=23):
        self.calls = []
        self.foreign_package_id = foreign_package_id
        self.foreign_food_id = foreign_food_id

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return 404, "application/json", b'{"detail":"No encontrado."}'

    def json(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/api/cuaderno/packages/":
            return [{"id": 99, "food": 98, "food_name": "Aceite DEMO propio"}]
        raise AssertionError(path)


class OwnerSession:
    def __init__(self, *, logout_error=None):
        self.logout_calls = 0
        self.logout_error = logout_error

    def logout(self):
        self.logout_calls += 1
        if self.logout_error:
            raise self.logout_error


class ReleaseReadContractsUnitTests(unittest.TestCase):
    def test_role_requires_exact_responsable_admin_contract_for_active_space(self):
        self.assertEqual(
            subject._validate_operational_role(role_payload(), edition="integral", space_id=17)["code"],
            "admin",
        )
        for changed in (
            {"code": "user"}, {"label": "Cocina"}, {"space": 18},
            {"can_operate_cuaderno": False}, {"can_manage_edition": False},
            {"native_permissions_preserved": False}, {"unexpected": True},
        ):
            with self.subTest(changed=changed), self.assertRaises(subject.SmokeFailure):
                subject._validate_operational_role(role_payload(**changed), edition="integral", space_id=17)

    def test_allergen_food_contract_accepts_declared_and_unknown_without_inferred_absence(self):
        declared = allergen_payload()
        subject._validate_allergens(declared, scope_type="food", scope_id=23, scope_name="Aceite DEMO")
        unknown = allergen_payload()
        unknown.update(assessment="unknown", foods=[{"id": 23, "name": "Aceite DEMO", "declarations": []}])
        subject._validate_allergens(unknown, scope_type="food", scope_id=23, scope_name="Aceite DEMO")

    def test_allergen_contract_rejects_safe_absent_and_contradictory_assessment(self):
        mutations = []
        for key, value in (("assessment", "safe"), ("assessment", "absent"), ("undeclared_means_absent", True)):
            changed = allergen_payload()
            changed[key] = value
            mutations.append(changed)
        changed = allergen_payload()
        changed["foods"][0]["declarations"][0]["state"] = "absent"
        mutations.append(changed)
        changed = allergen_payload()
        changed["assessment"] = "unknown"
        mutations.append(changed)
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(subject.SmokeFailure):
                subject._validate_allergens(payload, scope_type="food", scope_id=23, scope_name="Aceite DEMO")

    def test_allergen_contract_rejects_malformed_ids_labels_duplicates_and_unknown_fields(self):
        mutations = []
        for value in (True, 0, 9007199254740992):
            changed = allergen_payload()
            changed["foods"][0]["id"] = value
            mutations.append(changed)
        changed = allergen_payload()
        changed["foods"][0]["name"] = "Aceite\x00oculto"
        mutations.append(changed)
        changed = allergen_payload()
        changed["foods"][0]["declarations"] *= 2
        mutations.append(changed)
        changed = allergen_payload()
        changed["unexpected"] = True
        mutations.append(changed)
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(subject.SmokeFailure):
                subject._validate_allergens(payload, scope_type="food", scope_id=23, scope_name="Aceite DEMO")

    def test_recipe_scope_allows_multiple_unique_foods_and_unknown_ingredients(self):
        payload = allergen_payload("recipe")
        payload["unknown_ingredients"] = True
        payload["foods"].append({"id": 24, "name": "Sal", "declarations": []})
        subject._validate_allergens(payload, scope_type="recipe", scope_id=23, scope_name="Salsa DEMO")

    def test_foreign_checks_are_get_only_and_cover_native_details_packages_and_history(self):
        session = FakeSession()
        subject._assert_foreign_reads_denied(
            session, food_id=23, recipe_id=24, package_id=41,
            food_name="Aceite DEMO", recipe_name="Salsa DEMO",
        )
        self.assertTrue(session.calls)
        self.assertTrue(all(call[0] == "GET" for call in session.calls))
        paths = [call[1] for call in session.calls]
        self.assertIn("/api/food/23/", paths)
        self.assertIn("/api/recipe/24/", paths)
        self.assertIn("/api/cuaderno/allergens/?food=23", paths)
        self.assertIn("/api/cuaderno/allergens/?recipe=24", paths)
        self.assertIn("/api/cuaderno/packages/41/prices/?limit=20&offset=0", paths)
        self.assertIn("/api/cuaderno/packages/", paths)

    def test_foreign_denial_rejects_name_leaks_and_package_list_id_leaks(self):
        leaking = FakeSession()
        leaking.request = lambda *args, **kwargs: (404, "application/json", b'Aceite DEMO')
        with self.assertRaises(subject.SmokeFailure):
            subject._assert_foreign_reads_denied(
                leaking, food_id=23, recipe_id=24, package_id=41,
                food_name="Aceite DEMO", recipe_name="Salsa DEMO",
            )
        package_leak = FakeSession()
        package_leak.json = lambda *args, **kwargs: [{"id": 41, "food": 23, "food_name": "secreto"}]
        with self.assertRaises(subject.SmokeFailure):
            subject._assert_foreign_reads_denied(
                package_leak, food_id=23, recipe_id=24, package_id=41,
                food_name="Aceite DEMO", recipe_name="Salsa DEMO",
            )

    def test_foreign_package_catalog_must_be_complete_bounded_and_well_typed(self):
        malformed = (
            [None],
            [{"id": 99, "food": True, "food_name": "Propio"}],
            {"count": 0, "next": "/next", "previous": None, "results": []},
            {"count": 1, "next": None, "previous": None, "results": []},
        )
        for payload in malformed:
            session = FakeSession()
            session.json = lambda *args, value=payload, **kwargs: value
            with self.subTest(payload=payload), self.assertRaises(subject.SmokeFailure):
                subject._assert_foreign_reads_denied(
                    session, food_id=23, recipe_id=24, package_id=41,
                    food_name="Aceite DEMO", recipe_name="Salsa DEMO",
                )

    def test_account_early_failure_logs_out_and_preserves_original_if_logout_also_fails(self):
        session = Mock()
        session.logout.side_effect = subject.SmokeFailure("fallo secundario de logout")
        with patch.object(subject, "HttpSession", return_value=session), \
                patch.object(subject, "_active_space", side_effect=subject.SmokeFailure("fallo primario")):
            with self.assertRaisesRegex(subject.SmokeFailure, "fallo primario"):
                subject._check_account("integral", "Integral", "synthetic-only-password")
        session.logout.assert_called_once_with()

    def test_run_cross_failure_closes_every_retained_session_and_preserves_original(self):
        owners = [OwnerSession(logout_error=subject.SmokeFailure("logout secundario")) for _ in range(3)]
        check_results = [
            ({"mode": "read_only"}, {"food_id": 10 + index, "recipe_id": 20 + index,
              "package_id": 30 + index, "food_name": "Aceite DEMO", "recipe_name": "Salsa DEMO"},
             owners[index], {"stock": {}, "services": []})
            for index in range(3)
        ]
        ready = Mock()
        ready.json.return_value = {"ready": True}
        with patch.object(subject, "_guard_base_url"), patch.object(subject, "_guard_environment", return_value="x" * 12), \
                patch.object(subject, "HttpSession", return_value=ready), \
                patch.object(subject, "_check_account", side_effect=check_results), \
                patch.object(subject, "_assert_foreign_reads_denied", side_effect=subject.SmokeFailure("aislamiento primario")):
            with self.assertRaisesRegex(subject.SmokeFailure, "aislamiento primario"):
                subject.run()
        self.assertEqual([owner.logout_calls for owner in owners], [1, 1, 1])

    def test_run_rechecks_final_snapshots_after_all_cross_space_reads_then_logs_out(self):
        owners = [OwnerSession() for _ in range(3)]
        before = [{"stock": {"owner": index}, "services": []} for index in range(3)]
        check_results = [
            ({"mode": "read_only"}, {"food_id": 10 + index, "recipe_id": 20 + index,
              "package_id": 30 + index, "food_name": "Aceite DEMO", "recipe_name": "Salsa DEMO"},
             owners[index], before[index])
            for index in range(3)
        ]
        ready = Mock()
        ready.json.return_value = {"ready": True}
        compare = Mock()
        with patch.object(subject, "_guard_base_url"), patch.object(subject, "_guard_environment", return_value="x" * 12), \
                patch.object(subject, "HttpSession", return_value=ready), \
                patch.object(subject, "_check_account", side_effect=check_results), \
                patch.object(subject, "_assert_foreign_reads_denied") as denied, \
                patch.object(subject, "_state_snapshots", side_effect=before), \
                patch.object(subject, "_assert_same_snapshots", compare):
            result = subject.run()
        self.assertEqual(result["domain_write_requests"], 0)
        self.assertEqual(denied.call_count, 6)
        self.assertEqual(compare.call_count, 3)
        self.assertEqual([owner.logout_calls for owner in owners], [1, 1, 1])
        for index, call in enumerate(compare.call_args_list):
            self.assertEqual(call.args, (before[index], before[index]))

    def test_main_frames_success_and_failure_without_password_or_traceback(self):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(subject, "run", return_value={"ready": True}), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(subject.main(), 0)
        self.assertTrue(stdout.getvalue().startswith("CUADERNO_RELEASE_READ_CONTRACTS {"))
        self.assertEqual(stderr.getvalue(), "")
        stdout, stderr = StringIO(), StringIO()
        with patch.object(subject, "run", side_effect=subject.SmokeFailure("fallo controlado")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(subject.main(), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("CUADERNO_RELEASE_READ_CONTRACTS ERROR: fallo controlado", stderr.getvalue())
        self.assertNotIn("synthetic-only-password", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
