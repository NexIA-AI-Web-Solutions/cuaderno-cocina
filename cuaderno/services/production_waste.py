"""Classify theoretical declared yield loss without another stock movement."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import re

from rest_framework.exceptions import ValidationError


def _invalid():
    raise ValidationError({"waste_classification": "La traza congelada de merma no es válida."})


def _quantity(value):
    # Derived quantities can contain up to 64 significant digits. They are
    # documents, not new Decimal(32,16) stock fields; do not silently round.
    if not isinstance(value, str) or len(value) > 160 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        _invalid()
    result = Decimal(value)
    if len(result.as_tuple().digits) > 64 or (result and not -64 <= result.adjusted() <= 64):
        _invalid()
    return result


def _identifier(value):
    return type(value) is int and 0 < value <= 9223372036854775807


def _label(value):
    return isinstance(value, str) and 0 < len(value) <= 1024 and not any(
        ord(character) < 32 or 127 <= ord(character) <= 159
        or 0xD800 <= ord(character) <= 0xDFFF for character in value
    )


def classify_declared_loss(snapshot, user_id, recorded_at):
    if not isinstance(snapshot, dict) or not _identifier(user_id):
        _invalid()
    traces = snapshot.get("ingredient_yields", [])
    if not isinstance(traces, list) or len(traces) > 10000:
        _invalid()
    rows, incomplete = [], False
    for trace in traces:
        if not isinstance(trace, dict) or not _identifier(trace.get("ingredient_id")):
            _invalid()
        basis, raw_ratio = trace.get("quantity_basis"), trace.get("yield_ratio")
        if not isinstance(basis, str) or basis not in {"gross", "net_usable"}:
            _invalid()
        ratio = None if raw_ratio is None else _quantity(raw_ratio)
        if (ratio is not None and not 0 < ratio <= 1) or (basis == "net_usable" and ratio is None):
            _invalid()
        purchased = _quantity(trace.get("purchased_quantity"))
        raw_useful, raw_waste = trace.get("useful_quantity"), trace.get("waste_quantity")
        if ratio is None:
            if raw_useful is not None or raw_waste is not None:
                _invalid()
            incomplete = True
        else:
            useful, waste = _quantity(raw_useful), _quantity(raw_waste)
            with localcontext() as context:
                context.prec, context.rounding = 64, ROUND_HALF_EVEN
                if ((basis == "gross" and useful != purchased * ratio)
                        or (basis == "net_usable" and purchased != useful / ratio)):
                    _invalid()
                if purchased < useful or waste != purchased - useful:
                    _invalid()
        identity = {field: trace.get(field) for field in ("food_id", "food_name", "unit_id", "unit_name")}
        if identity["food_id"] is None and identity["unit_id"] is not None:
            _invalid()
        for prefix in ("food", "unit"):
            identifier, label = identity[f"{prefix}_id"], identity[f"{prefix}_name"]
            if identifier is None and label is None:
                incomplete = True  # Historical traces did not freeze labels.
            elif not _identifier(identifier) or not _label(label):
                _invalid()
        rows.append({
            "ingredient_id": trace["ingredient_id"], **identity,
            "quantity_basis": basis, "yield_ratio": raw_ratio,
            "purchased_quantity": trace["purchased_quantity"],
            "useful_quantity": raw_useful, "waste_quantity": raw_waste,
            "cause": "declared_yield",
        })
    return {
        "schema_version": 1, "policy": "declared_yield_estimate",
        "classification_only": True, "included_in_gross_needs": True,
        "additional_stock_movement": False, "coverage": "declared_yields_only",
        "status": "unknown" if not rows else "incomplete" if incomplete else "declared",
        "recorded_by": user_id, "recorded_at": recorded_at.isoformat(), "lines": rows,
    }


def validate_frozen_classification(plan):
    """Legacy productions remain replayable without fabricated history."""
    production = plan.snapshot.get("production") if isinstance(plan.snapshot, dict) else None
    if not isinstance(production, dict):
        _invalid()
    if "waste_classification" in production and (
            type(production.get("schema_version")) is not int or production["schema_version"] != 2):
        _invalid()
    if "schema_version" in production:
        if type(production["schema_version"]) is not int or production["schema_version"] != 2:
            _invalid()
        identifiers = production.get("movement_ids")
        if (not isinstance(identifiers, list) or len(identifiers) > 10000
                or any(not _identifier(value) for value in identifiers)
                or len(set(identifiers)) != len(identifiers)
                or type(production.get("stock_changed")) is not bool
                or production["stock_changed"] != bool(identifiers)
                or production.get("edition") not in ("profesional", "integral")
                or (production["edition"] == "profesional" and identifiers)
                or plan.produced_at is None
                or production.get("produced_at") != plan.produced_at.isoformat()):
            _invalid()
    if "waste_classification" not in production:
        if production.get("schema_version") == 2:
            _invalid()
        return
    document = production["waste_classification"]
    if not isinstance(document, dict) or plan.produced_at is None:
        _invalid()
    if (type(document.get("schema_version")) is not int or document["schema_version"] != 1
            or document.get("classification_only") is not True
            or document.get("included_in_gross_needs") is not True
            or document.get("additional_stock_movement") is not False):
        _invalid()
    expected = classify_declared_loss(plan.snapshot, document.get("recorded_by"), plan.produced_at)
    if document != expected:
        _invalid()
    return deepcopy(document)
