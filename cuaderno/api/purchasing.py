"""Strict API contracts for Integral purchasing.

The views live here as well once the RED purchasing contract is implemented.  Keeping
the input contract separate from the native serializers prevents JSON numbers from
silently becoming binary-float-derived money or quantities.
"""

from __future__ import annotations

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from cookbook.helper.permission_helper import CustomIsUser, CustomTokenHasReadWriteScope
from cookbook.models import InventoryEntry
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal, parse_decimal
from cuaderno.models import PurchaseOffer, PurchaseReceipt, SpaceProfile
from cuaderno.services.inventory_access import household_inventory
from cuaderno.services.purchasing import (
    accessible_orders,
    create_offer,
    create_order,
    receive_order,
    replenishment,
    reverse_receipt,
    serialize_offer,
    serialize_order,
    serialize_receipt,
    transition_order,
)


class StrictIdentifierField(serializers.IntegerField):
    default_error_messages = {"invalid": "Debe ser un identificador entero positivo."}

    def to_internal_value(self, data):
        if isinstance(data, bool) or isinstance(data, (list, dict)):
            self.fail("invalid")
        value = super().to_internal_value(data)
        if value <= 0:
            self.fail("invalid")
        return value


class DecimalStringField(serializers.Field):
    default_error_messages = {
        "invalid": "Debe ser un decimal enviado como texto.",
        "precision": "Admite como máximo 16 enteros y 16 decimales.",
    }

    def __init__(self, *, allow_zero=False, **kwargs):
        self.allow_zero = allow_zero
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        try:
            value = parse_decimal(data, allow_zero=self.allow_zero)
        except DomainError as exc:
            raise serializers.ValidationError(exc.message, code=exc.code) from exc
        _, raw_digits, exponent = value.as_tuple()
        digits = list(raw_digits)
        while digits and digits[-1] == 0:
            digits.pop()
            exponent += 1
        if value.adjusted() >= 16 or (digits and exponent < -16):
            self.fail("precision")
        return value

    def to_representation(self, value):
        return canonical_decimal(Decimal(value))


class OfferWriteSerializer(serializers.Serializer):
    package = StrictIdentifierField()
    supplier = StrictIdentifierField()
    amount = DecimalStringField(allow_zero=True)
    explicit_free = serializers.BooleanField(default=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", default="EUR")
    valid_from = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if (attrs["amount"] == 0) != attrs["explicit_free"]:
            raise serializers.ValidationError(
                {"explicit_free": "El precio cero debe declararse gratuito, y solo el cero puede ser gratuito."}
            )
        return attrs


class OrderWriteSerializer(serializers.Serializer):
    food = StrictIdentifierField(required=False)
    unit = StrictIdentifierField(required=False)
    quantity = DecimalStringField()
    supplier = StrictIdentifierField(required=False, allow_null=True)
    package = StrictIdentifierField(required=False, allow_null=True)
    offer = StrictIdentifierField(required=False, allow_null=True)
    package_count = DecimalStringField(required=False, allow_null=True)


class OrderActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("order", "cancel"))


class ReceiptWriteSerializer(serializers.Serializer):
    entry = StrictIdentifierField()
    quantity = DecimalStringField()
    idempotency_key = serializers.CharField(min_length=1, max_length=96, trim_whitespace=True)


class ReceiptReverseSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(min_length=1, max_length=96, trim_whitespace=True)


class ReplenishmentQuerySerializer(serializers.Serializer):
    service_plans = serializers.ListField(
        child=StrictIdentifierField(), allow_empty=False, max_length=100, required=False
    )
    household = StrictIdentifierField(required=False)


def _integral(space):
    profile, _ = SpaceProfile.objects.get_or_create(space=space)
    if profile.edition != SpaceProfile.INTEGRAL:
        raise PermissionDenied("Esta operación pertenece a la edición integral.")


class PurchaseOfferView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request):
        _integral(request.space)
        rows = PurchaseOffer.objects.filter(space=request.space).select_related("package", "supplier").order_by(
            "-valid_from", "-pk"
        )[:100]
        return Response([serialize_offer(row) for row in rows])

    def post(self, request):
        _integral(request.space)
        serializer = OfferWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = create_offer(space=request.space, user=request.user, data=serializer.validated_data)
        return Response(serialize_offer(offer), status=201)


class PurchaseOrderView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request, order_id=None):
        _integral(request.space)
        rows = accessible_orders(request).select_related("food", "unit", "supplier", "package")
        if order_id is not None:
            return Response(serialize_order(get_object_or_404(rows, pk=order_id)))
        return Response([serialize_order(row) for row in rows.order_by("-pk")[:100]])

    def post(self, request, order_id=None):
        _integral(request.space)
        if order_id is None:
            serializer = OrderWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = create_order(request=request, data=serializer.validated_data)
            return Response(serialize_order(order), status=201)
        order = get_object_or_404(accessible_orders(request), pk=order_id)
        serializer = OrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = transition_order(order=order, action=serializer.validated_data["action"])
        return Response(serialize_order(order))


class PurchaseReceiptView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request, order_id):
        _integral(request.space)
        order = get_object_or_404(accessible_orders(request), pk=order_id)
        rows = PurchaseReceipt.objects.filter(space=request.space, order=order).order_by("-pk")[:100]
        return Response([serialize_receipt(row) for row in rows])

    def post(self, request, order_id):
        _integral(request.space)
        order = get_object_or_404(accessible_orders(request), pk=order_id)
        serializer = ReceiptWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = get_object_or_404(
            household_inventory(request, InventoryEntry.objects.all()),
            pk=serializer.validated_data["entry"],
        )
        receipt, replayed = receive_order(
            request=request,
            order=order,
            entry=entry,
            quantity=serializer.validated_data["quantity"],
            raw_key=serializer.validated_data["idempotency_key"],
        )
        return Response(serialize_receipt(receipt), status=200 if replayed else 201)


class PurchaseReceiptReverseView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def post(self, request, receipt_id):
        _integral(request.space)
        receipt = get_object_or_404(
            PurchaseReceipt.objects.filter(
                space=request.space,
                order_id__in=accessible_orders(request).values("pk"),
            ),
            pk=receipt_id,
        )
        serializer = ReceiptReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt, replayed = reverse_receipt(
            request=request,
            receipt=receipt,
            raw_key=serializer.validated_data["idempotency_key"],
        )
        return Response(serialize_receipt(receipt), status=200 if replayed else 201)


class ReplenishmentView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def post(self, request):
        _integral(request.space)
        serializer = ReplenishmentQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"items": replenishment(request=request, data=serializer.validated_data)})
