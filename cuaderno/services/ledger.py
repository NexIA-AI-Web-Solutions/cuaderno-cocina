"""Single writer for professional stock. Uses the native InventoryEntry balance."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from cookbook.models import InventoryEntry, InventoryLog
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import canonical_decimal, parse_decimal
from cuaderno.domain.stock import consume, receive
from cuaderno.models import InventoryWriteRequest, StockMovement


def inventory_metadata(entry):
    return {
        "food_id": entry.food_id, "food_name": entry.food.name if entry.food_id else None,
        "unit_id": entry.unit_id, "unit_name": entry.unit.name if entry.unit_id else None,
        "location_id": entry.inventory_location_id, "location_name": entry.inventory_location.name,
        "household_id": entry.inventory_location.household_id,
        "sub_location": entry.sub_location, "code": entry.code, "note": entry.note,
        "expires": entry.expires.isoformat() if entry.expires else None,
    }


class IdempotencyConflict(ValidationError):
    status_code = 409


def _storage_decimal(value):
    digits = list(value.as_tuple().digits)
    exponent = value.as_tuple().exponent
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if value.adjusted() >= 16 or (digits and exponent < -16):
        raise ValidationError({"quantity": "La cantidad supera la precisión de almacenamiento (16 enteros y 16 decimales)."})
    return value


def _reversal_metadata(original):
    metadata = original.metadata_snapshot
    if not isinstance(metadata, dict) or (
        "valuation" in metadata and not isinstance(metadata["valuation"], dict)
    ):
        raise ValidationError({"reverse_of": "El historial del movimiento no tiene un snapshot válido para revertirlo."})
    return metadata


def apply_movement(*, entry_id: int, space, user, kind: str, quantity, idempotency_key: str, reverses_id: int | None = None, origin: dict | None = None) -> StockMovement:
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
        raise ValidationError({"idempotency_key": "La operación de stock necesita una clave."})
    if kind not in dict(StockMovement.KINDS):
        raise ValidationError({"kind": "Tipo de movimiento desconocido."})
    try:
        parsed_quantity = parse_decimal(quantity, allow_zero=False)
    except DomainError as exc:
        raise ValidationError({"quantity": exc.message}) from exc
    _storage_decimal(parsed_quantity)
    canonical_quantity = canonical_decimal(parsed_quantity)
    origin_suffix = ""
    if origin is not None:
        if not isinstance(origin, dict):
            raise ValidationError({"origin": "El origen debe ser un documento estructurado."})
        try:
            canonical_origin = json.dumps(origin, sort_keys=True, separators=(",", ":"), allow_nan=False)
            # Keep the historical ASCII-escaped fingerprint contract. Bound
            # actual UTF-8 JSON size separately so a valid emoji cause does
            # not exceed the cap merely because it is escaped for hashing.
            origin_bytes = len(json.dumps(
                origin, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False,
            ).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"origin": "El documento de origen no es válido."}) from exc
        if origin_bytes > 2048:
            raise ValidationError({"origin": "El documento de origen es demasiado grande."})
        origin = json.loads(canonical_origin)
        origin_suffix = f";origin={canonical_origin}"
    fingerprint = hashlib.sha256(
        f"entry={entry_id};kind={kind};quantity={canonical_quantity};reverses={reverses_id or ''}{origin_suffix}".encode()
    ).hexdigest()
    with transaction.atomic():
        # Serializa las claves de idempotencia y las operaciones de inventario
        # dentro de un Space. Así dos peticiones concurrentes no pueden leer
        # ambas "sin movimiento" antes de actualizar el saldo.
        type(space).objects.select_for_update().get(pk=space.pk)
        if InventoryWriteRequest.objects.filter(space=space, idempotency_key=idempotency_key).exists():
            raise IdempotencyConflict({"idempotency_key": "La clave ya pertenece a otra operación de inventario."})
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
        valuation_metadata = {}
        if reverses_id is not None:
            original = StockMovement.objects.get(pk=reverses_id, space=space, entry_id=entry.pk)
            original_metadata = _reversal_metadata(original)
            if "valuation" in original_metadata:
                # A compensating movement keeps the original estimate even
                # if the price, unit labels or policy changed afterwards.
                valuation_metadata["valuation"] = original_metadata["valuation"]
        elif kind == StockMovement.WASTE:
            from cuaderno.services.stock_valuation import replacement_valuation
            valuation_metadata["valuation"] = replacement_valuation(
                entry=entry, quantity=parsed_quantity, as_of=timezone.now(),
            )
        current = Decimal(entry.amount)
        try:
            if kind == StockMovement.RECEIPT:
                updated, _ = receive(current, parsed_quantity, [], key=idempotency_key, fingerprint=canonical_quantity)
            else:
                updated = consume(current, parsed_quantity, allow_negative=False)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        _storage_decimal(updated)
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
            quantity=parsed_quantity,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            balance_after=updated,
            metadata_snapshot={
                **inventory_metadata(entry), **valuation_metadata,
                **({"origin": origin} if origin is not None else {}),
            },
            reverses_id=reverses_id,
            created_by=user,
        )


def replay_legacy_waste(*, entry_id: int, space, user, quantity, idempotency_key):
    """Replay pre-cause API payloads, never create a cause-less movement.

    That endpoint ignored cause entirely. Only an existing WASTE whose
    snapshot has no origin qualifies; apply_movement still checks its exact
    historical fingerprint while the Space lock remains held.
    """
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > 128:
        return None
    with transaction.atomic():
        type(space).objects.select_for_update().get(pk=space.pk)
        prior = StockMovement.objects.select_for_update().filter(
            space=space, idempotency_key=idempotency_key, kind=StockMovement.WASTE,
        ).first()
        if prior is None or not isinstance(prior.metadata_snapshot, dict) or "origin" in prior.metadata_snapshot:
            return None
        return apply_movement(
            entry_id=entry_id, space=space, user=user, kind=StockMovement.WASTE,
            quantity=quantity, idempotency_key=idempotency_key,
        )


def reverse_movement(*, movement_id: int, space, user, idempotency_key: str, purchase_receipt_id: int | None = None) -> StockMovement:
    if not idempotency_key:
        raise ValidationError({"idempotency_key": "La reversión necesita una clave."})
    with transaction.atomic():
        type(space).objects.select_for_update().get(pk=space.pk)
        original = StockMovement.objects.select_for_update().get(pk=movement_id, space=space)
        original_metadata = _reversal_metadata(original)
        origin = original_metadata.get("origin")
        if isinstance(origin, dict) and origin.get("type") == "service_plan":
            # A service consumes several entries atomically. Returning just
            # one entry would leave its produced state and snapshot untrue.
            # Fail closed even when the referenced service is missing.
            raise ValidationError({
                "reverse_of": "No se puede revertir un movimiento aislado de producción. La reversión completa del servicio aún no está disponible."
            })
        from cuaderno.models import PurchaseReceipt
        receipt = PurchaseReceipt.objects.select_for_update().filter(space=space, movement=original).first()
        if receipt and receipt.pk != purchase_receipt_id:
            raise ValidationError({"reverse_of": "Revierte esta recepción desde el pedido para conservar su saldo documental."})
        if purchase_receipt_id is not None and (receipt is None or receipt.pk != purchase_receipt_id):
            raise ValidationError({"reverse_of": "La recepción no corresponde al movimiento."})
        prior = StockMovement.objects.filter(space=space, idempotency_key=idempotency_key).first()
        if prior:
            if prior.reverses_id != original.id:
                raise IdempotencyConflict({"idempotency_key": "La misma clave pertenece a otra operación."})
            return prior
        if original.reverses_id is not None:
            raise ValidationError({"reverse_of": "Una reversión no se puede volver a revertir."})
        if original.reversals.exists():
            raise ValidationError({"reverse_of": "Ese movimiento ya está revertido."})
        kind = StockMovement.CONSUME if original.kind == StockMovement.RECEIPT else StockMovement.RECEIPT
        return apply_movement(
            entry_id=original.entry_id,
            space=space,
            user=user,
            kind=kind,
            quantity=original.quantity,
            idempotency_key=idempotency_key,
            reverses_id=original.id,
            origin=original.metadata_snapshot.get("origin"),
        )
