"""Bounded user declarations and native-menu inputs; no dietary inference or I/O."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit

DIETS = (
    ("celiacos", "Celíacos"), ("colesterol", "Colesterol"), ("diabetes", "Diabetes"),
    ("hiposodica", "Hiposódica"), ("gastrica", "Gástrica"), ("fibra", "Fibra"),
    ("sinfructosa", "Sin fructosa"), ("sinlactosa", "Sin lactosa"),
)
STATUSES = ("unknown", "suitable", "unsuitable")
DECLARATION = "Valoraciones dietéticas declaradas por usuarios; no constituyen una evaluación clínica. Sin valoración significa desconocido."


class InputError(ValueError):
    pass


def fields(data, allowed, required=()):
    if type(data) is not dict or set(data) - set(allowed) or not set(required) <= set(data):
        raise InputError("Envía los campos previstos para esta operación.")
    return data


def text(value, maximum=128, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum
            or any(ord(c) < 32 and c not in "\n\t" or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise InputError("El texto tiene un formato o longitud no válidos.")
    value = value.strip()
    if not value and not empty:
        raise InputError("Completa el texto requerido.")
    return value


def integer(value, minimum=1, maximum=2147483647, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise InputError("El identificador o número entero no es válido.")
    return value


def servings(value):
    # Native MealPlan stores decimal(8,4); do not silently round input.
    if type(value) not in (str, int) or not re.fullmatch(r"\d{1,4}(?:[.,]\d{1,4})?", str(value)):
        raise InputError("Indica raciones positivas de hasta cuatro decimales.")
    try:
        result = Decimal(str(value).replace(",", "."))
    except InvalidOperation as exc:
        raise InputError("Raciones no válidas.") from exc
    if not 0 < result < 10000:
        raise InputError("Las raciones deben ser mayores que cero y menores que 10000.")
    return result


def date_range(start, end, maximum_days=35):
    try:
        if any(type(v) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in (start, end)):
            raise ValueError
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError) as exc:
        raise InputError("Indica fechas válidas con formato AAAA-MM-DD.") from exc
    if not 0 <= (last - first).days < maximum_days:
        raise InputError(f"El periodo debe contener entre 1 y {maximum_days} días.")
    return first, last


def reference_url(value):
    value = text(value, 1024, empty=True)
    if not value:
        return value
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or "\\" in value or any(c.isspace() for c in value)):
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise InputError("Usa una referencia web http o https sin credenciales.") from exc
    return value


def diet_rows(rows):
    if type(rows) is not list or len(rows) > len(DIETS):
        raise InputError("Envía hasta ocho declaraciones dietéticas.")
    result, seen = [], set()
    for row in rows:
        fields(row, ("slug", "status", "note"), ("slug", "status"))
        slug, status = row["slug"], row["status"]
        if not isinstance(slug, str) or slug not in dict(DIETS) or slug in seen or status not in STATUSES:
            raise InputError("Dieta o valoración no válida o repetida.")
        seen.add(slug)
        result.append({"slug": slug, "status": status, "note": text(row.get("note", ""), 1000, empty=True)})
    return result


def template_input(data):
    fields(data, ("name", "weeks", "entries", "revision"), ("name", "weeks", "entries"))
    result = {"name": text(data["name"]), "weeks": integer(data["weeks"], 1, 5), "entries": []}
    if type(data["entries"]) is not list or not 1 <= len(data["entries"]) <= 200:
        raise InputError("La plantilla debe tener entre 1 y 200 platos.")
    slots = set()
    for entry in data["entries"]:
        fields(entry, ("day_index", "meal_type", "course", "recipe", "title", "source_url", "servings"),
               ("day_index", "meal_type", "servings"))
        row = {
            "day_index": integer(entry["day_index"], 0, result["weeks"] * 7 - 1),
            "meal_type": integer(entry["meal_type"]), "course": integer(entry.get("course"), nullable=True),
            "recipe": integer(entry.get("recipe"), nullable=True),
            "title": text(entry.get("title", ""), 64, empty=True),
            "source_url": reference_url(entry.get("source_url", "")), "servings": servings(entry["servings"]),
        }
        if not row["recipe"] and not row["title"]:
            raise InputError("Cada plato necesita receta o título.")
        slot = (row["day_index"], row["meal_type"], row["course"])
        if slot in slots:
            raise InputError("Una plantilla no puede repetir día, comida y plato.")
        slots.add(slot)
        result["entries"].append(row)
    return result
