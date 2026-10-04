from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_scopes import scopes_disabled

from cookbook.models import Food, Household, InventoryEntry, InventoryLocation, MealPlan, MealType, Recipe, Space, UserSpace
from cuaderno.models import ServicePlan, SpaceProfile, StockMovement
from cuaderno.tests.test_services import ServiceFixtureMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ListQueryEfficiencyTests(ServiceFixtureMixin, TestCase):
    """Query-shape acceptance for the two bounded operational list APIs."""

    def setUp(self):
        super().setUp()
        if connection.vendor != "postgresql":
            self.fail("La caracterización de consultas exige PostgreSQL real.")
        self.profile.edition = SpaceProfile.INTEGRAL
        self.profile.save(update_fields=["edition"])
        with scopes_disabled():
            self.meal_type = MealType.objects.create(
                space=self.space,
                name="Listado eficiente",
                created_by=self.user,
            )

    def _meal(self, recipe, title):
        now = timezone.now()
        with scopes_disabled():
            return MealPlan.objects.create(
                space=self.space,
                recipe=recipe,
                servings=10,
                title=title,
                created_by=self.user,
                meal_type=self.meal_type,
                from_date=now,
                to_date=now,
            )

    def _service(self, recipe, title, *, snapshot=None):
        meal = self._meal(recipe, title)
        with scopes_disabled():
            return ServicePlan.objects.create(
                space=self.space,
                household=self.household,
                meal_plan=meal,
                title=title,
                covers=10,
                created_by=self.user,
                service_date=date(2026, 10, 25),
                snapshot=snapshot or {},
            )

    @staticmethod
    def _model_selects(captured, table):
        marker = f'FROM "{table}"'
        return [query["sql"] for query in captured.captured_queries if marker in query["sql"]]

    def test_service_list_materializes_once_and_returns_all_100_rows(self):
        meal = self._meal(self.recipe, "Servicio común")
        with scopes_disabled():
            plans = ServicePlan.objects.bulk_create([
                ServicePlan(
                    space=self.space,
                    household=self.household,
                    meal_plan=meal,
                    title=f"Turno {index:03d}",
                    covers=10,
                    created_by=self.user,
                    service_date=None if index == 0 else date(2026, 10, 25),
                )
                for index in range(100)
            ])
        client = self.client_for(self.user)
        self.assertEqual(client.get("/api/cuaderno/services/").status_code, 200)

        with CaptureQueriesContext(connection) as captured:
            response = client.get("/api/cuaderno/services/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 100)
        ordered_plans = [*plans[1:], plans[0]]
        self.assertEqual([row["id"] for row in response.data], [plan.pk for plan in ordered_plans])
        self.assertEqual(response.data[0], {
            "id": plans[1].pk,
            "title": "Turno 001",
            "covers": "10",
            "service_date": "2026-10-25",
            "state": ServicePlan.DRAFT,
            "meal_plan": meal.pk,
            "household": self.household.pk,
            "snapshot": {},
            "confirmed_at": None,
            "produced_at": None,
            "created_by": self.user.pk,
        })
        self.assertEqual(response.data[-1]["id"], plans[0].pk)
        self.assertIsNone(response.data[-1]["service_date"])
        self.assertEqual(len(self._model_selects(captured, "cuaderno_serviceplan")), 1)
        self.assertLessEqual(len(captured), 8)

    def test_raw_service_projection_fails_closed_for_missing_role_and_duplicate_membership(self):
        from cuaderno.services.operational_reads import service_plan_rows

        plan = self._service(self.recipe, "Servicio protegido por membresía")
        with scopes_disabled():
            membership = UserSpace.objects.get(user=self.user, space=self.space, active=True)
            original_groups = list(membership.groups.all())
        request = SimpleNamespace(user=self.user, space=self.space, user_space=membership)
        self.assertEqual([row["pk"] for row in service_plan_rows(request)], [plan.pk])

        with scopes_disabled():
            membership.groups.clear()
        self.assertEqual(service_plan_rows(request), [])

        with scopes_disabled():
            membership.groups.set(original_groups)
            other_space = Space.objects.create(name="Membresía activa duplicada", created_by=self.user)
            duplicate = UserSpace.objects.create(user=self.user, space=other_space, active=True)
            duplicate.groups.add(Group.objects.get_or_create(name="user")[0])
        self.assertEqual(service_plan_rows(request), [])

    def test_service_query_reduction_keeps_private_root_and_graph_acl(self):
        visible = self._service(self.recipe, "Visible")
        with scopes_disabled():
            private_root = Recipe.objects.create(
                space=self.space,
                name="Raíz privada ajena",
                servings=1,
                created_by=self.outsider,
                private=True,
            )
            private_child = Recipe.objects.create(
                space=self.space,
                name="Hija privada ajena",
                servings=1,
                created_by=self.outsider,
                private=True,
            )
        denied_root = self._service(private_root, "Raíz denegada")
        denied_graph = self._service(
            self.recipe,
            "Grafo denegado",
            snapshot={"recipe_graph": {str(self.recipe.pk): [private_child.pk]}},
        )
        with scopes_disabled():
            malformed = ServicePlan.objects.create(
                space=self.space,
                household=self.household,
                title="Snapshot inválido",
                covers=10,
                created_by=self.user,
                service_date=date(2026, 10, 25),
                snapshot=["not-an-object"],
            )
            legacy_owned = ServicePlan.objects.create(
                space=self.space,
                household=None,
                title="Legado propio",
                covers=10,
                created_by=self.user,
                service_date=date(2026, 10, 25),
            )
            other_household = ServicePlan.objects.create(
                space=self.space,
                household=self.other_household,
                title="Otro hogar",
                covers=10,
                created_by=self.outsider,
                service_date=date(2026, 10, 25),
            )
            foreign_space = Space.objects.create(name="Otro espacio de listado", created_by=self.outsider)
            foreign_household = Household.objects.create(space=foreign_space, name="Hogar de otro espacio")
            other_space = ServicePlan.objects.create(
                space=foreign_space,
                household=foreign_household,
                title="Otro espacio",
                covers=10,
                created_by=self.outsider,
                service_date=date(2026, 10, 25),
            )
        client = self.client_for(self.user)
        self.assertEqual(client.get("/api/cuaderno/services/").status_code, 200)

        with CaptureQueriesContext(connection) as captured:
            response = client.get("/api/cuaderno/services/")

        self.assertEqual(response.status_code, 200)
        response_ids = [row["id"] for row in response.data]
        self.assertEqual(response_ids, [visible.pk, legacy_owned.pk])
        for denied in (denied_root, denied_graph, malformed, other_household, other_space):
            self.assertNotIn(denied.pk, response_ids)
        self.assertEqual(len(self._model_selects(captured, "cuaderno_serviceplan")), 1)
        self.assertLessEqual(len(captured), 8)

    def test_movement_list_keeps_100_household_rows_without_hydrating_entries(self):
        with scopes_disabled():
            own_location = InventoryLocation.objects.create(
                space=self.space,
                household=self.household,
                name="Almacén propio",
                created_by=self.user,
            )
            own_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=own_location,
                food=self.food,
                unit=self.kg,
                amount=Decimal("100"),
                created_by=self.user,
            )
            foreign_food = Food.objects.create(space=self.space, name="Alimento ajeno")
            foreign_location = InventoryLocation.objects.create(
                space=self.space,
                household=self.other_household,
                name="Almacén ajeno",
                created_by=self.outsider,
            )
            foreign_entry = InventoryEntry.objects.create(
                space=self.space,
                inventory_location=foreign_location,
                food=foreign_food,
                unit=self.kg,
                amount=Decimal("1"),
                created_by=self.outsider,
            )
            nested_metadata = {
                "sequence": 100,
                "origin": {"type": "standalone_test", "detail": {"verified": True}},
            }
            own = StockMovement.objects.bulk_create([
                StockMovement(
                    space=self.space,
                    entry=own_entry,
                    kind=StockMovement.RECEIPT,
                    quantity=Decimal("1.25") if index == 99 else Decimal("1"),
                    idempotency_key=f"query-shape-{index}",
                    fingerprint=f"{index:064x}",
                    balance_after=Decimal("100.5") if index == 99 else Decimal(index + 1),
                    metadata_snapshot=nested_metadata if index == 99 else {"sequence": index + 1},
                    created_by=self.user,
                )
                for index in range(100)
            ])
            foreign = StockMovement.objects.create(
                space=self.space,
                entry=foreign_entry,
                kind=StockMovement.RECEIPT,
                quantity=Decimal("1"),
                idempotency_key="query-shape-foreign",
                fingerprint="f" * 64,
                balance_after=Decimal("1"),
                metadata_snapshot={"foreign": True},
                created_by=self.outsider,
            )
        client = self.client_for(self.user)
        self.assertEqual(client.get("/api/cuaderno/movements/").status_code, 200)

        with CaptureQueriesContext(connection) as captured:
            response = client.get("/api/cuaderno/movements/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 100)
        self.assertEqual([row["id"] for row in response.data], [row.pk for row in reversed(own)])
        self.assertNotIn(foreign.pk, {row["id"] for row in response.data})
        representative = own[-1]
        self.assertEqual(response.data[0], {
            "id": representative.pk,
            "kind": StockMovement.RECEIPT,
            "quantity": "1.2500000000000000",
            "entry": own_entry.pk,
            "balance": "100.5000000000000000",
            "reverses": None,
            "created_at": representative.created_at.isoformat(),
            "created_by": self.user.pk,
            "metadata_snapshot": nested_metadata,
        })
        self.assertTrue(all(set(row) == {
            "id", "kind", "quantity", "entry", "balance", "reverses", "created_at", "created_by", "metadata_snapshot",
        } for row in response.data))
        entry_selects = self._model_selects(captured, "cookbook_inventoryentry")
        self.assertEqual(len(entry_selects), 1)
        self.assertIn("ARRAY_AGG", entry_selects[0])
        self.assertNotIn('"cuaderno_stockmovement"', entry_selects[0])
        movement_selects = self._model_selects(captured, "cuaderno_stockmovement")
        self.assertEqual(len(movement_selects), 1)
        self.assertRegex(movement_selects[0], r'movement\.entry_id\s*=\s*ANY')
        projection = movement_selects[0].split(" FROM ", 1)[0]
        self.assertNotIn('"cookbook_inventoryentry".', projection)
        self.assertLessEqual(len(captured), 7)

    def test_service_list_rejects_float_snapshot_ids_instead_of_rounding_them(self):
        visible = self._service(self.recipe, "Visible integer identifiers")
        fractional = float(self.recipe.pk) + 0.5
        float_root = self._service(
            self.recipe,
            "Fractional snapshot root",
            snapshot={"recipe_id": fractional},
        )
        float_child = self._service(
            self.recipe,
            "Fractional snapshot child",
            snapshot={"recipe_graph": {str(self.recipe.pk): [fractional]}},
        )
        integral_float = self._service(
            self.recipe,
            "Integral float is still a non-JSON-integer",
            snapshot={"recipe_graph": {str(self.recipe.pk): [float(self.recipe.pk)]}},
        )

        response = self.client_for(self.user).get("/api/cuaderno/services/")

        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.data}
        self.assertIn(visible.pk, ids)
        for malformed in (float_root, float_child, integral_float):
            self.assertNotIn(malformed.pk, ids)
            self.assertNotIn(malformed.title, str(response.data))
