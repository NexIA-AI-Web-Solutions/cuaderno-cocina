"""Authenticated local workers; all business actions require a saved proposal."""
from django.http import Http404
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from cookbook.helper.permission_helper import CustomTokenHasReadWriteScope, has_group_permission
from cuaderno.api.base import CuadernoAPIView, CuadernoIsOperator
from cuaderno.models import WorkerRun
from cuaderno.services import workers
from cuaderno.services.profiles import profile_for_space


class WorkerListView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def get(self, request):
        edition=profile_for_space(request.space).edition
        ranks={'esencial':0,'profesional':1,'integral':2}
        kinds=[kind for kind in workers.KINDS if ranks.get(edition,-1)>=ranks[kind['min_edition']]]
        rows=WorkerRun.objects.filter(space=request.space)
        if not has_group_permission(request,['admin']): rows=rows.filter(created_by=request.user)
        rows=rows.order_by('-pk')[:20]
        runs=[]
        for run in rows:
            try:
                workers._reauthorize(request,run)
            except (PermissionDenied,NotFound,ValidationError,Http404):
                continue
            runs.append(workers.serialize_run(run))
        return Response({'kinds':kinds,'policy':workers.POLICY,'runs':runs,
                         'can_approve':has_group_permission(request,['admin']),
                         'limit':20,'history_scope':'authorized' if has_group_permission(request,['admin']) else 'own'})


class WorkerPreviewView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def post(self,request):
        return Response(workers.serialize_run(workers.preview(request,request.data)),status=201)


class WorkerApplyView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def post(self,request,run_id):
        return Response(workers.serialize_run(workers.apply(request,run_id,request.data)))


class WorkerDismissView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def post(self,request,run_id):
        run=workers.owned_run(request,run_id)
        workers._reauthorize(request,run)
        return Response(workers.serialize_run(workers.dismiss(request,run_id)))


class WorkerScheduleView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def get(self,request):
        from cuaderno.models import WorkerSchedule
        from cuaderno.services.worker_schedules import serialize_schedule
        rows=WorkerSchedule.objects.filter(space=request.space,created_by=request.user).order_by('-pk')[:20]
        return Response({'schedules':[serialize_schedule(row) for row in rows],
            'scheduler_mode':'management_command','runner_active':False,
            'notice':'La ejecución requiere un temporizador local configurado por el administrador. Esta pantalla no instala uno.'})

    def post(self,request,schedule_id=None):
        from cuaderno.services.worker_schedules import create_schedule,change_schedule,serialize_schedule
        row=create_schedule(request,request.data) if schedule_id is None else change_schedule(request,schedule_id,request.data)
        return Response(serialize_schedule(row),status=201 if schedule_id is None else 200)
