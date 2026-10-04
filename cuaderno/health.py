from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from cuaderno.api.schema import ReadySerializer


@extend_schema(operation_id="cuaderno_readiness", request=None, responses={200: ReadySerializer, 503: ReadySerializer})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def readiness(request):
    try:
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        ready = not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception:
        ready = False
    return JsonResponse({"ready": ready}, status=200 if ready else 503)
