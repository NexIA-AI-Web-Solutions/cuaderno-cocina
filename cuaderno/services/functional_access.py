"""Common bounded inputs and revision handling for native model extensions."""
import hashlib
import json

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, ValidationError

from cookbook.models import Space
from cuaderno.models import SpaceProfile
from cuaderno.services.planning_inputs import InputError


class Conflict(APIException):
    status_code = 409
    default_detail = "Los datos han cambiado o ya existen. Recarga antes de continuar."


class RevisionRequired(APIException):
    status_code = 428
    default_detail = "Envía la revisión actual antes de modificar los datos."


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except InputError as exc:
        raise ValidationError({"detail": str(exc)}) from exc


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def require_revision(data, current):
    supplied = data.get("revision")
    if supplied is None:
        raise RevisionRequired()
    if supplied != current:
        raise Conflict()


def lock_space(request):
    space = get_object_or_404(Space.objects.select_for_update(), pk=request.space.pk)
    # Serialize against concurrent edition changes as well as extension writers.
    list(SpaceProfile.objects.select_for_update().filter(space=space))
    request.space = space
    return space


def page_window(request, maximum=100):
    try:
        raw_offset, raw_limit = request.query_params.get("offset", "0"), request.query_params.get("limit", "50")
        if not raw_offset.isdecimal() or not raw_limit.isdecimal():
            raise ValueError
        offset, limit = int(raw_offset), int(raw_limit)
        if not 0 <= offset <= 100000 or not 1 <= limit <= maximum:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValidationError({"pagination": "Paginación no válida."}) from exc
    return offset, limit
