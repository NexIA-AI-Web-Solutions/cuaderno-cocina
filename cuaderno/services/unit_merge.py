"""Preserve exact professional quantities when native unit aliases merge."""
from django.db import transaction
from django.db.models import Q
from decimal import localcontext

from cookbook.models import InventoryEntry, Space, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.domain.units import to_base
from cuaderno.models import PackageFormat, PurchaseOrder, RecipeYield, ServicePlan, StockMinimum


@transaction.atomic
def preserve_native_unit_relations(source, target):
    Space._base_manager.select_for_update().get(pk=source.space_id)
    if source.space_id != target.space_id:
        raise DomainError("unit_merge_space", "Las unidades deben pertenecer al mismo espacio.")
    packages = PackageFormat.objects.filter(space=source.space, unit=source)
    minimums = StockMinimum.objects.filter(space=source.space, unit=source)
    yields = RecipeYield.objects.filter(space=source.space, unit=source)
    orders = PurchaseOrder.objects.filter(space=source.space).filter(Q(unit=source) | Q(package_unit_snapshot=source))
    # JSON snapshots have no FK: protect them before considering any early return.
    if orders.exists() or ServicePlan.objects.filter(space=source.space, snapshot__needs__contains=[{"unit_id": source.pk}]).exists():
        raise DomainError("unit_merge_snapshot", "La unidad está referenciada en un documento congelado; conserva su identidad e historial.")
    entries = InventoryEntry.objects.filter(space=source.space, unit=source)
    conversions = UnitConversion.objects.filter(space=source.space).filter(Q(base_unit=source) | Q(converted_unit=source))
    try:
        equivalent = to_base(1, source.base_unit or source.name) == to_base(1, target.base_unit or target.name)
    except DomainError:
        equivalent = False
    if not equivalent:
        raise DomainError("unit_merge_scale", "Solo se fusionan alias de igual dimensión y escala; no se cambiarán cantidades.")
    if not (packages.exists() or minimums.exists() or yields.exists() or entries.exists() or conversions.exists()):
        return
    # Validate all rewritten edges before touching quantities, units or relations.
    edges = list(UnitConversion.objects.filter(space=source.space).filter(
        Q(base_unit__in=[source, target]) | Q(converted_unit__in=[source, target])
    ).order_by("pk"))
    edges.sort(key=lambda row: (source.pk in {row.base_unit_id, row.converted_unit_id}, row.pk))
    kept, duplicates, rewritten = {}, [], []
    for row in edges:
        base = target.pk if row.base_unit_id == source.pk else row.base_unit_id
        converted = target.pk if row.converted_unit_id == source.pk else row.converted_unit_id
        key = (row.food_id, min(base, converted), max(base, converted))
        amounts = (row.base_amount, row.converted_amount) if base < converted else (row.converted_amount, row.base_amount)
        if row.base_amount <= 0 or row.converted_amount <= 0:
            raise DomainError("unit_merge_conversion", "Una conversión no tiene cantidades positivas. Corrígela antes de fusionar.")
        if base == converted:
            if row.base_amount != row.converted_amount:
                raise DomainError("unit_merge_conversion", "La conversión entre estos alias contradice su escala.")
            duplicates.append(row.pk)
            continue
        prior = kept.get(key)
        if prior is not None:
            with localcontext() as context:
                context.prec = 64
                equivalent = prior[0] * amounts[1] == amounts[0] * prior[1]
            if not equivalent:
                raise DomainError("unit_merge_conversion", "Las conversiones de las unidades difieren. Resuelve el conflicto antes de fusionar.")
            duplicates.append(row.pk)
        else:
            kept[key] = amounts
            rewritten.append((row, base, converted))
    UnitConversion.objects.filter(space=source.space, pk__in=duplicates).delete()
    for row, base, converted in rewritten:
        if row.base_unit_id != base or row.converted_unit_id != converted:
            row.base_unit_id, row.converted_unit_id = base, converted
            row.save(update_fields=["base_unit", "converted_unit"])
    packages.update(unit=target)
    minimums.update(unit=target)
    yields.update(unit=target)
    entries.update(unit=target)
