"""Household/location minimums over native inventory, without a stock counter."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.response import Response
from cuaderno.api.base import CuadernoAPIView as APIView, CuadernoIsOperator

from cookbook.helper.permission_helper import CustomIsUser, CustomTokenHasReadWriteScope, has_group_permission
from cookbook.models import InventoryLocation, Unit
from cuaderno.api.prices import JsonIdentifierField
from cuaderno.api.purchasing import DecimalStringField, _integral
from cuaderno.domain.money import canonical_decimal
from cuaderno.models import StockMinimum
from cuaderno.services.purchasing import _membership_household
from cuaderno.services.visibility import visible_foods, visible_minimums


class MinimumScopeConflict(APIException):
    status_code = 409
    default_detail = "Elige un mínimo global o mínimos por ubicación; elimina el anterior antes de cambiar el alcance."


class MinimumWriteSerializer(serializers.Serializer):
    food = JsonIdentifierField()
    unit = JsonIdentifierField()
    quantity = DecimalStringField(allow_null=True)
    location = JsonIdentifierField(allow_null=True, default=None)


class StockMinimumView(APIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    @staticmethod
    def payload(request, household):
        rows = visible_minimums(request.user, request.space).filter(household=household).select_related("food", "unit", "location").order_by("food_id", "location_id", "pk")
        return Response({
            "edition": "integral", "household": {"id": household.pk, "name": household.name},
            "locations": list(InventoryLocation.objects.filter(space=request.space, household=household).order_by("name", "pk").values("id", "name")),
            "items": [{
                "id": row.pk, "household": row.household_id,
                "food": row.food_id, "food_name": row.food.name,
                "unit": row.unit_id, "unit_name": row.unit.name,
                "quantity": canonical_decimal(row.quantity),
                "location": row.location_id, "location_name": row.location.name if row.location_id else None,
                "updated_by": row.updated_by_id, "updated_at": row.updated_at.isoformat(),
            } for row in rows],
        })

    def get(self, request):
        _integral(request.space)
        identifier = request.query_params.get("household")
        if identifier is not None:
            if not identifier.isascii() or not identifier.isdecimal() or len(identifier) > 19 or not 0 < int(identifier) <= 9223372036854775807:
                raise ValidationError({"household": "El hogar debe ser un identificador entero positivo."})
            identifier = int(identifier)
        if identifier is not None and identifier != getattr(getattr(request, "user_space", None), "household_id", None) and not has_group_permission(request, ["admin"]):
            raise NotFound("El hogar no está disponible.")
        return self.payload(request, _membership_household(request, identifier))

    @transaction.atomic
    def put(self, request):
        _integral(request.space)
        serializer = MinimumWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        household = _membership_household(request)
        food = get_object_or_404(visible_foods(request.user, request.space), pk=data["food"])
        unit = get_object_or_404(Unit.objects.filter(space=request.space), pk=data["unit"])
        location = None
        if data["location"] is not None:
            location = get_object_or_404(InventoryLocation.objects.filter(space=request.space, household=household), pk=data["location"])
        rows = StockMinimum.objects.filter(space=request.space, household=household, food=food)
        row = rows.filter(location=location).first()
        if data["quantity"] is None:
            if row is not None:
                row.delete()
        else:
            if rows.filter(location__isnull=location is not None).exists():
                raise MinimumScopeConflict()
            if row is None:
                StockMinimum.objects.create(space=request.space, household=household, food=food, unit=unit, location=location, quantity=data["quantity"], updated_by=request.user)
            elif row.quantity != data["quantity"] or row.unit_id != unit.pk:
                row.unit = unit
                row.quantity = data["quantity"]
                row.updated_by = request.user
                row.save(update_fields=["unit", "quantity", "updated_by", "updated_at"])
        return self.payload(request, household)
