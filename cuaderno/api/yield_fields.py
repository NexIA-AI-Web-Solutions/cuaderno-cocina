"""Shared validation for native serializers and the Cuaderno yield editor."""
from decimal import Decimal

from rest_framework import serializers
from django_scopes import scope
from django.db import transaction

from cuaderno.domain.errors import DomainError
from cuaderno.domain.ingredient_yields import parse_yield_ratio, validate_yield_policy


class YieldRatioField(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=17, decimal_places=16, min_value=Decimal("0.0000000000000001"), max_value=Decimal("1"), **kwargs)

    def to_internal_value(self, data):
        try:
            parsed = parse_yield_ratio(data)
        except DomainError as exc:
            raise serializers.ValidationError(exc.message) from exc
        return super().to_internal_value(format(parsed, "f"))


class IngredientYieldValidationMixin:
    @transaction.atomic
    def create(self, attrs):
        try:
            return super().create(attrs)
        except DomainError as exc:
            raise serializers.ValidationError({"yield_ratio": exc.message}) from exc

    @transaction.atomic
    def update(self, instance, attrs):
        try:
            return super().update(instance, attrs)
        except DomainError as exc:
            raise serializers.ValidationError({"yield_ratio": exc.message}) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        basis = attrs.get("quantity_basis", getattr(self.instance, "quantity_basis", "gross"))
        ratio = attrs.get("yield_ratio", getattr(self.instance, "yield_ratio", None))
        try:
            active = basis != "gross" or ratio is not None
            validate_yield_policy(basis, ratio, is_subrecipe=active and self._is_subrecipe(attrs))
        except DomainError as exc:
            raise serializers.ValidationError({"yield_ratio": exc.message}) from exc
        return attrs

    def _is_subrecipe(self, attrs):
        from cookbook.models import Food
        if "food" not in attrs:
            return bool(self.instance and self.instance.food_id and self.instance.food.recipe_id)
        data = attrs["food"]
        if data is None:
            return False
        if isinstance(data, Food):
            return bool(data.recipe_id)
        if not isinstance(data, dict):
            return False
        if data.get("recipe"):
            return True
        request = self.context.get("request")
        space = getattr(request, "space", None) or getattr(self.instance, "space", None)
        if space is None:
            raise serializers.ValidationError({"yield_ratio": "No se puede validar el alimento sin su espacio."})
        raw = getattr(self, "initial_data", {})
        raw_food = raw.get("food", {}) if isinstance(raw, dict) else {}
        identifier = data.get("id") or (raw_food.get("id") if isinstance(raw_food, dict) else None)
        if isinstance(identifier, str) and identifier.isdecimal() and len(identifier) <= 19:
            identifier = int(identifier)
        if identifier is not None and (type(identifier) is not int or not 0 < identifier <= 9223372036854775807):
            raise serializers.ValidationError({"yield_ratio": "El identificador del alimento no es válido."})
        if type(identifier) is int and 0 < identifier <= 9223372036854775807:
            with scope(space=space):
                row = Food.objects.filter(space=space, pk=identifier).values("recipe_id").first()
            if row is not None:
                return bool(row["recipe_id"])
        name = data.get("name")
        if isinstance(name, str):
            with scope(space=space):
                return Food.objects.filter(space=space, name__iexact=name.strip(), recipe__isnull=False).exists()
        return bool(self.instance and self.instance.food_id and self.instance.food.recipe_id)
