"""Generic recipe JSON. Unknown shapes are rejected; nothing is priced as zero."""

from __future__ import annotations

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal


def parse_recipe_document(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or any(key in payload for key in ("url", "source_url", "import_url")):
        raise DomainError("invalid_import", "La importación no descarga direcciones. Pega el JSON.")
    if not isinstance(payload.get("recipes"), list):
        raise DomainError("invalid_import", "El fichero debe tener una lista recipes.")
    recipes = []
    for raw in payload["recipes"]:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            raise DomainError("invalid_import", "Cada receta necesita nombre.")
        servings = parse_decimal(raw.get("servings", "1"), allow_zero=False)
        ingredients = []
        for item in raw.get("ingredients") or []:
            if not isinstance(item, dict) or not str(item.get("food") or "").strip():
                raise DomainError("invalid_import", "Cada ingrediente necesita alimento.")
            ingredients.append(
                {
                    "food": str(item["food"]).strip(),
                    "quantity": parse_decimal(item.get("quantity", "0"), allow_zero=True),
                    "unit": str(item.get("unit") or "").strip(),
                }
            )
        recipes.append({"name": str(raw["name"]).strip(), "servings": servings, "ingredients": ingredients})
    return recipes


def export_recipe_document(recipes: list[dict]) -> dict:
    return {"format": "cuaderno-recipes-v1", "recipes": recipes}
