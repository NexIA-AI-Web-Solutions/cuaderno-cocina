"""Reservation persistence, permission, aggregation and native-stock regression tests."""
from decimal import Decimal
from django.test import TestCase
from django_scopes import scopes_disabled
from cookbook.models import InventoryEntry, InventoryLocation, MealType, Recipe, Step, Ingredient
from cuaderno.models import CustomerReservation, MenuTemplate, MenuTemplateEntry, MealCourse, ReservationService, ReservationRevision, ServicePlan, SpaceProfile, StockMovement
from cuaderno.tests.test_services import ServiceFixtureMixin

BASE = '/api/cuaderno/reservations/'


class ReservationTests(ServiceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        with scopes_disabled():
            self.guest = self.make_user('reservation-guest', 'guest', self.other_household)
            self.meal = MealType.objects.create(space=self.space, name='Comida', created_by=self.admin)
            self.template = MenuTemplate.objects.create(space=self.space, name='Menú local', created_by=self.admin)
            MenuTemplateEntry.objects.create(space=self.space, template=self.template, day_index=0, meal_type=self.meal, recipe=self.recipe)
            self.location = InventoryLocation.objects.create(space=self.space, household=self.household, name='Local', created_by=self.admin)
            self.stock = InventoryEntry.objects.create(space=self.space, inventory_location=self.location, food=self.food, unit=self.kg, amount=Decimal('100'), created_by=self.admin)

    def create(self, covers=20, user=None, **overrides):
        data = dict(customer_name='Grupo local', phone='600000000', service_date='2026-10-25', service_time='13:30',
                    template=self.template.pk, template_day=0, meal_type=self.meal.pk, covers=covers, reason='Reserva telefónica')
        data.update(overrides)
        response = self.client_for(user or self.user).post(BASE, data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def action(self, row, action, user=None, reason='Cambio autorizado', expected=200):
        response = self.client_for(user or self.user).post(BASE + str(row['id']) + '/transition/',
            {'action': action, 'revision': row['revision'], 'reason': reason}, format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def read(self, row, user=None):
        response = self.client_for(user or self.user).get(BASE + str(row['id']) + '/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_requested_confirmed_edit_and_history_never_touch_stock(self):
        row = self.create()
        self.assertEqual(row['state'], 'requested')
        self.assertEqual(row['history'][0]['action'], 'create')
        row = self.action(row, 'confirm')
        self.assertEqual(row['services'][0]['snapshot']['needs'][0]['quantity'], '4')
        response = self.client_for(self.user).patch(BASE + str(row['id']) + '/',
            {'covers': 15, 'revision': row['revision'], 'reason': 'Cinco cancelaciones'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data
        self.assertEqual(row['services'][0]['snapshot']['needs'][0]['quantity'], '3')
        with scopes_disabled():
            self.assertEqual(ReservationService.objects.filter(reservation_id=row['id'], active=True).count(), 1)
            self.assertEqual(ReservationService.objects.filter(reservation_id=row['id'], active=False).count(), 1)
            self.stock.refresh_from_db()
            self.assertEqual(self.stock.amount, 100)
            self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual([r['action'] for r in row['history']], ['create', 'confirm', 'edit'])

    def test_professional_kitchen_served_no_stock_and_pending_excludes_served(self):
        row = self.action(self.create(), 'confirm')
        row = self.action(row, 'start_kitchen')
        self.assertEqual(row['state'], 'in_kitchen')
        row = self.action(row, 'serve')
        self.assertEqual(row['state'], 'served')
        with scopes_disabled():
            self.stock.refresh_from_db(); self.assertEqual(self.stock.amount, 100)
            self.assertEqual(StockMovement.objects.count(), 0)
        summary = self.client_for(self.guest).get(BASE + 'summary/?date=2026-10-25')
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['pending_covers'], 0)

    def test_integral_consumption_cancel_compensation_and_replay(self):
        self.profile.edition = SpaceProfile.INTEGRAL; self.profile.save()
        row = self.action(self.create(), 'confirm')
        confirmed = row
        row = self.action(row, 'start_kitchen')
        replay = self.action(confirmed, 'start_kitchen')
        self.assertEqual(replay['revision'], row['revision'])
        with scopes_disabled():
            self.stock.refresh_from_db(); self.assertEqual(self.stock.amount, 96)
            self.assertEqual(StockMovement.objects.count(), 1)
        row = self.action(row, 'cancel', user=self.admin)
        with scopes_disabled():
            self.stock.refresh_from_db(); self.assertEqual(self.stock.amount, 100)
            self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(row['state'], 'cancelled')

    def test_summary_20_15_30_10_is_75_without_requested(self):
        rows = [self.action(self.create(covers=count), 'confirm') for count in (20, 15, 30, 10)]
        self.create(covers=90)
        self.action(rows[0], 'start_kitchen')
        result = self.client_for(self.guest).get(BASE + 'summary/?date=2026-10-25')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['total_active_covers'], 75)
        self.assertEqual(result.data['pending_covers'], 55)
        self.assertEqual(result.data['groups'][0]['dishes'][0]['pending_servings'], 55)
        self.assertEqual(Decimal(result.data['groups'][0]['needs'][0]['quantity']), Decimal('11'))
        self.assertEqual(result.data['groups'][0]['confirmed_covers'], 55)
        self.assertEqual(result.data['groups'][0]['in_kitchen_covers'], 20)

    def test_consulta_space_reads_and_no_writes(self):
        row = self.create()
        self.read(row, self.guest)
        result = self.client_for(self.guest).get(BASE)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data['can_operate'])
        self.assertEqual(self.client_for(self.guest).post(BASE, {}, format='json').status_code, 403)
        self.action(row, 'confirm', user=self.guest, expected=403)

    def test_cocina_menu_change_and_cancel_denied_admin_allowed(self):
        row = self.create()
        result = self.client_for(self.user).patch(BASE + str(row['id']) + '/',
            {'template_day': 0, 'revision': row['revision'], 'reason': 'Menú'}, format='json')
        self.assertEqual(result.status_code, 403)
        self.action(row, 'cancel', expected=403)
        self.action(row, 'confirm')
        row = self.read(row)
        result = self.client_for(self.admin).patch(BASE + str(row['id']) + '/',
            {'template_day': 0, 'revision': row['revision'], 'reason': 'Menú'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.action(result.data, 'cancel', user=self.admin)

    def test_stale_revision_conflicts_and_reason_required(self):
        row = self.create()
        self.action(row, 'confirm')
        self.action(row, 'cancel', user=self.admin, expected=409)
        result = self.client_for(self.user).patch(BASE + str(row['id']) + '/', {'covers': 10, 'revision': 2}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertEqual(len(self.read(row)['history']), 2)

    def test_contact_covers_and_unknown_inputs_rejected(self):
        for patch in ({'phone': '', 'email': ''}, {'covers': True}, {'covers': 1.5}, {'covers': 10000}, {'unknown': 1}):
            data = dict(customer_name='Grupo', phone='1', service_date='2026-10-25', service_time='13:30',
                template=self.template.pk, template_day=0, meal_type=self.meal.pk, covers=20, reason='Alta')
            data.update(patch)
            result = self.client_for(self.user).post(BASE, data, format='json')
            self.assertEqual(result.status_code, 400, result.data)

    def test_esencial_denies_read_and_creation(self):
        self.profile.edition = SpaceProfile.ESENCIAL; self.profile.save()
        self.assertEqual(self.client_for(self.user).get(BASE).status_code, 403)
        self.assertEqual(self.client_for(self.user).get(BASE + 'menus/').status_code, 403)

    def test_multidish_integral_failure_rolls_back_all_consumption(self):
        self.profile.edition = SpaceProfile.INTEGRAL; self.profile.save()
        with scopes_disabled():
            food = type(self.food).objects.create(space=self.space, name='Sin stock')
            recipe = Recipe.objects.create(space=self.space, name='Segundo', servings=10, created_by=self.user)
            step = Step.objects.create(space=self.space, name='Preparar segundo')
            step.ingredients.add(Ingredient.objects.create(space=self.space, food=food, unit=self.kg, amount=Decimal('1')))
            recipe.steps.add(step)
            course = MealCourse.objects.create(space=self.space, meal_type=self.meal, name='Segundo')
            MenuTemplateEntry.objects.create(space=self.space, template=self.template, day_index=0, meal_type=self.meal, recipe=recipe, course=course)
        row = self.action(self.create(), 'confirm')
        self.action(row, 'start_kitchen', expected=400)
        with scopes_disabled():
            self.stock.refresh_from_db(); self.assertEqual(self.stock.amount, 100)
            self.assertEqual(StockMovement.objects.count(), 0)
            self.assertEqual(set(ReservationService.objects.filter(reservation_id=row['id']).values_list('service__state', flat=True)), {'confirmed'})
        self.assertEqual(self.read(row)['state'], 'confirmed')

    def test_cross_space_or_wrong_template_day_hidden(self):
        row = self.create()
        with scopes_disabled():
            from cookbook.models import Space, Household
            foreign = Space.objects.create(name='Ajeno')
            home = Household.objects.create(space=foreign, name='Ajeno')
            original = self.space; self.space = foreign
            foreign_user = self.make_user('reservation-foreign', 'admin', home)
            self.space = original
            SpaceProfile.objects.create(space=foreign, edition=SpaceProfile.PROFESIONAL)
        self.assertEqual(self.client_for(foreign_user).get(BASE + str(row['id']) + '/').status_code, 404)
        result = self.client_for(self.admin).patch(BASE + str(row['id']) + '/',
            {'template_day': 3, 'revision': row['revision'], 'reason': 'Día inválido'}, format='json')
        self.assertEqual(result.status_code, 400)

    def test_contact_edit_preserves_confirmed_price_snapshot(self):
        row = self.action(self.create(), 'confirm')
        service_id = row['services'][0]['id']
        response = self.client_for(self.user).patch(BASE + str(row['id']) + '/',
            {'phone': '611111111', 'revision': row['revision'], 'reason': 'Corregir contacto'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['services'][0]['id'], service_id)
        self.assertEqual(response.data['services'][0]['snapshot'], row['services'][0]['snapshot'])

    def test_recipe_visibility_is_rechecked_for_frozen_reservation(self):
        row = self.action(self.create(), 'confirm')
        with scopes_disabled():
            self.recipe.private = True
            self.recipe.created_by = self.admin
            self.recipe.save(update_fields=['private', 'created_by'])
        response = self.client_for(self.user).get(BASE + str(row['id']) + '/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client_for(self.user).get(BASE).data['count'], 0)

    def test_cocina_other_household_cannot_operate_space_read_reservation(self):
        row = self.create()
        readonly = self.read(row, self.outsider)
        self.assertFalse(readonly['can_operate'])
        self.assertFalse(readonly['can_edit'])
        self.assertTrue(self.read(row, self.admin)['can_operate'])
        self.action(row, 'confirm', user=self.outsider, expected=403)

    def test_time_input_rejects_seconds_precision(self):
        row = self.create()
        response = self.client_for(self.user).patch(BASE + str(row['id']) + '/',
            {'service_time': '13:30:45', 'revision': row['revision'], 'reason': 'Hora'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.read(row)['service_time'], '13:30')

    def test_operator_without_household_sees_no_operational_capabilities(self):
        row = self.create()
        with scopes_disabled():
            from cookbook.models import UserSpace
            for user in (self.admin, self.user):
                UserSpace.objects.filter(user=user, space=self.space).update(household=None)
        for user in (self.admin, self.user):
            detail = self.read(row, user)
            self.assertFalse(detail['can_operate'])
            self.assertFalse(detail['can_edit'])
            self.assertFalse(detail['can_change_menu'])
            self.assertFalse(detail['can_cancel'])
            listing = self.client_for(user).get(BASE)
            self.assertEqual(listing.status_code, 200)
            self.assertFalse(listing.data['can_operate'])
            self.action(row, 'confirm', user=user, expected=400)
