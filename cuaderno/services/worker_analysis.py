"""Deterministic, bounded operational analysis over native records. Never writes."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
import re

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from cookbook.helper.permission_helper import has_group_permission
from cookbook.models import InventoryEntry, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.models import RecipeDietDeclaration
from cuaderno.services.allergens import recipe_allergens
from cuaderno.services.costing import _cost_ingredient, _load_costing_context, cost_recipe, visible_recipes
from cuaderno.services.inventory_access import household_inventory
from cuaderno.services.price_history import recipe_price_impact_payload
from cuaderno.services.profiles import profile_for_space
from cuaderno.services.purchasing import accessible_orders, replenishment
from cuaderno.services.reservations import visible_reservations
from cuaderno.services.service_plans import accessible_service_plans
from cuaderno.services.subrecipes import convert_native_quantity, native_recipe_graph, sheet_from_recipes
from cuaderno.services.visibility import visible_foods, visible_packages

TITLES = {
    "cost_completion": "Completar escandallos", "price_watch": "Vigilar precios",
    "service_briefing": "Preparar el servicio", "requirements_review": "Revisar requisitos",
    "purchase_review": "Revisar compras", "receipt_review": "Revisar recepciones",
    "menu_candidates": "Proponer platos con existencias", "service_learning": "Aprender del registro de servicios",
}
PROFESSIONAL = {"service_briefing", "requirements_review", "service_learning", "menu_candidates"}
INTEGRAL = {"purchase_review", "receipt_review"}
PARAMS = {"date", "start", "end", "recipe_id", "package_id", "supplier_id", "order_id", "servings", "budget", "limit"}
# Candidates are explicit textual mentions; they are never dietary declarations.
MENTIONS = {
    "gluten": r"\b(?:gluten|cel[ií]ac[oa]s?)\b", "lactosa": r"\b(?:lactosa|l[aá]cteos?)\b",
    "frutos_secos": r"\b(?:frutos? secos?|cacahuetes?)\b", "huevo": r"\bhuevos?\b",
    "marisco": r"\bmariscos?\b", "pescado": r"\bpescados?\b",
    "vegetariano": r"\bvegetarian[oa]s?\b", "vegano": r"\bvegan[oa]s?\b",
    "sal": r"\b(?:sin sal|baj[oa] en sal|hipos[oó]dic[oa])\b",
    "diabetes": r"\b(?:diabetes|diab[eé]tic[oa]s?)\b",
}


def _number(value):
    return format(value, "f") if value is not None else None


def _day(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValidationError({field: "Usa una fecha ISO (AAAA-MM-DD)."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "La fecha no es válida."}) from exc


def _parameters(params):
    if params is None:
        params = {}
    if not isinstance(params, dict) or set(params) - PARAMS:
        raise ValidationError({"params": "Parámetros no admitidos."})
    values = dict(params)
    limit = values.get("limit", 30)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError({"limit": "El límite debe ser un entero de 1 a 100."})
    values["limit"] = limit
    for field in ("recipe_id", "package_id", "supplier_id", "order_id"):
        if field in values and (type(values[field]) is not int or not 0 < values[field] <= 2147483647):
            raise ValidationError({field: "El identificador debe ser un entero positivo."})
    for field in ("date", "start", "end"):
        if field in values:
            values[field] = _day(values[field], field)
    for field in ("servings", "budget"):
        if field in values:
            try:
                values[field] = parse_decimal(values[field], allow_zero=field == "budget")
                if values[field].adjusted() > 15 or values[field].as_tuple().exponent < -16:
                    raise DomainError("invalid_decimal", "Usa un decimal de hasta 16 enteros y 16 decimales.")
            except DomainError as exc:
                raise ValidationError({field: exc.message}) from exc
    if "start" in values and "end" in values and (values["end"] < values["start"] or (values["end"] - values["start"]).days > 366):
        raise ValidationError({"period": "El periodo debe estar ordenado y abarcar como máximo 366 días."})
    return values


def _effective_period(params, default_start, default_end):
    start = params.get("start", default_start)
    end = params.get("end", default_end)
    if end < start or (end - start).days > 366:
        raise ValidationError({"period": "El periodo debe estar ordenado y abarcar como máximo 366 días."})
    return start, end


def _evidence(report, kind, identifier, label):
    urls = {"recipe": f"/recipe/{identifier}", "package": "/cuaderno/precios", "order": "/cuaderno/almacen",
            "service": "/cuaderno/produccion", "reservation": "/cuaderno/reservas",
            "food": "/cuaderno/almacen", "entry": "/cuaderno/almacen"}
    row = {"type": kind, "id": identifier, "label": label, "action_url": urls.get(kind)}
    if row not in report["evidence"]:
        report["evidence"].append(row)


def _bounded(rows, report, params):
    result = list(rows[:params["limit"] + 1])
    if len(result) > params["limit"]:
        report["warnings"].append("Se muestra una selección limitada; reduce los filtros para revisar todos los registros.")
    return result[:params["limit"]]


def _recipes(request, report, params):
    rows = visible_recipes(request.user, request.space).order_by("pk")
    if "recipe_id" in params:
        rows = rows.filter(pk=params["recipe_id"])
    return _bounded(rows, report, params)


def _services(request, report, params, filters):
    rows = accessible_service_plans(request, aggregate_filters=filters).select_related("meal_plan__recipe").order_by("service_date", "pk")
    if "recipe_id" in params:
        rows = rows.filter(meal_plan__recipe_id=params["recipe_id"])
    return _bounded(rows, report, params)


def _safe_error(report, recipe, exc):
    # Domain errors may contain private child labels/IDs. Preserve only their code.
    report["items"].append({"recipe_id": recipe.pk, "name": recipe.name, "status": "unavailable",
                            "codes": [exc.code], "action": "Revisa la ficha y sus referencias autorizadas."})


def _cost_completion(request, report, params, at):
    for recipe in _recipes(request, report, params):
        try:
            _, graph, _ = native_recipe_graph([recipe.pk], request.space, request.user)
            context = _load_costing_context(graph, request.space.pk, at)
            blockers = []
            for source in graph.values():
                for step in source.steps.all():
                    for ingredient in step.ingredients.all():
                        result = _cost_ingredient(ingredient, 1, at, [], context)
                        codes = list(result.warnings) if result.status != "complete" else []
                        if ingredient.food_id and ingredient.food.recipe_id and not ingredient.is_header and not ingredient.no_amount:
                            # Food.recipe is costed through its declared output, not a reference package.
                            codes = []
                            declared = context.yields.get(ingredient.food.recipe_id)
                            if declared is None:
                                codes.append("rendimiento_desconocido")
                            else:
                                try:
                                    convert_native_quantity(ingredient.amount, ingredient.unit, declared.unit,
                                                            ingredient.food, request.space)
                                except DomainError as exc:
                                    codes.append(exc.code)
                        if codes:
                            blockers.append({"recipe_id": source.pk, "step_id": step.pk,
                                "ingredient_id": ingredient.pk, "food_id": ingredient.food_id,
                                "food_name": ingredient.food.name if ingredient.food_id else None,
                                "unit_id": ingredient.unit_id, "codes": codes,
                                "action": "Completa cantidad, formato, precio, rendimiento o conversión en la ficha indicada."})
            cost = cost_recipe(recipe, params.get("servings", Decimal(recipe.servings or 1)), at, request.user)
            report["items"].append({"recipe_id": recipe.pk, "name": recipe.name, "status": cost["status"],
                                    "cost": cost, "blockers": blockers})
            for source in graph.values():
                _evidence(report, "recipe", source.pk, source.name)
        except DomainError as exc:
            _safe_error(report, recipe, exc)

    grouped = {}
    for item in report["items"]:
        for blocker in item.get("blockers", []):
            for code in blocker["codes"]:
                key = (blocker["food_id"], code)
                question = grouped.setdefault(key, {"food_id": blocker["food_id"], "food_name": blocker["food_name"],
                    "code": code, "recipe_ids": [], "ingredient_ids": [],
                    "question": "Completa el dato indicado en la ficha de origen.",
                    "action_url": f"/recipe/{blocker['recipe_id']}"})
                if item["recipe_id"] not in question["recipe_ids"]:
                    question["recipe_ids"].append(item["recipe_id"])
                if blocker["ingredient_id"] not in question["ingredient_ids"]:
                    question["ingredient_ids"].append(blocker["ingredient_id"])
    report["grouped_questions"] = [{**row, "affected_recipe_count": len(row["recipe_ids"])} for row in grouped.values()]


def _price_watch(request, report, params, at):
    today = timezone.localdate(at)
    start, end = _effective_period(params, today - timedelta(days=30), today + timedelta(days=30))
    report.update(start=start.isoformat(), end=end.isoformat())
    recipes = _recipes(request, report, params)
    packages = visible_packages(request.user, request.space).filter(is_reference=True).order_by("pk")
    if "package_id" in params:
        packages = packages.filter(pk=params["package_id"])
    packages = _bounded(packages, report, {**params, "limit": min(params["limit"], 10)})
    # A maximum of 100 engine comparisons; the same bounded rule applies on every run.
    compared = 0
    for recipe in recipes:
        for package in packages:
            if compared >= 100:
                report["warnings"].append("Se alcanzó el límite de 100 comparaciones de precios.")
                break
            compared += 1
            try:
                impact = recipe_price_impact_payload(recipe, package, params.get("servings", Decimal(recipe.servings or 1)), at, request.user)
                if impact["affected"]:
                    report["items"].append({"type": "recipe_price_impact", "name": recipe.name,
                                            "package_id": package.pk, **impact})
                    _evidence(report, "recipe", recipe.pk, recipe.name)
                    _evidence(report, "package", package.pk, package.label)
            except DomainError as exc:
                _safe_error(report, recipe, exc)
                break
    report["service_drift"] = []
    if profile_for_space(request.space).edition not in ("profesional", "integral"):
        return
    filters = {"state__in": ("confirmed", "produced"), "service_date__gte": start, "service_date__lte": end}
    for plan in _services(request, report, params, filters):
        recipe = plan.meal_plan.recipe if plan.meal_plan_id else None
        frozen = plan.snapshot.get("cost")
        if recipe is None or not isinstance(frozen, dict):
            continue
        try:
            current = cost_recipe(recipe, plan.covers, at, request.user)
            difference = None
            if frozen.get("status") == current["status"] == "complete":
                difference = _number(Decimal(current["unrounded"]) - Decimal(frozen["unrounded"]))
            report["service_drift"].append({"service_id": plan.pk, "title": plan.title, "recipe_id": recipe.pk,
                "frozen_cost": frozen, "current_cost": current, "difference": difference,
                "comparison": "Coste congelado frente a receta y precios actuales; puede incluir cambios de ingredientes."})
            _evidence(report, "service", plan.pk, plan.title)
        except (DomainError, ValueError, TypeError, KeyError):
            report["warnings"].append("Un servicio no tiene costes comparables válidos.")
    report["warnings"].append("Las variaciones son estimaciones de ingredientes; no representan ahorro realizado ni beneficio neto.")


def _candidates(note):
    return [{"keyword": label, "matched_text": match.group(0), "status": "candidate", "requires_confirmation": True}
            for label, pattern in MENTIONS.items() for match in [re.search(pattern, note or "", re.IGNORECASE)] if match]


def _reservations(request, report, params, day):
    rows = visible_reservations(request, dates={"service_date": day}).exclude(state="cancelled").order_by("service_time", "pk")
    rows = _bounded(rows, report, params)
    result = []
    for row in rows:
        result.append({"reservation_id": row.pk, "time": row.service_time.isoformat(timespec="minutes"),
                       "covers": row.covers, "state": row.state, "note": row.note,
                       "requirement_candidates": _candidates(row.note)})
        _evidence(report, "reservation", row.pk, f"Reserva {row.pk}")
    return result


def _service_briefing(request, report, params, at):
    day = params.get("date", timezone.localdate())
    report["date"] = day.isoformat()
    report["reservations"] = _reservations(request, report, params, day)
    plans = _services(request, report, params, {"service_date": day, "state__in": ("draft", "confirmed", "produced")})
    food_ids = set(visible_foods(request.user, request.space).values_list("pk", flat=True))
    unit_ids = set(Unit.objects.filter(space=request.space).values_list("pk", flat=True))
    for plan in plans:
        needs = plan.snapshot.get("needs", [])
        if not isinstance(needs, list) or any(not isinstance(need, dict) or need.get("food_id") not in food_ids
                or need.get("unit_id") not in unit_ids for need in needs):
            report["warnings"].append("Una ficha congelada tiene referencias no disponibles y requiere revisión.")
            continue
        frozen_allergens = plan.snapshot.get("allergens")
        if isinstance(frozen_allergens, dict):
            frozen_foods = frozen_allergens.get("foods", [])
            if not isinstance(frozen_foods, list) or any(not isinstance(food, dict) or food.get("id") not in food_ids for food in frozen_foods):
                report["warnings"].append("Una ficha de alérgenos congelada tiene referencias no disponibles y requiere revisión.")
                continue
        tasks = list(plan.preparation_items.filter(space=request.space).order_by("position", "pk"))
        report["items"].append({"service_id": plan.pk, "title": plan.title, "state": plan.state,
            "covers": _number(plan.covers), "needs": needs, "frozen": plan.state != "draft",
            "cost": plan.snapshot.get("cost"), "allergens": plan.snapshot.get("allergens"),
            "preparation": {"total": len(tasks), "pending": sum(not task.checked for task in tasks),
                "items": [{"id": task.pk, "name": task.name, "instruction": task.instruction,
                           "checked": task.checked, "source_step_id": task.source_step_id} for task in tasks]},
            "warnings": ["Confirma el servicio para congelar necesidades y preparación."] if plan.state == "draft" else []})
        _evidence(report, "service", plan.pk, plan.title)
    report["warnings"].append("Las notas son requisitos pendientes de confirmación; la ausencia de declaración no garantiza ausencia de alérgenos.")


def _requirements_review(request, report, params, at):
    report["dietary_guarantees"] = False
    report["reservations"] = _reservations(request, report, params, params.get("date", timezone.localdate()))
    for recipe in _recipes(request, report, params):
        try:
            assessment = recipe_allergens(user=request.user, space=request.space, recipe_id=recipe.pk)
            diets = list(RecipeDietDeclaration.objects.filter(space=request.space, recipe=recipe).order_by("slug"))
            report["items"].append({"recipe_id": recipe.pk, "name": recipe.name, "allergens": assessment,
                "diets": [{"slug": row.slug, "status": row.status, "note": row.note,
                           "source_id": row.pk, "updated_by": row.updated_by_id} for row in diets],
                "requirement_candidates": _candidates(recipe.description),
                "action": "Contrasta declaraciones, fichas del proveedor y requisitos confirmados antes del servicio."})
            _evidence(report, "recipe", recipe.pk, recipe.name)
        except DomainError as exc:
            _safe_error(report, recipe, exc)
    report["warnings"].append("Las menciones explícitas de notas son candidatos; nunca cambian declaraciones ni prueban aptitud dietética.")


def _orders(request, report, params):
    rows = accessible_orders(request).select_related("food", "unit").prefetch_related("receipts").order_by("pk")
    for field in ("order_id", "supplier_id"):
        if field in params:
            rows = rows.filter(**{"pk" if field == "order_id" else "supplier_id": params[field]})
    return _bounded(rows, report, params)


def _purchase_review(request, report, params, at):
    day = params.get("date", timezone.localdate(at))
    start, end = _effective_period(params, day, day)
    report.update(start=start.isoformat(), end=end.isoformat())
    for order in _orders(request, report, params):
        receipts = [receipt for receipt in order.receipts.all() if receipt.space_id == request.space.pk and receipt.reversed_by_id is None]
        recorded = sum((receipt.quantity for receipt in receipts), Decimal(0))
        pending = order.quantity - order.received_quantity
        issues = []
        if recorded != order.received_quantity:
            issues.append("receipt_total_mismatch")
        if order.state == "received" and pending != 0:
            issues.append("received_state_with_pending_quantity")
        if order.state in ("ordered", "part_received") and order.ordered_at and (at - order.ordered_at).days >= 7 and pending > 0:
            issues.append("pending_over_7_days")
        if order.price_snapshot is None:
            issues.append("price_unknown")
        report["items"].append({"order_id": order.pk, "food_id": order.food_id, "name": order.food.name,
            "unit_id": order.unit_id, "unit_name": order.unit.name, "state": order.state,
            "quantity": _number(order.quantity), "received_quantity": _number(order.received_quantity),
            "receipt_quantity": _number(recorded), "pending_quantity": _number(pending), "issues": issues,
            "price_snapshot": _number(order.price_snapshot), "currency": order.currency_snapshot,
            "action": "Revisa documentos y cantidades; un pedido pendiente no aumenta existencias."})
        _evidence(report, "order", order.pk, f"Pedido {order.pk}")

    report["pending_orders"] = [{**item, "arrival_unknown": True} for item in report["items"]
                                if Decimal(item["pending_quantity"]) > 0 and item["state"] not in ("draft", "cancelled")]
    buying_data = {"from_date": start, "to_date": end}
    needs = replenishment(request=request, data=buying_data)
    service_filters = {"state": "confirmed", "household_id": request.user_space.household_id}
    if "from_date" in buying_data:
        service_filters["service_date__gte"] = buying_data["from_date"]
    if "to_date" in buying_data:
        service_filters["service_date__lte"] = buying_data["to_date"]
    report["service_ids"] = list(accessible_service_plans(request, aggregate_filters=service_filters)
                                 .order_by("pk").values_list("pk", flat=True))
    if len(needs) > params["limit"]:
        report["warnings"].append("La propuesta de compra está limitada; revisa todas las necesidades en Almacén.")
    report["buying_needs"] = needs[:params["limit"]]
    for need in report["buying_needs"]:
        package = visible_packages(request.user, request.space).filter(pk=need["package"]).first() if need["package"] else None
        if package:
            _evidence(report, "package", package.pk, package.label)
        food = visible_foods(request.user, request.space).filter(pk=need["food"]).first()
        unit = Unit.objects.filter(space=request.space, pk=need["unit"]).first()
        need["food_id"] = need["food"]
        need["unit_id"] = need["unit"]
        need["package_id"] = need["package"]
        if food:
            _evidence(report, "food", food.pk, food.name)
        need["food_name"] = food.name if food else None
        need["unit_name"] = unit.name if unit else None
        need["package_label"] = package.label if package else None
        need["arrival_assumed"] = False
        need["action_url"] = "/cuaderno/almacen"
    report["warnings"].append("Necesidades confirmadas y mínimos frente a stock utilizable. Los pedidos pendientes se muestran aparte: fecha de llegada desconocida, no descontados de la compra propuesta.")


def _receipt_review(request, report, params, at):
    from cuaderno.models import PurchaseReceipt
    orders = accessible_orders(request)
    if "order_id" in params:
        orders = orders.filter(pk=params["order_id"])
    if "supplier_id" in params:
        orders = orders.filter(supplier_id=params["supplier_id"])
    rows = household_inventory(request, PurchaseReceipt.objects.filter(order__in=orders), path="entry__inventory_location__household_id")
    rows = rows.select_related("order__unit", "entry__unit", "entry__food", "movement", "reversed_by").order_by("pk")
    for receipt in _bounded(rows, report, params):
        issues = []
        order = receipt.order
        movement = receipt.movement
        if receipt.entry.food_id != order.food_id:
            issues.append("food_mismatch")
        if movement.space_id != request.space.pk or movement.entry_id != receipt.entry_id or movement.kind != "receipt":
            issues.append("movement_mismatch")
        try:
            expected = convert_native_quantity(receipt.quantity, order.unit, receipt.entry.unit, receipt.entry.food, request.space)
            if expected != movement.quantity:
                issues.append("movement_quantity_mismatch")
        except DomainError:
            issues.append("conversion_unknown")
        if receipt.reversed_by_id and (receipt.reversed_by.space_id != request.space.pk
                or receipt.reversed_by.reverses_id != movement.pk):
            issues.append("reversal_mismatch")
        report["items"].append({"receipt_id": receipt.pk, "order_id": order.pk, "quantity": _number(receipt.quantity),
            "entry_id": receipt.entry_id, "movement_id": movement.pk, "reversed": receipt.reversed_by_id is not None,
            "issues": issues, "action": "Contrasta recepción, pedido y movimiento antes de corregir mediante reversión."})
        _evidence(report, "order", order.pk, f"Pedido {order.pk}")


def _menu_candidates(request, report, params, at):
    day = params.get("date", timezone.localdate())
    stock_known = profile_for_space(request.space).edition == "integral"
    stock = list(household_inventory(request, InventoryEntry.objects.all()).filter(amount__gt=0)
                 .filter(Q(expires__isnull=True) | Q(expires__gte=day)).select_related("food", "unit").order_by("pk")[:2001]) if stock_known else []
    if len(stock) > 2000:
        raise ValidationError({"inventory": "Hay más de 2000 lotes; reduce el inventario operativo antes del análisis."})
    foods = {row.name: row for row in visible_foods(request.user, request.space)}
    units = {row.name: row for row in Unit.objects.filter(space=request.space)}
    by_food = defaultdict(list)
    for entry in stock:
        if entry.food_id and entry.unit_id:
            by_food[entry.food_id].append(entry)
    for recipe in _recipes(request, report, params):
        try:
            servings = params.get("servings", Decimal(recipe.servings or 1))
            if recipe.servings <= 0:
                raise DomainError("invalid_servings", "Raciones base inválidas.")
            sheet = sheet_from_recipes([recipe.pk], request.space, request.user,
                                      factor_ratios={recipe.pk: (servings, Decimal(recipe.servings))})
            needs, sufficient = [], bool(sheet["needs"]) and not sheet["warnings"]
            for name, quantity in sheet["needs"].items():
                food, unit = foods.get(name), units.get(sheet["units"].get(name))
                available, unknown = Decimal(0), False
                entries = []
                if food and unit:
                    for entry in by_food.get(food.pk, []):
                        try:
                            available += convert_native_quantity(entry.amount, entry.unit, unit, food, request.space)
                            entries.append(entry.pk)
                        except DomainError:
                            unknown = True
                else:
                    unknown = True
                shortfall = max(Decimal(quantity) - available, Decimal(0))
                sufficient &= shortfall == 0 and not unknown
                needs.append({"food_id": food.pk if food else None, "name": name,
                    "unit_id": unit.pk if unit else None, "quantity": quantity, "available": _number(available) if stock_known else None,
                    "shortfall": _number(shortfall) if stock_known else None, "unknown_conversion": unknown, "inventory_entry_ids": entries})
            cost = cost_recipe(recipe, servings, at, request.user)
            budget = params.get("budget")
            within_budget = None if budget is None or cost["status"] != "complete" else Decimal(cost["per_serving"]) <= budget
            report["items"].append({"recipe_id": recipe.pk, "name": recipe.name, "servings": _number(servings),
                "needs": needs, "stock_known": stock_known, "stock_sufficient": bool(sufficient) if stock_known else None, "cost": cost, "within_budget": within_budget,
                "warnings": sheet["warnings"], "dietary_guarantee": False})
            _evidence(report, "recipe", recipe.pk, recipe.name)
        except DomainError as exc:
            _safe_error(report, recipe, exc)
    if not stock_known:
        report["warnings"].append("La edición Profesional compara recetas y costes; existencias desconocidas. Integral añade el inventario registrado.")
    report["items"].sort(key=lambda row: (not row.get("stock_sufficient", False), row.get("within_budget") is False, row["recipe_id"]))
    report["warnings"].append("Cada plato se evalúa por separado con existencias registradas; no reserva stock ni garantiza varios platos simultáneos. Presupuesto por ración.")


def _service_learning(request, report, params, at):
    end = params.get("end", params.get("date", timezone.localdate()))
    start = params.get("start", end - timedelta(days=90))
    if end < start or (end - start).days > 366:
        raise ValidationError({"period": "El periodo debe estar ordenado y abarcar como máximo 366 días."})
    rows = _services(request, report, {**params, "limit": 100}, {"service_date__gte": start, "service_date__lte": end})
    groups = {}
    for plan in rows:
        recipe_id = plan.snapshot.get("recipe_id") or (plan.meal_plan.recipe_id if plan.meal_plan_id else None)
        key = recipe_id
        item = groups.setdefault(key, {"recipe_id": recipe_id, "recorded_count": 0, "produced_count": 0,
            "cancelled_count": 0, "produced_covers": Decimal(0), "service_ids": [], "weekdays": defaultdict(int)})
        item["recorded_count"] += 1
        item["produced_count"] += plan.state == "produced"
        item["cancelled_count"] += plan.state == "cancelled"
        if plan.state == "produced":
            item["produced_covers"] += plan.covers
        item["service_ids"].append(plan.pk)
        item["weekdays"][str(plan.service_date.weekday())] += 1
        _evidence(report, "service", plan.pk, plan.title)
    for item in groups.values():
        item["produced_covers"] = _number(item["produced_covers"])
        item["weekdays"] = dict(item["weekdays"])
    report["items"] = list(groups.values())
    report.update(start=start.isoformat(), end=end.isoformat(), forecast=False, sampled_service_count=len(rows))
    report["warnings"].append("Frecuencias de servicios registrados y raciones por plato; no son demanda futura, clientes únicos ni desperdicio real.")


def build_worker_report(request, kind, params=None):
    """Build JSON-safe evidence for an explicit report. Safe for GET or saved runs."""
    if not isinstance(kind, str) or kind not in TITLES:
        raise ValidationError({"kind": "Trabajador no admitido."})
    if getattr(request, "space", None) is None or not has_group_permission(request, ["guest"]):
        raise PermissionDenied("Necesitas pertenecer al espacio para consultar análisis.")
    params = _parameters(params)
    profile = profile_for_space(request.space)
    if (kind in PROFESSIONAL and profile.edition not in ("profesional", "integral")) or (kind in INTEGRAL and profile.edition != "integral"):
        raise PermissionDenied("Este trabajador necesita la edición operativa correspondiente.")
    at = timezone.now()
    report = {"kind": kind, "title": TITLES[kind], "summary": "", "items": [], "warnings": [], "evidence": [],
              "generated_at": at.isoformat(), "as_of": at.isoformat(), "analysis_mode": "deterministic", "read_only": True}
    handler = globals()[f"_{kind}"]
    with localcontext() as context:
        context.prec = 64
        handler(request, report, params, at)
    for item in report["items"]:
        item.setdefault("title", item.get("name") or item.get("title") or (
            f"Pedido {item['order_id']}" if "order_id" in item else
            f"Receta {item.get('recipe_id')}" if "recipe_id" in item else report["title"]))
        if item.get("recipe_id"):
            item.setdefault("action_url", f"/recipe/{item['recipe_id']}")
        elif "service_id" in item:
            item.setdefault("action_url", "/cuaderno/produccion")
        elif "order_id" in item:
            item.setdefault("action_url", "/cuaderno/almacen")
        item.setdefault("detail", item.get("action", "Análisis de registros guardados; revisa las fuentes antes de actuar."))
        item.setdefault("severity", "warning" if item.get("issues") or item.get("blockers") or item.get("status") in ("incomplete", "invalid", "unavailable") else "info")
        item.setdefault("values", {key: value for key, value in item.items()
                                    if key not in ("title", "detail", "severity", "values")})
    report["warnings"] = list(dict.fromkeys(report["warnings"]))
    count = len(report["items"])
    report["summary"] = f"{count} registros analizados con datos guardados en este espacio."
    if kind == "purchase_review":
        report["summary"] = f"{count} pedidos revisados y {len(report['buying_needs'])} necesidades de compra; llegada de pendientes sin confirmar."
    elif kind == "service_briefing":
        report["summary"] = f"{count} fichas de servicio y {len(report['reservations'])} reservas para {report['date']}."
    elif kind == "service_learning":
        report["summary"] = f"{report['sampled_service_count']} servicios registrados agrupados en {count} platos; sin previsión de demanda."
    elif kind == "price_watch":
        report["summary"] = f"{count} impactos de precios y {len(report.get('service_drift', []))} comparaciones con costes congelados."
    elif kind == "cost_completion":
        report["summary"] = f"{count} recetas revisadas y {len(report['grouped_questions'])} datos pendientes agrupados."
    return report
