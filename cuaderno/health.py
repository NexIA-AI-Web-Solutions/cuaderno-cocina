from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM django_migrations WHERE app = %s AND name = %s", ["cuaderno", "0013_offer_free_equivalence"])
            ready = cursor.fetchone() is not None
    except Exception:
        ready = False
    return JsonResponse({"ready": ready}, status=200 if ready else 503)
