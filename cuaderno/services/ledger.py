"""Single writer for professional stock. Uses the native InventoryEntry balance."""

from __future__ import annotations

from decimal import Decimal
import hashlib

from django.db import transaction
from rest_framework.exceptions import ValidationError

from cookbook.models import InventoryEntry, InventoryLog
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.domain.stock import consume, receive
from cuaderno.models import StockMovement


class IdempotencyConflict(ValidationError):
    status_code = 409


def apply_movement(*, entry_id: int, space, user, kind: str, quantity, idempotency_key: str, reverses_id: int | None = None) -> StockMovement:
    if not idempotency_key:
        raise ValidationError({"idempotency_key": "La operación de stock necesita una clave."})
    fingerprint = hashlib.sha256(f"{kind}:{quantity}".encode()).hexdigest()
    with transaction.atomic():
        prior = (
            StockMovement.objects.select_for_update()
            .filter(space=space, idempotency_key=idempotency_key)
            .first()
        )
        if prior:
            if prior.fingerprint != fingerprint:
                raise IdempotencyConflict({"idempotency_key": "La misma clave llega con otra cantidad."})
            return prior
        entry = InventoryEntry.objects.select_for_update().get(pk=entry_id, space=space)
        current = Decimal(entry.amount)
        try:
            if kind == StockMovement.RECEIPT:
                updated, _ = receive(current, quantity, [], key=idempotency_key, fingerprint=quantity)
            elif kind in (StockMovement.CONSUME, StockMovement.WASTE):
                updated = consume(current, quantity, allow_negative=False)
            else:
                raise DomainError("invalid_movement", "Tipo de movimiento desconocido.")
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        old_amount = entry.amount
        entry.amount = updated
        entry.save(update_fields=["amount", "updated_at"])
        booking = InventoryLog.B_ADD if kind == StockMovement.RECEIPT else InventoryLog.B_REMOVE
        InventoryLog.objects.create(
            space=space,
            entry=entry,
            booking_type=booking,
            old_amount=old_amount,
            new_amount=updated,
            old_inventory_location=entry.inventory_location,
            new_inventory_location=entry.inventory_location,
            note=kind,
        )
        return StockMovement.objects.create(
            space=space,
            entry=entry,
            kind=kind,
            quantity=parse_decimal(quantity, allow_zero=True),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            reverses_id=reverses_id,
            created_by=user,
        )


def reverse_movement(*, movement_id: int, space, user, idempotency_key: str) -> StockMovement:
    with transaction.atomic():
        original = StockMovement.objects.select_for_update().get(pk=movement_id, space=space)
        kind = StockMovement.CONSUME if original.kind == StockMovement.RECEIPT else StockMovement.RECEIPT
        return apply_movement(
            entry_id=original.entry_id,
            space=space,
            user=user,
            kind=kind,
            quantity=original.quantity,
            idempotency_key=idempotency_key,
            reverses_id=original.id,
        )
