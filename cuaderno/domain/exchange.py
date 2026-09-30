"""Generic recipe JSON. Unknown shapes are rejected; nothing is priced as zero."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal, validate_explicit_price
from cuaderno.domain.ingredient_yields import parse_yield_ratio, validate_yield_policy


def _fields(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed.split()):
        raise DomainError("unsupported_import", "El documento contiene campos no soportados; utiliza la exportación nativa para esos datos.")


def _number(value, *, allow_zero=False):
    number = parse_decimal(value, allow_zero=allow_zero)
    # Matches native Ingredient and professional DecimalField(32, 16), without rounding.
    digits = list(number.as_tuple().digits)
    exponent = number.as_tuple().exponent
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if number.adjusted() >= 16 or (digits and exponent < -16):
        raise DomainError("invalid_import", "El decimal supera la precisión de almacenamiento (16 enteros y 16 decimales).")
    return number


def parse_recipe_document(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or any(key in payload for key in ("url", "source_url", "import_url")):
        raise DomainError("invalid_import", "La importación no descarga direcciones. Pega el JSON.")
    if not isinstance(payload.get("recipes"), list):
        raise DomainError("invalid_import", "El fichero debe tener una lista recipes.")
    _fields(payload, "format source source_space recipes catalog mapping preview_sha256 media warnings")
    if payload.get("format") not in (None, "cuaderno-recipes-v1", "cuaderno-recipes-v2"):
        raise DomainError("unsupported_import", "Versión de intercambio no soportada.")
    if "media" in payload:
        _fields(payload["media"], "included method url_downloads")
        if payload["media"] != {"included": False, "method": "native-tandoor-zip", "url_downloads": False}:
            raise DomainError("unsupported_import", "Las fotografías se transfieren mediante la exportación ZIP nativa, sin descargar URLs.")
    if len(payload["recipes"]) > 1000 or len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) > 2_000_000:
        raise DomainError("import_limit", "La importación supera 1000 recetas o 2 MB.")
    source = str(payload.get("source") or payload.get("format") or "cuaderno-recipes-v1").strip()
    if not source or len(source) > 64:
        raise DomainError("invalid_import", "Indica la fuente o formato de la importación.")
    recipes = []
    for raw in payload["recipes"]:
        _fields(raw, "id_externo external_id name servings description private steps ingredients yield")
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            raise DomainError("invalid_import", "Cada receta necesita nombre.")
        servings = parse_decimal(raw.get("servings", "1"), allow_zero=False)
        if servings != servings.to_integral_value() or servings > 2147483647:
            raise DomainError("invalid_import", "Las raciones de Tandoor deben ser un número entero positivo.")
        external_id = str(raw.get("id_externo") or raw.get("external_id") or "").strip()
        if not external_id:
            canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            external_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if len(external_id) > 256 or len(str(raw["name"]).strip()) > 128:
            raise DomainError("invalid_import", "El identificador o nombre es demasiado largo.")
        if len(str(raw.get("description") or "")) > 512:
            raise DomainError("invalid_import", "La descripción supera 512 caracteres.")
        raw_steps = raw.get("steps", [{"instruction": "", "ingredients": raw.get("ingredients") or []}])
        if not isinstance(raw_steps, list) or len(raw_steps) > 1000:
            raise DomainError("invalid_import", "Los pasos deben ser una lista de hasta 1000 elementos.")
        steps, ingredients = [], []
        for raw_step in raw_steps:
            _fields(raw_step, "instruction name ingredients step_recipe")
            if not isinstance(raw_step, dict) or not isinstance(raw_step.get("ingredients", []), list):
                raise DomainError("invalid_import", "Cada paso necesita una lista de ingredientes.")
            step_ingredients = []
            for item in raw_step.get("ingredients", []):
                _fields(item, "food food_id food_ref quantity unit unit_id unit_ref note original_text is_header no_amount quantity_basis yield_ratio")
                if not isinstance(item, dict):
                    raise DomainError("invalid_import", "Ingrediente inválido.")
                food = str(item.get("food") or "").strip()
                excluded = item.get("no_amount") is True or item.get("is_header") is True
                if not food and not excluded:
                    raise DomainError("invalid_import", "Cada ingrediente necesita alimento.")
                if any(len(str(item.get(key) or "")) > limit for key, limit in (("food", 128), ("unit", 128), ("note", 256), ("original_text", 512))):
                    raise DomainError("invalid_import", "Texto de ingrediente demasiado largo.")
                parsed = {
                    "food": food, "food_id": item.get("food_id"),
                    "quantity": _number(item.get("quantity", "0"), allow_zero=excluded),
                    "unit": str(item.get("unit") or "").strip(), "unit_id": item.get("unit_id"),
                    "note": item.get("note"), "original_text": item.get("original_text"),
                    "is_header": item.get("is_header") is True, "no_amount": item.get("no_amount") is True,
                    "food_ref": item.get("food_ref"), "unit_ref": item.get("unit_ref"),
                    "quantity_basis": item.get("quantity_basis", "gross"),
                    "yield_ratio": None if item.get("yield_ratio") is None else parse_yield_ratio(item["yield_ratio"]),
                }
                validate_yield_policy(parsed["quantity_basis"], parsed["yield_ratio"])
                step_ingredients.append(parsed)
                ingredients.append(parsed)
            if len(ingredients) > 10000:
                raise DomainError("import_limit", "Una receta supera 10000 ingredientes.")
            if len(str(raw_step.get("name") or "")) > 128:
                raise DomainError("invalid_import", "El nombre del paso supera 128 caracteres.")
            steps.append({"instruction": str(raw_step.get("instruction") or ""), "name": str(raw_step.get("name") or ""),
                          "ingredients": step_ingredients, "step_recipe": raw_step.get("step_recipe")})
        recipes.append(
            {
                "source": source,
                "external_id": external_id,
                "name": str(raw["name"]).strip(),
                "description": str(raw.get("description") or ""),
                "private": raw.get("private") is True,
                "servings": servings,
                "ingredients": ingredients,
                "steps": steps,
                "yield": raw.get("yield"),
            }
        )
    return recipes


def parse_portable_catalog(payload, recipes):
    """Validate portable references before touching the ORM; no name-based identity."""
    catalog = payload.get("catalog")
    if payload.get("format") != "cuaderno-recipes-v2":
        if catalog is not None or any(r["yield"] or any(s["step_recipe"] for s in r["steps"]) or
                                      any(i["food_ref"] or i["unit_ref"] for i in r["ingredients"]) for r in recipes):
            raise DomainError("unsupported_import", "Los vínculos y rendimientos requieren cuaderno-recipes-v2.")
        return None
    _fields(catalog, "foods units packages conversions")
    result = {}
    allowed = {
        "foods": "ref id name recipe",
        "units": "ref id name base_unit plural_name description",
        "packages": "ref id food_ref unit_ref label quantity is_reference prices",
        "conversions": "ref id food_ref base_unit_ref converted_unit_ref base_amount converted_amount",
    }
    for kind, fields in allowed.items():
        values = catalog.get(kind, [])
        if not isinstance(values, list) or len(values) > 10000:
            raise DomainError("invalid_import", "Catálogo inválido o demasiado grande.")
        result[kind] = {}
        names = set()
        for value in values:
            _fields(value, fields)
            ref = value.get("ref")
            if not isinstance(ref, str) or not ref or len(ref) > 256 or ref in result[kind]:
                raise DomainError("invalid_import", "Identidad del catálogo ausente o repetida.")
            if kind in ("foods", "units") and (not isinstance(value.get("name"), str) or not value["name"] or len(value["name"]) > 128):
                raise DomainError("invalid_import", "Nombre de catálogo inválido.")
            if kind in ("foods", "units"):
                if value["name"] in names:
                    raise DomainError("invalid_import", "El catálogo repite un nombre con identidades diferentes.")
                names.add(value["name"])
            result[kind][ref] = dict(value)
    ids = {r["external_id"] for r in recipes}

    def require(ref, collection, optional=False):
        if ref is None and optional:
            return
        if not isinstance(ref, str) or ref not in collection:
            raise DomainError("invalid_import", "Una referencia no está incluida en el documento.")
    for food in result["foods"].values():
        require(food.get("recipe"), ids, optional=True)
    for unit in result["units"].values():
        for field, limit in (("base_unit", 256), ("plural_name", 128), ("description", 100000)):
            if unit.get(field) is not None and (not isinstance(unit[field], str) or len(unit[field]) > limit):
                raise DomainError("invalid_import", "Los metadatos de la unidad no son válidos.")
    conversion_pairs = set()
    for conversion in result["conversions"].values():
        require(conversion.get("food_ref"), result["foods"], optional=True)
        require(conversion.get("base_unit_ref"), result["units"])
        require(conversion.get("converted_unit_ref"), result["units"])
        base_ref = conversion["base_unit_ref"]
        converted_ref = conversion["converted_unit_ref"]
        # Match native f_unique_conversion_per_space: directed endpoints and
        # NULL foods are distinct in PostgreSQL. Preserve reverse, parallel
        # global and self edges in document order, hence native PK precedence.
        if conversion.get("food_ref") is not None:
            pair = (conversion["food_ref"], base_ref, converted_ref)
            if pair in conversion_pairs:
                raise DomainError("invalid_import", "El catálogo repite una conversión dirigida del mismo alimento.")
            conversion_pairs.add(pair)
        conversion["base_amount"] = _number(conversion.get("base_amount"))
        conversion["converted_amount"] = _number(conversion.get("converted_amount"))
    references = set()
    for package in result["packages"].values():
        require(package.get("food_ref"), result["foods"])
        require(package.get("unit_ref"), result["units"])
        package["quantity"] = _number(package.get("quantity"))
        if not isinstance(package.get("label"), str) or len(package["label"]) > 128 or not isinstance(package.get("is_reference"), bool):
            raise DomainError("invalid_import", "Formato de compra inválido.")
        if package["is_reference"]:
            if package["food_ref"] in references:
                raise DomainError("invalid_import", "Un alimento solo puede tener un formato de referencia.")
            references.add(package["food_ref"])
        if not isinstance(package.get("prices"), list):
            raise DomainError("invalid_import", "El historial de precios debe ser una lista.")
        package["prices"] = [dict(price) if isinstance(price, dict) else price for price in package["prices"]]
        for price in package["prices"]:
            _fields(price, "amount explicit_free valid_from note")
            if not isinstance(price.get("explicit_free"), bool) or not isinstance(price.get("note", ""), str) or len(price.get("note", "")) > 256:
                raise DomainError("invalid_import", "Precio inválido.")
            price["amount"] = _number(price.get("amount"), allow_zero=price["explicit_free"])
            try:
                validate_explicit_price(price["amount"], price["explicit_free"])
            except DomainError as exc:
                raise DomainError("invalid_import", exc.message) from exc
            try:
                price["valid_from"] = datetime.fromisoformat(price["valid_from"])
                if price["valid_from"].utcoffset() is None:
                    raise ValueError("timezone required")
            except (KeyError, TypeError, ValueError) as exc:
                raise DomainError("invalid_import", "La fecha del precio necesita zona horaria.") from exc
    edges = {}
    for recipe in recipes:
        edges[recipe["external_id"]] = []
        output = recipe["yield"]
        if output is not None:
            _fields(output, "quantity unit_ref")
            require(output.get("unit_ref"), result["units"])
            recipe["yield"] = {**output, "quantity": _number(output.get("quantity"))}
        for step in recipe["steps"]:
            require(step["step_recipe"], ids, optional=True)
            if step["step_recipe"]:
                edges[recipe["external_id"]].append(step["step_recipe"])
            for ingredient in step["ingredients"]:
                for field in ("food", "unit"):
                    ref = ingredient[field + "_ref"]
                    require(ref, result[field + "s"], optional=not ingredient[field])
                    if ref is not None and ingredient[field] != result[field + "s"][ref]["name"]:
                        raise DomainError("invalid_import", "El nombre y la referencia del catálogo no coinciden.")
                if ingredient["food_ref"]:
                    child = result["foods"][ingredient["food_ref"]].get("recipe")
                    validate_yield_policy(ingredient["quantity_basis"], ingredient["yield_ratio"], is_subrecipe=bool(child))
                    if child:
                        edges[recipe["external_id"]].append(child)
    # Bound depth independently of cycle checks to avoid Python recursion limits.
    depths = {}

    def walk(node, path):
        if node in path:
            raise DomainError("recipe_cycle", "Referencia circular en el documento.")
        if len(path) >= 32:
            raise DomainError("recipe_graph_limit", "El documento supera 32 niveles de subrecetas.")
        if node not in depths:
            depths[node] = 1 + max((walk(child, (*path, node)) for child in edges[node]), default=0)
        if depths[node] + len(path) > 32:
            raise DomainError("recipe_graph_limit", "El documento supera 32 niveles de subrecetas.")
        return depths[node]
    for node in edges:
        walk(node, ())
    return result


def export_recipe_document(recipes: list[dict]) -> dict:
    return {"format": "cuaderno-recipes-v1", "recipes": recipes}
