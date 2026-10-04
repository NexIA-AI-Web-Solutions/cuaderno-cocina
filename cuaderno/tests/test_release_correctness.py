"""Release regressions against real ORM/API boundaries, on isolated PostgreSQL."""
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled

from cookbook.models import Household, ShoppingList, ShoppingListEntry, Space, UserSpace
from cuaderno.models import AllergenDeclaration
from cuaderno.tests import test_integration as fixtures


class ReadinessTests(TestCase):
    def test_pending_required_migration_is_not_ready(self):
        self.assertEqual(self.client.get("/health/ready/").status_code, 200)
        MigrationRecorder.Migration.objects.filter(app="cuaderno", name="0016_servicepreparationitem").delete()
        response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"ready": False})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProductionInputTests(TestCase):
    setUp = fixtures.CuadernoIntegrationTests.setUp
    _user = fixtures.CuadernoIntegrationTests._user
    _client = fixtures.CuadernoIntegrationTests._client
    def test_invalid_manual_production_returns_400_without_writes(self):
        client = self._client(self.user)
        before = self.entry.amount
        payloads = [[], {"usages": [{}]}, {"usages": [{"component": "oil", "quantity": "invalid"}]},
                    {"edges": []}, {"edges": {"A": "B"}, "start": "A"}, {"recipe_ids": [True]},
                    {"usages": [{"component": "oil", "quantity": 1.5}]}, {"service_plan": True}]
        for payload in payloads:
            with self.subTest(payload=payload):
                response = client.post("/api/cuaderno/production/", payload, format="json")
                self.assertEqual(response.status_code, 400)
        with scopes_disabled():
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.amount, before)

    def test_manual_production_preserves_exact_quantity(self):
        response = self._client(self.user).post("/api/cuaderno/production/", {
            "usages": [{"component": "oil", "quantity": "1234567890123456.1234567890123456"}],
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["needs"]["oil"], "1234567890123456.1234567890123456")

    def test_operational_endpoints_reject_non_object_envelopes(self):
        client = self._client(self.admin)
        for path in ('edition', 'movements', 'orders', 'services', 'allergens', 'exchange', 'packages',
                     'purchase-offers', 'purchase-orders', 'replenishment', 'stock-minimums'):
            with self.subTest(path=path):
                method = client.put if path in ('edition', 'stock-minimums') else client.post
                self.assertEqual(method(f'/api/cuaderno/{path}/', [], format='json').status_code, 400)

    def test_allergen_history_records_actor_time_and_case_insensitive_latest(self):
        client = self._client(self.user)
        declared = client.post("/api/cuaderno/allergens/", {
            "food": self.food.pk, "name": "Gluten", "state": "declared",
        }, format="json")
        unknown = client.post("/api/cuaderno/allergens/", {
            "food": self.food.pk, "name": " gluten ", "state": "unknown",
        }, format="json")
        self.assertEqual(declared.status_code, 201)
        self.assertEqual(unknown.status_code, 201)
        with scopes_disabled():
            history = list(AllergenDeclaration.objects.filter(food=self.food).order_by("pk"))
            self.assertEqual(len(history), 2)
            self.assertEqual(history[-1].created_by_id, self.user.pk)
            self.assertIsNotNone(history[-1].created_at)
        assessment = client.get(f"/api/cuaderno/allergens/?food={self.food.pk}").json()
        self.assertEqual(assessment["assessment"], "unknown")
        self.assertEqual(len(assessment["foods"][0]["declarations"]), 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ShoppingRevisionTests(TestCase):
    setUp = fixtures.CuadernoIntegrationTests.setUp
    _user = fixtures.CuadernoIntegrationTests._user
    _client = fixtures.CuadernoIntegrationTests._client

    def test_checked_requires_revision_and_preserves_guest_household_and_owner_rights(self):
        with scopes_disabled():
            entry = ShoppingListEntry.objects.create(space=self.space, food=self.food, unit=self.unit,
                                                     amount=1, created_by=self.user)
        url = f'/api/shopping-list-entry/{entry.pk}/'
        client = self._client(self.user)
        data = client.get(url).json()
        self.assertEqual(client.patch(url, {'checked': True}, format='json').status_code, 428)
        self.assertEqual(client.patch(url, {'checked': True}, format='json', HTTP_IF_MATCH='*').status_code, 400)
        self.assertEqual(self._client(self.guest).patch(url, {'checked': True}, format='json',
            HTTP_IF_MATCH=f'"{data["revision"]}"').status_code, 200)
        with scopes_disabled():
            separate = Household.objects.create(space=self.space, name='Otro equipo')
            UserSpace.objects.filter(user=self.guest, space=self.space).update(household=separate)
        revision = client.get(url).json()['revision']
        self.assertEqual(self._client(self.guest).patch(url, {'checked': False}, format='json',
            HTTP_IF_MATCH=f'"{revision}"').status_code, 404)
        with scopes_disabled():
            owned = ShoppingListEntry.objects.create(space=self.space, food=self.food, unit=self.unit,
                amount=1, created_by=self.guest)
        guest_client = self._client(self.guest)
        owned_url = f'/api/shopping-list-entry/{owned.pk}/'
        owned_data = guest_client.get(owned_url).json()
        self.assertEqual(guest_client.patch(owned_url, {'checked': True}, format='json',
            HTTP_IF_MATCH=f'"{owned_data["revision"]}"').status_code, 200)

    def test_bulk_conflict_is_atomic_and_opaque_revisions_roundtrip(self):
        with scopes_disabled():
            rows = [ShoppingListEntry.objects.create(space=self.space, food=self.food, unit=self.unit,
                amount=1, created_by=self.user) for _ in range(2)]
        client = self._client(self.user)
        revisions = {str(row.pk): client.get(f'/api/shopping-list-entry/{row.pk}/').json()['revision'] for row in rows}
        ids = [row.pk for row in rows]
        bulk = '/api/shopping-list-entry/bulk/'
        self.assertEqual(client.post(bulk, {'ids': ids, 'checked': True}, format='json').status_code, 428)
        changed = client.patch(f'/api/shopping-list-entry/{ids[0]}/', {'checked': True}, format='json',
            HTTP_IF_MATCH=f'"{revisions[str(ids[0])]}"')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(len(changed.json()['revision']), 64)
        stale = client.post(bulk, {'ids': ids, 'checked': False, 'revisions': revisions}, format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertTrue(client.get(f'/api/shopping-list-entry/{ids[0]}/').json()['checked'])
        self.assertFalse(client.get(f'/api/shopping-list-entry/{ids[1]}/').json()['checked'])
        revisions[str(ids[0])] = changed.json()['revision']
        result = client.post(bulk, {'ids': ids, 'checked': True, 'revisions': revisions}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.json()['revisions']), set(revisions))
        self.assertEqual(client.post(bulk, {'ids': [ids[0], ids[0]], 'checked': False,
            'revisions': {str(ids[0]): result.json()['revisions'][str(ids[0])]}}, format='json').status_code, 400)

    def test_bulk_relation_targets_cannot_cross_space_or_partially_write(self):
        with scopes_disabled():
            entry = ShoppingListEntry.objects.create(space=self.space, food=self.food, unit=self.unit,
                amount=1, created_by=self.user)
            local = ShoppingList.objects.create(space=self.space, name='Local')
            foreign = ShoppingList.objects.create(space=Space.objects.create(name='Otro'), name='Lista privada ajena')
        client = self._client(self.user)
        before = client.get(f'/api/shopping-list-entry/{entry.pk}/').json()['revision']
        for field in ('shopping_lists_add', 'shopping_lists_set', 'shopping_lists_remove'):
            with self.subTest(field=field):
                response = client.post('/api/shopping-list-entry/bulk/', {
                    'ids': [entry.pk], field: [local.pk, foreign.pk],
                }, format='json')
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(foreign.name, str(response.json()))
                self.assertEqual(client.get(f'/api/shopping-list-entry/{entry.pk}/').json()['revision'], before)
                with scopes_disabled():
                    self.assertFalse(entry.shopping_lists.exists())
    def test_stale_toggle_and_undo_cannot_overwrite_later_change(self):
        with scopes_disabled():
            entry = ShoppingListEntry.objects.create(space=self.space, food=self.food, unit=self.unit,
                                                     amount=1, created_by=self.user)
        client = self._client(self.user)
        url = f"/api/shopping-list-entry/{entry.pk}/?autosync=1"
        initial = client.get(url).json()
        first = client.patch(url, {"checked": True}, format="json", HTTP_IF_MATCH=f'"{initial["updated_at"]}"')
        self.assertEqual(first.status_code, 200)
        stale = client.patch(url, {"checked": False}, format="json", HTTP_IF_MATCH=f'"{initial["updated_at"]}"')
        self.assertEqual(stale.status_code, 409)
        self.assertTrue(client.get(url).json()["checked"])
        next_revision = first.json()["updated_at"]
        changed = client.patch(url, {"checked": False}, format="json", HTTP_IF_MATCH=f'"{next_revision}"')
        self.assertEqual(changed.status_code, 200)
        undo = client.patch(url, {"checked": True}, format="json", HTTP_IF_MATCH=f'"{next_revision}"')
        self.assertEqual(undo.status_code, 409)
        self.assertFalse(client.get(url).json()["checked"])
