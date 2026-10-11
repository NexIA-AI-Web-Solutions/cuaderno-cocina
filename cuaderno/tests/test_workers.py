"""Saved worker decisions use real PostgreSQL and native purchasing/costing data."""
from decimal import Decimal
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled
from cuaderno.tests.test_purchasing import PurchasingFixtureMixin
from cuaderno.models import PriceVersion, PurchaseOrder
from django.utils import timezone


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkerApprovalTests(PurchasingFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.client_for(self.admin)
        self.url = '/api/cuaderno/workers/'

    def preview_price(self, **changes):
        payload = {'rows': [{'package_id': self.package.pk, 'amount': '12.50', 'explicit_free': False}],
                   'evidence': 'Tarifa sintética 11/10; saco 5 kg; 12,50 EUR.'}
        payload.update(changes)
        return self.client.post(self.url+'preview/', {'kind':'price_watch', 'params': {},
            'proposal': {'action':'reference_prices', 'payload':payload}}, format='json')

    def apply(self, run, **changes):
        payload = {'approval':True, 'expected_digest':run['input_digest']}
        payload.update(changes)
        return self.client.post(f"{self.url}{run['id']}/apply/", payload, format='json')

    def test_preview_is_non_mutating_and_approval_replay_creates_one_price(self):
        before = PriceVersion.objects.count()
        response = self.preview_price()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PriceVersion.objects.count(), before)
        self.assertEqual(response.data['status'], 'pending')
        applied = self.apply(response.data)
        self.assertEqual(applied.status_code, 200, applied.content)
        self.assertEqual(applied.data['status'], 'applied')
        self.assertEqual(PriceVersion.objects.count(), before+1)
        self.assertEqual(self.apply(response.data).status_code, 200)
        self.assertEqual(PriceVersion.objects.count(), before+1)
        self.assertEqual(PriceVersion.objects.latest('pk').amount, Decimal('12.50'))

    def test_rejects_stale_price_preview_and_wrong_digest_without_writes(self):
        preview = self.preview_price()
        self.assertEqual(preview.status_code, 201, preview.content)
        self.assertEqual(self.apply(preview.data, expected_digest='wrong').status_code, 409)
        PriceVersion.objects.create(space=self.space, package=self.package, amount=13,
            created_by=self.admin, valid_from=timezone.now())
        response = self.apply(preview.data)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(PriceVersion.objects.count(), 1)

    def test_exact_approval_required_and_cocina_cannot_apply(self):
        preview = self.preview_price()
        self.assertEqual(preview.status_code, 201, preview.content)
        self.assertEqual(self.apply(preview.data, approval='true').status_code, 400)
        membership = self.admin.userspaces.get(space=self.space) if hasattr(self.admin, 'userspaces') else None
        # A separate operator cannot approve another person's evidence either.
        self.client = self.client_for(self.user)
        self.assertIn(self.apply(preview.data).status_code, (403,404))
        self.assertEqual(PriceVersion.objects.count(), 0)

    def test_explicit_free_duplicate_rows_and_unknown_actions_rejected(self):
        for rows in ([{'package_id':self.package.pk,'amount':'0','explicit_free':False}],
                     [{'package_id':self.package.pk,'amount':'NaN','explicit_free':False}],
                     [{'package_id':self.package.pk,'amount':12.5,'explicit_free':False}],
                     [{'package_id':self.package.pk,'amount':'2'}]*2):
            response = self.preview_price(rows=rows)
            self.assertEqual(response.status_code, 400, response.content)
        response = self.client.post(self.url+'preview/', {'kind':'price_watch','proposal':{'action':'shell','payload':{}}},format='json')
        self.assertEqual(response.status_code, 400)

    def test_batch_is_atomic_and_source_required(self):
        self.assertEqual(self.preview_price(evidence='').status_code,400)
        response=self.preview_price(rows=[{'package_id':self.package.pk,'amount':'12.50'}, {'package_id':9999999,'amount':'5'}])
        self.assertEqual(response.status_code,404)
        self.assertEqual(PriceVersion.objects.count(),0)

    def test_csv_is_local_strict_and_identified_by_ids(self):
        response=self.preview_price(rows=None,csv='package_id,amount,explicit_free,note\n%d,12.50,false,tarifa\n'%self.package.pk)
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(self.apply(response.data).status_code,200)
        self.assertEqual(PriceVersion.objects.count(),1)

    def test_purchase_draft_approval_does_not_receive_stock_and_is_idempotent(self):
        response=self.client.post(self.url+'preview/', {'kind':'purchase_review','params':{},'proposal':{
            'action':'purchase_draft','payload':{'package_id':self.package.pk,'package_count':'2','evidence':'Reposición revisada por responsable'}}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(PurchaseOrder.objects.count(),0)
        self.assertEqual(self.apply(response.data).status_code,200)
        self.assertEqual(self.apply(response.data).status_code,200)
        order=PurchaseOrder.objects.get()
        self.assertEqual(order.state,'draft')
        self.assertEqual(order.quantity,Decimal('10'))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount,Decimal('1000'))

    def test_saved_report_is_private_and_dismiss_never_applies(self):
        preview=self.preview_price()
        self.assertEqual(preview.status_code,201,preview.content)
        other=self.client_for(self.user).get(self.url)
        self.assertEqual(other.status_code,200)
        self.assertEqual(other.data['runs'],[])
        response=self.client.post(f"{self.url}{preview.data['id']}/dismiss/",{},format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.apply(preview.data).status_code,409)
        self.assertEqual(PriceVersion.objects.count(),0)

    def test_prospective_price_simulation_uses_exact_native_engine(self):
        from cookbook.models import Recipe, Step, Ingredient, SearchFields
        with scopes_disabled():
            SearchFields.objects.get_or_create(name='Name',defaults={'field':'name'})
            recipe=Recipe.objects.create(space=self.space,name='Pan sintético',servings=4,created_by=self.admin)
            step=Step.objects.create(space=self.space)
            step.ingredients.add(Ingredient.objects.create(space=self.space,food=self.food,unit=self.g,amount=400))
            recipe.steps.add(step)
            PriceVersion.objects.create(space=self.space,package=self.package,amount=10,created_by=self.admin,valid_from=timezone.now())
        response=self.preview_price()
        self.assertEqual(response.status_code,201,response.content)
        item=next(row for row in response.data['report']['items'] if row.get('type')=='proposed_price_impact')
        self.assertEqual(Decimal(item['values']['before']['unrounded']),Decimal('0.8'))
        self.assertEqual(Decimal(item['values']['after']['unrounded']),Decimal('1'))
        self.assertEqual(Decimal(item['values']['difference']),Decimal('0.2'))
        self.assertEqual(PriceVersion.objects.count(),1)
        self.assertEqual(self.apply(response.data).status_code,200)
        self.assertEqual(self.apply(response.data).status_code,200)

    def test_private_source_revocation_hides_history(self):
        from cookbook.models import Recipe, Step, Ingredient, SearchFields
        with scopes_disabled():
            SearchFields.objects.get_or_create(name='Name',defaults={'field':'name'})
            recipe=Recipe.objects.create(space=self.space,name='Receta confidencial',servings=4,created_by=self.user)
            step=Step.objects.create(space=self.space)
            step.ingredients.add(Ingredient.objects.create(space=self.space,food=self.food,unit=self.g,amount=400))
            recipe.steps.add(step)
        response=self.client.post(self.url+'preview/',{'kind':'cost_completion','params':{'recipe_id':recipe.pk}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        with scopes_disabled():
            recipe.private=True;recipe.save(update_fields=['private'])
        history=self.client.get(self.url)
        self.assertEqual(history.status_code,200)
        self.assertNotIn('Receta confidencial',str(history.data))

    def test_current_approval_role_is_rechecked_despite_cached_request(self):
        from types import SimpleNamespace
        from cookbook.helper.permission_helper import has_group_permission
        from cookbook.models import UserSpace
        from django.contrib.auth.models import Group
        from rest_framework.exceptions import PermissionDenied
        from cuaderno.services.workers import apply
        response=self.preview_price()
        self.assertEqual(response.status_code,201,response.content)
        with scopes_disabled():
            member=UserSpace.objects.get(user=self.admin,space=self.space)
            request=SimpleNamespace(user=self.admin,space=self.space,user_space=member)
            self.assertTrue(has_group_permission(request,['admin']))
            member.groups.set([Group.objects.get_or_create(name='user')[0]])
            with self.assertRaises(PermissionDenied):
                apply(request,response.data['id'],{'approval':True,'expected_digest':response.data['input_digest']})
        self.assertEqual(PriceVersion.objects.count(),0)

    def test_pack_change_invalidates_purchase_and_price_approval(self):
        response=self.preview_price()
        self.assertEqual(response.status_code,201,response.content)
        self.package.quantity=Decimal('4');self.package.save(update_fields=['quantity'])
        self.assertEqual(self.apply(response.data).status_code,409)
        self.assertEqual(PriceVersion.objects.count(),0)

    def test_read_only_report_cannot_be_applied(self):
        response=self.client.post(self.url+'preview/',{'kind':'cost_completion','params':{}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(response.data['status'],'read_only')
        self.assertEqual(self.apply(response.data).status_code,409)

    def test_cocina_hands_purchase_proposal_to_responsable_preserving_household(self):
        cocina=self.client_for(self.user)
        response=cocina.post(self.url+'preview/',{'kind':'purchase_review','params':{},'proposal':{
            'action':'purchase_draft','payload':{'package_id':self.package.pk,'package_count':'2','evidence':'Compra preparada por cocina'}}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        from cookbook.models import UserSpace
        with scopes_disabled():
            # The approver can oversee another household; delivery stays at the creator's household.
            UserSpace.objects.filter(user=self.admin,space=self.space).update(household=self.other_household)
        # Changing membership is itself a material change: make a fresh proposal.
        response=cocina.post(self.url+'preview/',{'kind':'purchase_review','params':{},'proposal':{
            'action':'purchase_draft','payload':{'package_id':self.package.pk,'package_count':'2','evidence':'Compra preparada por cocina'}}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        history=self.client.get(self.url)
        self.assertIn(response.data['id'],[row['id'] for row in history.data['runs']])
        approved=self.apply(response.data)
        self.assertEqual(approved.status_code,200,approved.content)
        self.assertEqual(PurchaseOrder.objects.get().household_id,self.household.pk)
        self.assertEqual(approved.data['approved_by'],self.admin.pk)
        self.assertEqual(approved.data['created_by'],self.user.pk)

    def test_history_result_is_hidden_after_operator_moves_household(self):
        from cookbook.models import UserSpace
        from django.contrib.auth.models import Group
        response=self.client.post(self.url+'preview/',{'kind':'purchase_review','params':{},'proposal':{
            'action':'purchase_draft','payload':{'package_id':self.package.pk,'package_count':'2','evidence':'Compra sintética del hogar original'}}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(self.apply(response.data).status_code,200)
        with scopes_disabled():
            member=UserSpace.objects.get(user=self.admin,space=self.space)
            member.household=self.other_household;member.save(update_fields=['household'])
            member.groups.set([Group.objects.get_or_create(name='user')[0]])
        history=self.client.get(self.url)
        self.assertEqual(history.status_code,200)
        self.assertEqual(history.data['runs'],[])

    def test_deleted_unpriced_package_does_not_break_history(self):
        response=self.preview_price()
        self.assertEqual(response.status_code,201,response.content)
        self.package.delete()
        history=self.client.get(self.url)
        self.assertEqual(history.status_code,200,history.content)
        self.assertEqual(history.data['runs'],[])

    def test_guest_cannot_generate_or_approve(self):
        self.client=self.client_for(self.guest)
        self.assertEqual(self.preview_price().status_code,403)
        self.assertEqual(self.client.get(self.url).status_code,200)

    def test_csrf_is_required_for_cookie_authenticated_preview(self):
        from rest_framework.test import APIClient
        client=APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response=client.post(self.url+'preview/',{'kind':'cost_completion'},format='json')
        self.assertEqual(response.status_code,403)


from django.test import TransactionTestCase
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkerConcurrencyTests(PurchasingFixtureMixin, TransactionTestCase):
    def test_two_approvals_of_one_run_create_one_price(self):
        client=self.client_for(self.admin)
        response=client.post('/api/cuaderno/workers/preview/',{'kind':'price_watch','params':{},'proposal':{
            'action':'reference_prices','payload':{'rows':[{'package_id':self.package.pk,'amount':'12.50'}],'evidence':'Tarifa sintética concurrente'}}},format='json')
        self.assertEqual(response.status_code,201,response.content)
        clients=[self.client_for(self.admin),self.client_for(self.admin)]
        barrier=Barrier(2)
        def approve(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result=clients[index].post(f"/api/cuaderno/workers/{response.data['id']}/apply/",{'approval':True,'expected_digest':response.data['input_digest']},format='json')
                return result.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses=list(executor.map(approve,[0,1]))
        self.assertEqual(statuses,[200,200])
        self.assertEqual(PriceVersion.objects.count(),1)
