"""Preserve native conversions/properties when merging native Foods."""
from django.db import transaction
from cookbook.models import Food, FoodProperty, Space, UnitConversion
from cuaderno.domain.errors import DomainError


@transaction.atomic
def preserve_native_food_relations(source, target):
    from cuaderno.services.yield_integrity import assert_food_recipe_compatible
    Space._base_manager.select_for_update().get(pk=source.space_id)
    target_recipe = Food._base_manager.filter(pk=target.pk, space_id=source.space_id).values_list("recipe_id", flat=True).get()
    assert_food_recipe_compatible(source.pk, source.space_id, target_recipe)
    from cuaderno.models import StockMinimum
    minimums = list(StockMinimum.objects.filter(space=source.space, food=source))
    for minimum in minimums:
        others = StockMinimum.objects.filter(space=source.space, food=target, household_id=minimum.household_id)
        if others.filter(location_id=minimum.location_id).exists() or others.filter(location__isnull=minimum.location_id is not None).exists():
            raise DomainError("merge_minimum_conflict", "Los alimentos tienen mínimos incompatibles. Resuelve sus cantidades y alcance antes de fusionar.")
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
    StockMinimum.objects.filter(space=source.space, food=source).update(food=target)
