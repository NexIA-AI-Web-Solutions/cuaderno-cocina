"""Typed input for native Food/Unit purchase formats; never coerce truthy JSON."""
from rest_framework import serializers

from cuaderno.api.purchasing import DecimalStringField
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import validate_explicit_price


class ExactDecimalField(DecimalStringField):
    def to_internal_value(self, data):
        # Preserve the existing exact integer contract, but never accept floats/bools.
        if type(data) is int:
            data = str(data)
        return super().to_internal_value(data)


class JsonBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if type(data) is not bool:
            self.fail("invalid")
        return data


class JsonIdentifierField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int or data <= 0 or data > 9223372036854775807:
            self.fail("invalid")
        return data


class TextLabelField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


def validate_free_flag(amount, explicit_free):
    try:
        validate_explicit_price(amount, explicit_free)
    except DomainError as exc:
        raise serializers.ValidationError({"explicit_free": exc.message}) from exc


class PackageWriteSerializer(serializers.Serializer):
    food = JsonIdentifierField()
    unit = JsonIdentifierField()
    label = TextLabelField(max_length=128, trim_whitespace=True)
    quantity = ExactDecimalField()
    price = ExactDecimalField(allow_zero=True, required=False, allow_null=True)
    explicit_free = JsonBooleanField(default=False)

    def validate(self, attrs):
        validate_free_flag(attrs.get("price"), attrs["explicit_free"])
        return attrs


class PriceWriteSerializer(serializers.Serializer):
    amount = ExactDecimalField(allow_zero=True)
    explicit_free = JsonBooleanField(default=False)

    def validate(self, attrs):
        validate_free_flag(attrs["amount"], attrs["explicit_free"])
        return attrs
