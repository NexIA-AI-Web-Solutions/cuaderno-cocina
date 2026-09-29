"""Preserve native conversions/properties when merging native Foods."""
from cookbook.models import FoodProperty, UnitConversion
from cuaderno.domain.errors import DomainError


def preserve_native_food_relations(source, target):
    pairs = []
    for conversion in UnitConversion.objects.filter(space=source.space, food=source):
        existing = UnitConversion.objects.filter(
            space=source.space, food=target, base_unit=conversion.base_unit, converted_unit=conversion.converted_unit,
        ).first()
        if existing and existing.base_amount * conversion.converted_amount != conversion.base_amount * existing.converted_amount:
            raise DomainError("merge_conversion_conflict", "Las conversiones de los alimentos difieren. Resuelve el conflicto antes de fusionar.")
        pairs.append((conversion, existing))
    for conversion, existing in pairs:
        if existing:
            conversion.delete()
        else:
            conversion.food = target
            conversion.save(update_fields=["food"])
    existing_properties = target.properties.values_list("pk", flat=True)
    duplicates = FoodProperty.objects.filter(food=source, property_id__in=existing_properties)
    duplicates.delete()
    FoodProperty.objects.filter(food=source).update(food=target)
