"""Bounded contracts for manual and persisted production sheets."""
from rest_framework import serializers

from cuaderno.api.prices import JsonIdentifierField
from cuaderno.api.purchasing import DecimalStringField
from cuaderno.domain.errors import DomainError
from cuaderno.domain.production import assert_no_cycle


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "Campo desconocido." for key in sorted(unknown)})
        return super().to_internal_value(data)


class ProductionUsageSerializer(StrictSerializer):
    component = serializers.CharField(max_length=256, allow_blank=False)
    quantity = DecimalStringField(allow_zero=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "component" in data and not isinstance(data["component"], str):
            raise serializers.ValidationError({"component": "El componente debe ser texto."})
        return super().to_internal_value(data)


class ProductionWriteSerializer(StrictSerializer):
    service_plan = JsonIdentifierField(required=False)
    action = serializers.ChoiceField(choices=("produce",), required=False)
    idempotency_key = serializers.CharField(max_length=128, allow_blank=False, required=False)
    usages = ProductionUsageSerializer(many=True, max_length=1000, required=False)
    recipe_ids = serializers.ListField(child=JsonIdentifierField(), max_length=100, required=False)
    edges = serializers.JSONField(required=False)
    start = serializers.CharField(max_length=256, allow_blank=False, required=False)

    def validate(self, attrs):
        recipe_ids = attrs.get("recipe_ids", [])
        if len(recipe_ids) != len(set(recipe_ids)):
            raise serializers.ValidationError({"recipe_ids": "Cada receta debe aparecer una sola vez."})
        if "service_plan" in attrs:
            if any(key in attrs for key in ("usages", "recipe_ids", "edges", "start")):
                raise serializers.ValidationError("No mezcles un servicio confirmado con una ficha manual.")
            if attrs.get("action") == "produce" and not attrs.get("idempotency_key"):
                raise serializers.ValidationError({"idempotency_key": "Indica una clave para producir sin duplicar consumos."})
        elif "action" in attrs or "idempotency_key" in attrs:
            raise serializers.ValidationError({"service_plan": "Selecciona un servicio para producir."})
        if "edges" in attrs or "start" in attrs:
            try:
                assert_no_cycle(attrs.get("start", "__root__"), attrs.get("edges", {}))
            except DomainError as exc:
                raise serializers.ValidationError({exc.code: exc.message}) from exc
        return attrs


class ProductionResponseSerializer(serializers.Serializer):
    needs = serializers.JSONField(required=False)
    edges = serializers.DictField(child=serializers.ListField(child=serializers.CharField()), required=False)
    units = serializers.DictField(child=serializers.CharField(allow_null=True), required=False)
    warnings = serializers.ListField(child=serializers.JSONField(), required=False)
    stock_changed = serializers.BooleanField()
    service_plan = serializers.IntegerField(required=False)
    state = serializers.CharField(required=False)
    movement_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    snapshot = serializers.JSONField(required=False)
    cost = serializers.JSONField(required=False, allow_null=True)
