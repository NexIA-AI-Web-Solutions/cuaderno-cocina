"""Read and update one persistent service preparation checklist."""

from collections.abc import Mapping
import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from cuaderno.api.base import CuadernoAPIView as APIView, CuadernoIsOperator

from cookbook.helper.permission_helper import CustomTokenHasReadWriteScope, has_group_permission
from cookbook.models import Space
from cuaderno.api.ingredient_yields import RevisionField
from cuaderno.api.prices import JsonBooleanField, JsonIdentifierField
from cuaderno.models import ServicePlan, ServicePreparationItem, SpaceProfile
from cuaderno.services.preparation import preparation_payload, preparation_revision
from cuaderno.services.service_plans import accessible_service_plans


class PreparationWriteSerializer(serializers.Serializer):
    item = JsonIdentifierField()
    checked = JsonBooleanField()
    revision = RevisionField()


class PreparationRevisionRequired(APIException):
    status_code = 428
    default_detail = "Incluye la revisión obtenida al leer la preparación."
    default_code = "preparation_revision_required"


class PreparationRevisionConflict(APIException):
    status_code = 409
    default_detail = "La preparación ha cambiado; vuelve a cargarla antes de guardar."
    default_code = "preparation_revision_conflict"


def _require_professional(space):
    try:
        edition = space.cuaderno_profile.edition
    except SpaceProfile.DoesNotExist:
        edition = SpaceProfile.ESENCIAL
    if edition not in {SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL}:
        raise PermissionDenied("Esta operación pertenece a la edición profesional.")


def _locked_plan(request, plan_id: int) -> ServicePlan:
    locked_space = (
        Space._base_manager.select_for_update(of=("self",))
        .select_related("cuaderno_profile").get(pk=request.space.pk)
    )
    try:
        plan = ServicePlan._base_manager.select_for_update().get(pk=plan_id, space_id=request.space.pk)
    except ServicePlan.DoesNotExist as exc:
        raise Http404 from exc
    if not accessible_service_plans(request, plan_id).filter(pk=plan.pk).exists():
        raise Http404
    plan.space = locked_space
    return plan


def _locked_items(plan: ServicePlan) -> list[ServicePreparationItem]:
    return list(
        ServicePreparationItem._base_manager.select_for_update()
        .filter(service_id=plan.pk, space_id=plan.space_id)
        .order_by("position", "pk")
    )


class ServicePreparationView(APIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def get(self, request, plan_id):
        # A deliberate coherent-read tradeoff: this short, explicit/lazy GET
        # uses the same Space lock as PUT. No GET writes or claimed scalable
        # snapshot isolation for unrelated native writers.
        plan = _locked_plan(request, plan_id)
        _require_professional(plan.space)
        payload = preparation_payload(plan, _locked_items(plan))
        payload["can_edit"] = payload["can_edit"] and has_group_permission(request, ["user"])
        return Response(payload)

    @transaction.atomic
    def put(self, request, plan_id):
        plan = _locked_plan(request, plan_id)
        _require_professional(plan.space)
        if not isinstance(request.data, Mapping):
            raise ValidationError({"preparation": "El cuerpo debe ser un objeto JSON."})
        if "revision" not in request.data:
            raise PreparationRevisionRequired({"revision": PreparationRevisionRequired.default_detail})
        serializer = PreparationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        items = _locked_items(plan)
        current_revision = preparation_revision(plan, items)
        if data["revision"] != current_revision:
            raise PreparationRevisionConflict({"revision": PreparationRevisionConflict.default_detail})
        if plan.state != ServicePlan.CONFIRMED:
            raise ValidationError({"state": "Solo se puede editar la preparación de un servicio confirmado."})
        item = next((row for row in items if row.pk == data["item"]), None)
        if item is None:
            raise Http404
        if item.checked is data["checked"]:
            return Response(preparation_payload(plan, items))

        before = item.checked
        item.checked = data["checked"]
        item.checked_at = timezone.now() if item.checked else None
        item.updated_by = request.user
        item.save(update_fields=["checked", "checked_at", "updated_by", "updated_at"])
        LogEntry.objects.create(
            user_id=request.user.pk,
            content_type=ContentType.objects.get_for_model(ServicePlan),
            object_id=str(plan.pk),
            object_repr=str(plan.title)[:200],
            action_flag=CHANGE,
            change_message=json.dumps([{"changed": {
                "fields": ["checked"],
                "preparation_item_id": item.pk,
                "before": before,
                "after": item.checked,
            }}], ensure_ascii=False, separators=(",", ":")),
        )
        return Response(preparation_payload(plan, _locked_items(plan)))
