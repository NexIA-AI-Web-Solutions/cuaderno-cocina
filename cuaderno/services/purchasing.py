"""Integral purchasing over native Food, Supermarket and InventoryEntry rows."""

from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_CEILING, localcontext

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import Household, InventoryEntry, Supermarket, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal
from cuaderno.models import (
    InventoryWriteRequest,
    PurchaseOffer,
    PurchaseOrder,
    PurchaseReceipt,
    ServicePlan,
    StockMovement,
)
from cuaderno.services.costing import current_price
from cuaderno.services.ledger import IdempotencyConflict, apply_movement, reverse_movement
from cuaderno.services.service_plans import accessible_service_plans
from cuaderno.services.subrecipes import convert_native_quantity
from cuaderno.services.visibility import visible_foods, visible_minimums, visible_packages


def _decimal(value) -> str:
    return canonical_decimal(Decimal(value))


def _membership_household(request, requested_id=None) -> Household:
    membership = getattr(request, "user_space", None)
    own_id = membership.household_id if membership else None
    if requested_id is None:
        requested_id = own_id
    if requested_id is None:
        raise ValidationError({"household": "Asigna un hogar operativo."})
    if requested_id != own_id and not has_group_permission(request, ["admin"]):
        raise PermissionDenied("No puedes operar para otro hogar.")
    household = Household.objects.filter(pk=requested_id, space=request.space).first()
    if household is None:
        raise NotFound("El hogar no está disponible en este espacio.")
    return household


def accessible_orders(request):
    rows = PurchaseOrder.objects.filter(
        space=request.space, food_id__in=visible_foods(request.user, request.space).values("pk"),
        unit__space=request.space, household__space=request.space,
    ).filter(
        Q(package_id__isnull=True)
        | Q(package_id__in=visible_packages(request.user, request.space).values("pk"),
            package__food_id=F("food_id"), package__unit_id=F("unit_id")),
    ).filter(Q(supplier_id__isnull=True) | Q(supplier__space=request.space)).filter(
        Q(package_unit_snapshot_id__isnull=True) | Q(package_unit_snapshot__space=request.space),
    )
    if has_group_permission(request, ["admin"]):
        return rows
    membership = getattr(request, "user_space", None)
    if membership is None or membership.household_id is None:
        return rows.none()
    return rows.filter(household_id=membership.household_id)


def serialize_offer(offer: PurchaseOffer) -> dict:
    return {
        "id": offer.pk,
        "package": offer.package_id,
        "supplier": offer.supplier_id,
        "amount": _decimal(offer.amount),
        "explicit_free": offer.explicit_free,
        "currency": offer.currency,
        "valid_from": offer.valid_from.isoformat(),
        "created_by": offer.created_by_id,
        "created_at": offer.created_at.isoformat(),
    }


def accessible_offers(user, space):
    return PurchaseOffer.objects.filter(
        space=space, package_id__in=visible_packages(user, space).values("pk"), supplier__space=space,
    )


@transaction.atomic
def create_offer(*, space, user, data) -> PurchaseOffer:
    type(space).objects.select_for_update().get(pk=space.pk)
    package = visible_packages(user, space).filter(pk=data["package"]).first()
    supplier = Supermarket.objects.filter(pk=data["supplier"], space=space).first()
    if package is None:
        raise NotFound("El formato no está disponible en este espacio.")
    if supplier is None:
        raise NotFound("El proveedor no está disponible en este espacio.")
    return PurchaseOffer.objects.create(
        space=space,
        package=package,
        supplier=supplier,
        amount=data["amount"],
        explicit_free=data["explicit_free"],
        currency=data["currency"],
        valid_from=data.get("valid_from", timezone.now()),
        created_by=user,
    )


def serialize_order(order: PurchaseOrder) -> dict:
    return {
        "id": order.pk,
        "food": order.food_id,
        "unit": order.unit_id,
        "quantity": _decimal(order.quantity),
        "received_quantity": _decimal(order.received_quantity),
        "household": order.household_id,
        "supplier": order.supplier_id,
        "supplier_name": order.supplier_name,
        "package": order.package_id,
        "package_count": _decimal(order.package_count) if order.package_count is not None else None,
        "package_quantity_snapshot": (
            _decimal(order.package_quantity_snapshot) if order.package_quantity_snapshot is not None else None
        ),
        "package_unit_snapshot": order.package_unit_snapshot_id,
        "price_snapshot": _decimal(order.price_snapshot) if order.price_snapshot is not None else None,
        "currency_snapshot": order.currency_snapshot,
        "state": order.state,
        "ordered_at": order.ordered_at.isoformat() if order.ordered_at else None,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        "created_by": order.created_by_id,
        "created_at": order.created_at.isoformat(),
    }


@transaction.atomic
def create_order(*, request, data) -> PurchaseOrder:
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    household = _membership_household(request)
    package = None
    if data.get("package") is not None:
        package = visible_packages(request.user, request.space).select_related("food", "unit").filter(
            pk=data["package"],
        ).first()
        if package is None:
            raise NotFound("El formato no está disponible en este espacio.")
    food_id = data.get("food") or (package.food_id if package else None)
    unit_id = data.get("unit") or (package.unit_id if package else None)
    food = visible_foods(request.user, request.space).filter(pk=food_id).first()
    unit = Unit.objects.filter(pk=unit_id, space=request.space).first()
    if food is None or unit is None:
        raise ValidationError({"food": "El pedido necesita alimento y unidad del mismo espacio."})
    if package and (package.food_id != food.pk or package.unit_id != unit.pk):
        raise ValidationError({"package": "El formato no corresponde al alimento y unidad del pedido."})

    supplier = None
    if data.get("supplier") is not None:
        supplier = Supermarket.objects.filter(pk=data["supplier"], space=request.space).first()
        if supplier is None:
            raise NotFound("El proveedor no está disponible en este espacio.")
    offer = None
    if data.get("offer") is not None:
        offer = accessible_offers(request.user, request.space).select_related("package", "supplier").filter(
            pk=data["offer"],
        ).first()
        if offer is None:
            raise NotFound("La oferta no está disponible en este espacio.")
        if package is None or offer.package_id != package.pk:
            raise ValidationError({"offer": "La oferta no corresponde al formato."})
        if supplier is not None and offer.supplier_id != supplier.pk:
            raise ValidationError({"offer": "La oferta no corresponde al proveedor."})
        supplier = offer.supplier

    package_count = data.get("package_count")
    if package is not None:
        if package_count is None:
            raise ValidationError({"package_count": "Indica cuántos envases se piden."})
        with localcontext() as context:
            context.prec = 64
            expected = Decimal(package.quantity) * package_count
        if expected != data["quantity"]:
            raise ValidationError({"quantity": "La cantidad no coincide con el número y contenido de envases."})
    elif package_count is not None or offer is not None:
        raise ValidationError({"package": "El número de envases y la oferta necesitan un formato."})

    return PurchaseOrder.objects.create(
        space=request.space,
        household=household,
        food=food,
        unit=unit,
        quantity=data["quantity"],
        supplier=supplier,
        supplier_name=supplier.name if supplier else "",
        package=package,
        package_count=package_count,
        package_quantity_snapshot=package.quantity if package else None,
        package_unit_snapshot=package.unit if package else None,
        price_snapshot=offer.amount if offer else None,
        currency_snapshot=offer.currency if offer else "EUR",
        created_by=request.user,
    )


@transaction.atomic
def transition_order(*, request, order: PurchaseOrder, action: str) -> PurchaseOrder:
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    order = accessible_orders(request).select_for_update(of=("self",)).filter(pk=order.pk).first()
    if order is None:
        raise NotFound("El pedido no está disponible.")
    if action == "order":
        if order.state == PurchaseOrder.ORDERED:
            return order
        if order.state != PurchaseOrder.DRAFT:
            raise ValidationError({"state": "Solo un borrador puede marcarse como pedido."})
        order.state = PurchaseOrder.ORDERED
        order.ordered_at = timezone.now()
        order.save(update_fields=["state", "ordered_at"])
        return order
    if action == "cancel":
        if order.state == PurchaseOrder.CANCELLED:
            return order
        if order.state == PurchaseOrder.RECEIVED:
            raise ValidationError({"state": "Un pedido ya recibido no se puede cancelar."})
        order.state = PurchaseOrder.CANCELLED
        order.cancelled_at = timezone.now()
        order.save(update_fields=["state", "cancelled_at"])
        return order
    raise ValidationError({"action": "Acción de pedido desconocida."})


def _receipt_fingerprint(order_id, entry_id, quantity) -> str:
    payload = f"order={order_id};entry={entry_id};quantity={canonical_decimal(quantity)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def serialize_receipt(receipt: PurchaseReceipt) -> dict:
    return {
        "id": receipt.pk,
        "order": receipt.order_id,
        "entry": receipt.entry_id,
        "quantity": _decimal(receipt.quantity),
        "movement": receipt.movement_id,
        "reversed_by": receipt.reversed_by_id,
        "idempotency_key": receipt.idempotency_key,
        "created_by": receipt.created_by_id,
        "created_at": receipt.created_at.isoformat(),
    }


@transaction.atomic
def receive_order(*, request, order: PurchaseOrder, entry: InventoryEntry, quantity, raw_key: str):
    from cuaderno.services.inventory_access import household_inventory
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    order = accessible_orders(request).select_for_update(of=("self",)).filter(pk=order.pk).first()
    entry = household_inventory(request, InventoryEntry.objects).select_for_update(of=("self",)).select_related(
        "food", "unit", "inventory_location",
    ).filter(pk=entry.pk).first()
    if order is None or entry is None:
        raise NotFound("El pedido o la existencia no están disponibles.")
    fingerprint = _receipt_fingerprint(order.pk, entry.pk, quantity)
    prior = PurchaseReceipt.objects.select_for_update().filter(
        space=request.space, idempotency_key=raw_key
    ).first()
    if prior:
        if prior.fingerprint != fingerprint:
            raise IdempotencyConflict({"idempotency_key": "La misma clave llega con otro pedido, entrada o cantidad."})
        return prior, True
    if InventoryWriteRequest.objects.filter(space=request.space, idempotency_key=f"purchase-receipt:{raw_key}").exists():
        raise IdempotencyConflict({"idempotency_key": "La clave ya pertenece a otra operación de inventario."})
    if order.state not in (PurchaseOrder.ORDERED, PurchaseOrder.PART_RECEIVED):
        raise ValidationError({"state": "Solo se reciben pedidos enviados y no cancelados."})
    if order.household_id is None or entry.inventory_location.household_id != order.household_id:
        raise NotFound("La existencia no pertenece al hogar del pedido.")
    if entry.food_id != order.food_id:
        raise ValidationError({"entry": "La existencia no corresponde al alimento pedido."})
    with localcontext() as context:
        context.prec = 64
        received_after = Decimal(order.received_quantity) + quantity
    if received_after > order.quantity:
        raise ValidationError({"quantity": "La recepción supera la cantidad pendiente."})
    try:
        with localcontext() as context:
            context.prec = 64
            ledger_quantity = convert_native_quantity(quantity, order.unit, entry.unit, order.food, request.space)
    except DomainError as exc:
        raise ValidationError({exc.code: exc.message}) from exc
    movement = apply_movement(
        entry_id=entry.pk,
        space=request.space,
        user=request.user,
        kind=StockMovement.RECEIPT,
        quantity=ledger_quantity,
        idempotency_key=f"purchase-receipt:{raw_key}",
        origin={"type": "purchase_order", "id": order.pk, "receipt_key": raw_key},
    )
    receipt = PurchaseReceipt.objects.create(
        space=request.space,
        order=order,
        entry=entry,
        movement=movement,
        quantity=quantity,
        idempotency_key=raw_key,
        fingerprint=fingerprint,
        created_by=request.user,
    )
    order.received_quantity = received_after
    order.state = PurchaseOrder.RECEIVED if received_after == order.quantity else PurchaseOrder.PART_RECEIVED
    order.save(update_fields=["received_quantity", "state"])
    return receipt, False


@transaction.atomic
def reverse_receipt(*, request, receipt: PurchaseReceipt, raw_key: str):
    from cuaderno.services.inventory_access import household_inventory
    type(request.space).objects.select_for_update().get(pk=request.space.pk)
    receipt = PurchaseReceipt.objects.filter(
        space=request.space, order_id__in=accessible_orders(request).values("pk"),
        entry_id__in=household_inventory(request, InventoryEntry.objects).values("pk"),
    ).select_for_update(of=("self",)).select_related("order", "movement").filter(pk=receipt.pk).first()
    if receipt is None:
        raise NotFound("La recepción no está disponible.")
    ledger_key = f"purchase-reversal:{raw_key}"
    if receipt.reversed_by_id:
        if receipt.reversed_by.idempotency_key != ledger_key:
            raise IdempotencyConflict({"idempotency_key": "La recepción ya se revirtió con otra clave."})
        return receipt, True
    order = accessible_orders(request).select_for_update(of=("self",)).get(pk=receipt.order_id)
    movement = reverse_movement(
        movement_id=receipt.movement_id,
        space=request.space,
        user=request.user,
        idempotency_key=ledger_key,
        purchase_receipt_id=receipt.pk,
    )
    with localcontext() as context:
        context.prec = 64
        updated = Decimal(order.received_quantity) - receipt.quantity
    if updated < 0:
        raise ValidationError({"received_quantity": "El documento de compra tiene un saldo incoherente."})
    order.received_quantity = updated
    if order.state != PurchaseOrder.CANCELLED:
        order.state = PurchaseOrder.ORDERED if updated == 0 else PurchaseOrder.PART_RECEIVED
    order.save(update_fields=["received_quantity", "state"])
    receipt.reversed_by = movement
    receipt.save(update_fields=["reversed_by"])
    return receipt, False


def replenishment(*, request, data) -> list[dict]:
    household = _membership_household(request, data.get("household"))
    plans = accessible_service_plans(request).filter(state=ServicePlan.CONFIRMED, household=household)
    requested = data.get("service_plans")
    if requested is not None:
        plans = plans.filter(pk__in=requested)
        if plans.count() != len(set(requested)):
            raise NotFound("Algún servicio no está disponible o no está confirmado.")
    plans = list(plans.order_by("pk"))
    cutoff = max([timezone.localdate(), *(p.service_date for p in plans if p.service_date)])
    needs_by_food: dict[int, list[tuple[int, Decimal]]] = {}
    for plan in plans:
        for need in plan.snapshot.get("needs", []):
            try:
                food_id = int(need["food_id"])
                unit_id = int(need["unit_id"])
                quantity = Decimal(str(need["quantity"]))
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise ValidationError({"snapshot": "Una necesidad confirmada no es válida."}) from exc
            if quantity <= 0 or not quantity.is_finite():
                raise ValidationError({"snapshot": "Una necesidad confirmada no es válida."})
            needs_by_food.setdefault(food_id, []).append((unit_id, quantity))

    minimums_by_food = {}
    for row in visible_minimums(request.user, request.space).filter(household=household).select_related("unit", "location").order_by("food_id", "location_id", "pk"):
        if row.unit.space_id != request.space.pk or (row.location_id and (row.location.space_id != request.space.pk or row.location.household_id != household.pk)):
            raise ValidationError({"minimum": "El mínimo tiene una unidad o ubicación fuera de su hogar y espacio."})
        minimums_by_food.setdefault(row.food_id, []).append(row)

    items = []
    for food_id in sorted(set(needs_by_food) | set(minimums_by_food)):
        needs = needs_by_food.get(food_id, [])
        minimums = minimums_by_food.get(food_id, [])
        food = visible_foods(request.user, request.space).filter(pk=food_id).first()
        need_units = {
            row.pk: row for row in Unit.objects.filter(pk__in={unit_id for unit_id, _ in needs}, space=request.space)
        }
        if food is None or len(need_units) != len({unit_id for unit_id, _ in needs}):
            raise ValidationError({"snapshot": "Un alimento o unidad confirmados ya no están disponibles."})
        package = visible_packages(request.user, request.space).filter(
            food=food, is_reference=True,
        ).select_related("unit").first()
        target_unit = package.unit if package else (need_units[needs[0][0]] if needs else minimums[0].unit)
        try:
            with localcontext() as context:
                context.prec = 64
                required_target = sum(
                    (
                        convert_native_quantity(quantity, need_units[unit_id], target_unit, food, request.space)
                        for unit_id, quantity in needs
                    ),
                    Decimal("0"),
                )
                converted_minimums = [(row, convert_native_quantity(row.quantity, row.unit, target_unit, food, request.space)) for row in minimums]
                minimum_target = sum((amount for _, amount in converted_minimums), Decimal("0"))
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        usable = Decimal("0")
        usable_by_location = {}
        entries = InventoryEntry.objects.filter(
            space=request.space,
            inventory_location__household=household,
            inventory_location__space=request.space,
            food=food,
            unit__space=request.space,
            amount__gt=0,
        ).filter(Q(expires__isnull=True) | Q(expires__gte=cutoff)).select_related("unit")
        for entry in entries:
            try:
                with localcontext() as context:
                    context.prec = 64
                    converted = convert_native_quantity(entry.amount, entry.unit, target_unit, food, request.space)
                    usable += converted
                    usable_by_location[entry.inventory_location_id] = usable_by_location.get(entry.inventory_location_id, Decimal("0")) + converted
            except DomainError as exc:
                raise ValidationError({exc.code: exc.message}) from exc
        with localcontext() as context:
            context.prec = 64
            target_stock = required_target + minimum_target
            location_shortfalls = []
            for row, minimum in converted_minimums:
                if row.location_id is not None:
                    local_stock = usable_by_location.get(row.location_id, Decimal("0"))
                    location_shortfalls.append({
                        "location": row.location_id, "location_name": row.location.name,
                        "minimum_stock": _decimal(minimum), "usable_stock": _decimal(local_stock),
                        "missing": _decimal(max(minimum - local_stock, Decimal("0"))),
                    })
            # Excess in another location is not an implicit stock transfer.
            local_deficit = sum((Decimal(row["missing"]) for row in location_shortfalls), Decimal("0"))
            missing = max(target_stock - usable, local_deficit, Decimal("0"))
            packages = purchase_quantity = None
            if package:
                packages = (missing / package.quantity).to_integral_value(rounding=ROUND_CEILING) if missing else Decimal("0")
                purchase_quantity = packages * package.quantity
        price = current_price(package, timezone.now()) if package else None
        items.append({
            "food": food.pk,
            "unit": target_unit.pk,
            "required": _decimal(required_target),
            "minimum_stock": _decimal(minimum_target),
            "target_stock": _decimal(target_stock),
            "location_shortfalls": location_shortfalls,
            "usable_stock": _decimal(usable),
            "missing": _decimal(missing),
            "package": package.pk if package else None,
            "packages": _decimal(packages) if packages is not None else None,
            "purchase_quantity": _decimal(purchase_quantity) if purchase_quantity is not None else None,
            "reference_price": _decimal(price.amount) if price else None,
            "currency": "EUR",
        })
    return items
