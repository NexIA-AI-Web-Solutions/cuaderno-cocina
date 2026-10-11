"""Opt-in scheduled evidence capture. Run by an operator-owned local timer."""
from datetime import timedelta
from types import SimpleNamespace
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework.exceptions import APIException, ValidationError
from cookbook.models import Space, UserSpace
from cuaderno.models import WorkerSchedule, WorkerEvent
from cuaderno.services.workers import _check_kind, _refresh_actor, preview
from cuaderno.services.worker_analysis import _parameters


def serialize_schedule(row):
    return {'id':row.pk,'kind':row.kind,'params':row.params,'interval_hours':row.interval_hours,
            'enabled':row.enabled,'next_run':row.next_run.isoformat(),'last_run_id':row.last_run_id,
            'last_error':row.last_error,'created_at':row.created_at.isoformat()}


@transaction.atomic
def create_schedule(request, data):
    Space.objects.select_for_update().get(pk=request.space.pk)
    _refresh_actor(request,'user')
    if set(data)-{'kind','params','interval_hours'}:
        raise ValidationError({'schedule':'Solo se programan informes de lectura, sin propuestas ni acciones.'})
    kind=data.get('kind'); _check_kind(request,kind)
    params=data.get('params',{})
    if not isinstance(params,dict): raise ValidationError({'params':'Envía un objeto de parámetros.'})
    if len(str(params))>8000: raise ValidationError({'params':'Demasiados parámetros.'})
    _parameters(params)
    hours=data.get('interval_hours',24)
    if type(hours) is not int or hours not in (24,168):
        raise ValidationError({'interval_hours':'Elige 24 o 168 horas.'})
    rows=WorkerSchedule.objects.filter(space=request.space,created_by=request.user)
    if rows.count()>=20 or rows.filter(enabled=True).count()>=10:
        raise ValidationError({'schedule':'Máximo 10 programaciones activas y 20 guardadas por persona.'})
    if rows.filter(kind=kind,params=params,interval_hours=hours,enabled=True).exists():
        raise ValidationError({'schedule':'Este informe ya tiene esa programación activa.'})
    return WorkerSchedule.objects.create(space=request.space,created_by=request.user,kind=kind,params=params,
        interval_hours=hours,next_run=timezone.now()+timedelta(hours=hours))


@transaction.atomic
def change_schedule(request, pk, data):
    Space.objects.select_for_update().get(pk=request.space.pk)
    _refresh_actor(request,'user')
    if set(data)!={'enabled'} or type(data.get('enabled')) is not bool:
        raise ValidationError({'enabled':'Indica true para activar o false para pausar.'})
    row=get_object_or_404(WorkerSchedule.objects.select_for_update(),pk=pk,space=request.space,created_by=request.user)
    if data['enabled'] and not row.enabled:
        _check_kind(request,row.kind)
        if WorkerSchedule.objects.filter(space=request.space,created_by=request.user,enabled=True).count()>=10:
            raise ValidationError({'schedule':'Máximo 10 programaciones activas.'})
        if WorkerSchedule.objects.filter(space=request.space,created_by=request.user,kind=row.kind,params=row.params,interval_hours=row.interval_hours,enabled=True).exclude(pk=row.pk).exists():
            raise ValidationError({'schedule':'Ya existe otra programación equivalente activa.'})
        row.next_run=timezone.now()+timedelta(hours=row.interval_hours)
    row.enabled=data['enabled'];row.save(update_fields=['enabled','next_run'])
    return row


def run_due(*,limit=20):
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('limit must be between 1 and 100')
    due=list(WorkerSchedule.objects.filter(enabled=True,next_run__lte=timezone.now()).order_by('next_run','pk').values_list('pk','space_id')[:limit])
    outcomes=[]
    for pk,space_id in due:
        with transaction.atomic():
            space=Space.objects.select_for_update().get(pk=space_id)
            row=WorkerSchedule.objects.select_for_update().select_related('created_by').filter(pk=pk,enabled=True,next_run__lte=timezone.now()).first()
            if row is None: continue
            membership=UserSpace.objects.filter(user=row.created_by,space=space,active=True).first()
            request=SimpleNamespace(user=row.created_by,space=space,user_space=membership)
            try:
                if not row.created_by.is_active:
                    raise ValidationError('La cuenta no está activa.')
                # Nested transaction rolls back a failed report without losing
                # the scheduler's failure record and next-check timestamp.
                with transaction.atomic():
                    _refresh_actor(request,'user')
                    run=preview(request,{'kind':row.kind,'params':row.params})
                    WorkerEvent.objects.create(run=run,actor=row.created_by,event='scheduled',data={'schedule_id':row.pk})
                row.last_run=run;row.last_error=''
                outcomes.append({'id':pk,'status':'generated','run_id':run.pk})
            except (APIException,Http404):
                row.last_error='No se pudo generar el informe. Revisa permisos, edición y datos de la programación.'
                outcomes.append({'id':pk,'status':'needs_review'})
            row.next_run=timezone.now()+timedelta(hours=row.interval_hours)
            row.save(update_fields=['last_run','last_error','next_run'])
    return outcomes
