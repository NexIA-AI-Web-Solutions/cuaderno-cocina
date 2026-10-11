"""Periodic analyses execute locally, preserve ownership, and never approve."""
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from django_scopes import scopes_disabled
from cuaderno.tests.test_purchasing import PurchasingFixtureMixin
from cuaderno.models import WorkerSchedule, WorkerRun, PriceVersion, PurchaseOrder
from cuaderno.services.worker_schedules import run_due


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkerScheduleTests(PurchasingFixtureMixin,TestCase):
    def setUp(self):
        super().setUp()
        self.client=self.client_for(self.user)
        self.url='/api/cuaderno/workers/schedules/'

    def create(self, **changes):
        data={'kind':'cost_completion','params':{},'interval_hours':24};data.update(changes)
        return self.client.post(self.url,data,format='json')

    def test_due_job_creates_one_read_only_report_without_business_writes(self):
        response=self.create()
        self.assertEqual(response.status_code,201,response.content)
        row=WorkerSchedule.objects.get()
        self.assertEqual(run_due(),[])
        row.next_run=timezone.now()-timedelta(minutes=1);row.save(update_fields=['next_run'])
        with scopes_disabled():
            result=run_due()
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['status'],'generated')
            self.assertEqual(run_due(),[])
        run=WorkerRun.objects.get()
        self.assertEqual(run.status,'read_only');self.assertEqual(run.created_by,self.user)
        self.assertFalse(run.proposal)
        self.assertEqual(PriceVersion.objects.count(),0);self.assertEqual(PurchaseOrder.objects.count(),0)
        row.refresh_from_db();self.assertEqual(row.last_run,run)
        self.assertGreater(row.next_run,timezone.now())
        self.assertEqual(run.events.filter(event='scheduled').count(),1)

    def test_revoked_permission_records_failure_without_running(self):
        from cookbook.models import UserSpace
        from django.contrib.auth.models import Group
        self.assertEqual(self.create().status_code,201)
        with scopes_disabled():
            UserSpace.objects.get(user=self.user,space=self.space).groups.set([Group.objects.get_or_create(name='guest')[0]])
            WorkerSchedule.objects.update(next_run=timezone.now()-timedelta(minutes=1))
            result=run_due()
        self.assertEqual(result[0]['status'],'needs_review')
        self.assertEqual(WorkerRun.objects.count(),0)
        self.assertTrue(WorkerSchedule.objects.get().last_error)

    def test_schedules_cannot_carry_proposals_or_arbitrary_actions(self):
        self.assertEqual(self.create(proposal={'action':'reference_prices'}).status_code,400)
        self.assertEqual(self.create(interval_hours=1).status_code,400)
        self.assertEqual(self.create(params={'shell':'whoami'}).status_code,400)
        self.assertEqual(self.create(params=None).status_code,400)
        self.assertEqual(WorkerSchedule.objects.count(),0)

    def test_duplicate_schedule_pause_and_owner_boundaries(self):
        response=self.create();self.assertEqual(response.status_code,201)
        self.assertEqual(self.create().status_code,400)
        pk=response.data['id']
        other=self.client_for(self.outsider)
        self.assertEqual(other.get(self.url).data['schedules'],[])
        self.assertEqual(other.post(f'{self.url}{pk}/',{'enabled':False},format='json').status_code,404)
        self.assertEqual(self.client.post(f'{self.url}{pk}/',{'enabled':False},format='json').status_code,200)
        WorkerSchedule.objects.filter(pk=pk).update(next_run=timezone.now()-timedelta(minutes=1))
        self.assertEqual(run_due(),[])
        resumed=self.client.post(f'{self.url}{pk}/',{'enabled':True},format='json')
        self.assertEqual(resumed.status_code,200)
        self.assertGreater(WorkerSchedule.objects.get().next_run,timezone.now())
        self.assertFalse(self.client.get(self.url).data['runner_active'])

    def test_reenable_cannot_duplicate_an_active_schedule(self):
        first=self.create();self.assertEqual(first.status_code,201)
        self.client.post(f"{self.url}{first.data['id']}/",{'enabled':False},format='json')
        self.assertEqual(self.create().status_code,201)
        duplicate=self.client.post(f"{self.url}{first.data['id']}/",{'enabled':True},format='json')
        self.assertEqual(duplicate.status_code,400)
