"""Named schemas for computed native recipe properties."""
from rest_framework import serializers


class PropertyNamedObjectSchema(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PropertyConversionSchema(serializers.Serializer):
    base_unit = PropertyNamedObjectSchema()
    converted_unit = PropertyNamedObjectSchema()


class PropertyFoodValueSchema(serializers.Serializer):
    id = serializers.IntegerField()
    food = PropertyNamedObjectSchema()
    value = serializers.FloatField(allow_null=True)
    missing_unit = serializers.BooleanField(required=False)
    missing_conversion = PropertyConversionSchema(required=False)


class ComputedPropertySchema(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    unit = serializers.CharField(allow_null=True)
    order = serializers.IntegerField()
    food_values = serializers.DictField(child=PropertyFoodValueSchema())
    total_value = serializers.FloatField()
    missing_value = serializers.BooleanField()
