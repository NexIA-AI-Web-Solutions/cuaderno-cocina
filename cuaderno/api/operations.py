import json
import hashlib
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.helper.permission_helper import CustomIsGuest, CustomIsUser, CustomTokenHasReadWriteScope
from cookbook.models import Food, Ingredient, InventoryEntry, MealPlan, MealType, Recipe, Step, Unit, UnitConversion
from cuaderno.domain.errors import DomainError
from cuaderno.domain.exchange import MAX_CATALOG_ITEMS, MAX_EXCHANGE_RECIPES, export_recipe_document, parse_recipe_document, validate_exchange_limits
from cuaderno.domain.margin import food_cost_gap
from cuaderno.domain.money import parse_decimal
from cuaderno.domain.ingredient_yields import validate_yield_policy
from cuaderno.domain.production import assert_no_cycle, consolidate, scale_covers
from cuaderno.domain.stock import packs_to_buy, waste_value
from cuaderno.models import AllergenDeclaration, RecipeExchangeRecord, RecipeYield, ServicePlan, SpaceProfile, StockMovement
from cuaderno.services.ledger import IdempotencyConflict, apply_movement, replay_legacy_waste, reverse_movement
from cuaderno.services.service_plans import (
    accessible_service_plans,
    cancel_service_plan,
    confirm_service_plan,
    produce_service_plan,
    reverse_service_plan,
    serialize_service_plan,
)
from cuaderno.services.subrecipes import sheet_from_recipes


def _balances(space):
    return list(InventoryEntry.objects.filter(space=space).order_by("id").values_list("id", "amount"))


def _dec(value) -> str:
    return format(Decimal(str(value)), "f")


def _require(space, minimum: str):
    profile, _ = SpaceProfile.objects.get_or_create(space=space)
    rank = {SpaceProfile.ESENCIAL: 1, SpaceProfile.PROFESIONAL: 2, SpaceProfile.INTEGRAL: 3}
    if rank[profile.edition] < rank[minimum]:
        raise PermissionDenied(f"Esta operación pertenece a la edición {minimum}.")
    return profile


class MovementView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request):
        from cuaderno.services.inventory_access import household_inventory
        _require(request.space, SpaceProfile.INTEGRAL)
        rows = household_inventory(request, StockMovement.objects.all(), "entry__inventory_location__household_id").order_by("-id").values(
            "id", "kind", "quantity", "entry_id", "balance_after", "reverses_id", "created_at", "created_by_id", "metadata_snapshot",
        )[:100]
        return Response(
            [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "quantity": _dec(row["quantity"]),
                    "entry": row["entry_id"],
                    "balance": _dec(row["balance_after"]) if row["balance_after"] is not None else None,
                    "reverses": row["reverses_id"],
                    "created_at": row["created_at"].isoformat(),
                    "created_by": row["created_by_id"],
                    "metadata_snapshot": row["metadata_snapshot"],
                }
                for row in rows
            ]
        )

    @transaction.atomic
    def post(self, request):
        from cuaderno.services.inventory_access import household_inventory
        _require(request.space, SpaceProfile.INTEGRAL)
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        try:
            if request.data.get("reverse_of"):
                get_object_or_404(household_inventory(request, StockMovement.objects.all(), "entry__inventory_location__household_id"),
                                  pk=request.data.get("reverse_of"))
                movement = reverse_movement(
                    movement_id=request.data.get("reverse_of"),
                    space=request.space,
                    user=request.user,
                    idempotency_key=request.data.get("idempotency_key", ""),
                )
            else:
                entry = get_object_or_404(household_inventory(request, InventoryEntry.objects.all()), pk=request.data.get("entry"))
                origin = None
                movement = None
                if request.data.get("kind") == StockMovement.WASTE:
                    movement = replay_legacy_waste(
                        entry_id=entry.id, space=request.space, user=request.user,
                        quantity=request.data.get("quantity"), idempotency_key=request.data.get("idempotency_key", ""),
                    )
                if request.data.get("kind") == StockMovement.WASTE and movement is None:
                    raw_cause = request.data.get("cause")
                    if not isinstance(raw_cause, str):
                        raise ValidationError({"cause": "Indica un motivo del desperdicio de 1 a 256 caracteres."})
                    cause = raw_cause.strip()
                    if not cause or len(cause) > 256 or any(
                        ord(character) < 32 or 127 <= ord(character) <= 159
                        or 0xD800 <= ord(character) <= 0xDFFF for character in raw_cause
                    ):
                        raise ValidationError({"cause": "Indica un motivo de 1 a 256 caracteres, sin caracteres de control."})
                    origin = {"type": "standalone_waste", "cause": cause}
                if movement is None:
                    movement = apply_movement(
                        entry_id=entry.id,
                        space=request.space,
                        user=request.user,
                        kind=request.data.get("kind"),
                        quantity=request.data.get("quantity"),
                        idempotency_key=request.data.get("idempotency_key", ""),
                        origin=origin,
                    )
        except IdempotencyConflict as exc:
            return Response(exc.detail, status=409)
        except StockMovement.DoesNotExist:
            raise ValidationError({"reverse_of": "Ese movimiento no está en este espacio."})
        movement.entry.refresh_from_db()
        return Response(
            {
                "movement_id": movement.id,
                "balance": _dec(movement.balance_after) if movement.balance_after is not None else None,
                "current_balance": _dec(movement.entry.amount),
                "metadata_snapshot": movement.metadata_snapshot,
                "kind": movement.kind,
                "reverses": movement.reverses_id,
            },
            status=201,
        )


class PurchaseOrderView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def post(self, request):
        _require(request.space, SpaceProfile.INTEGRAL)
        from cuaderno.api.purchasing import OrderWriteSerializer
        from cuaderno.services.purchasing import create_order
        serializer = OrderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier_name = request.data.get("supplier_name", "")
        if not isinstance(supplier_name, str) or len(supplier_name) > 128:
            raise ValidationError({"supplier_name": "El nombre del proveedor debe ser texto de hasta 128 caracteres."})
        order = create_order(request=request, data=serializer.validated_data)
        if supplier_name and order.supplier_id is None:
            order.supplier_name = supplier_name.strip()
            order.save(update_fields=["supplier_name"])
        return Response(
            {"id": order.id, "stock_unchanged": True, "quantity": _dec(order.quantity)},
            status=201,
        )


class ReplenishmentView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def post(self, request):
        _require(request.space, SpaceProfile.INTEGRAL)
        packs, quantity = packs_to_buy(request.data.get("required"), request.data.get("usable_stock"), request.data.get("pack_size"))
        value = None
        if request.data.get("waste_quantity") is not None:
            value = _dec(waste_value(request.data.get("waste_quantity"), request.data.get("unit_valuation")))
        profile = _require(request.space, SpaceProfile.INTEGRAL)
        gap = food_cost_gap(
            request.data.get("ingredient_cost", "0"),
            request.data.get("selling_price"),
            profile.target_food_cost_ratio,
        )
        return Response(
            {
                "packs": _dec(packs),
                "quantity": _dec(quantity),
                "waste_value": value,
                "food_cost": gap,
            }
        )


class ServicePlanView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request, plan_id=None):
        _require(request.space, SpaceProfile.PROFESIONAL)
        if plan_id is not None:
            rows = accessible_service_plans(request, plan_id).select_related("meal_plan").order_by("service_date", "id")
            return Response(serialize_service_plan(get_object_or_404(rows, pk=plan_id)))
        return Response([serialize_service_plan(plan) for plan in accessible_service_plans(request, as_list=True)])

    @transaction.atomic
    def post(self, request, plan_id=None):
        _require(request.space, SpaceProfile.PROFESIONAL)
        if not isinstance(request.data, dict):
            raise ValidationError({"service": "Envía un objeto JSON para el servicio."})
        if plan_id is not None:
            if request.data.get("action") == "reverse":
                type(request.space).objects.select_for_update().only("pk").get(pk=request.space.pk)
            plan = get_object_or_404(accessible_service_plans(request, plan_id).select_related("space"), pk=plan_id)
            action = request.data.get("action")
            if action == "confirm":
                plan = confirm_service_plan(plan, request.user)
                payload = serialize_service_plan(plan)
                payload["stock_changed"] = False
                return Response(payload)
            if action == "cancel":
                plan = cancel_service_plan(plan)
                payload = serialize_service_plan(plan)
                payload["stock_changed"] = False
                return Response(payload)
            if action == "produce":
                try:
                    plan, movement_ids, stock_changed = produce_service_plan(
                        plan, request.user, request.data.get("idempotency_key")
                    )
                except IdempotencyConflict as exc:
                    return Response(exc.detail, status=409)
                payload = serialize_service_plan(plan)
                payload.update({"movement_ids": movement_ids, "stock_changed": stock_changed})
                return Response(payload)
            if action == "reverse":
                try:
                    plan, movement_ids, stock_changed = reverse_service_plan(
                        plan, request.user, request.data.get("idempotency_key"),
                    )
                except IdempotencyConflict as exc:
                    return Response(exc.detail, status=409)
                payload = serialize_service_plan(plan)
                payload.update({"reversal_movement_ids": movement_ids, "stock_changed": stock_changed})
                return Response(payload)
            raise ValidationError({"action": "Acción de servicio desconocida."})

        try:
            if request.data.get("covers") is not None:
                covers = parse_decimal(request.data.get("covers"), allow_zero=False)
            else:
                covers = scale_covers(
                    request.data.get("base_covers", "0"),
                    request.data.get("extra", "0"),
                    request.data.get("cancelled", "0"),
                )
        except DomainError as exc:
            raise ValidationError({"covers": exc.message}) from exc
        if covers <= 0 or covers != covers.to_integral_value() or covers > Decimal("9999"):
            raise ValidationError({"covers": "Los comensales deben ser un entero entre 1 y 9999."})
        if getattr(request, "user_space", None) is None or request.user_space.household_id is None:
            raise ValidationError({"household": "Asigna un hogar operativo antes de crear servicios."})
        raw_title = request.data.get("title", "Servicio")
        if raw_title is None:
            raw_title = "Servicio"
        if not isinstance(raw_title, str):
            raise ValidationError({"title": "El título debe ser texto."})
        title = raw_title.strip() or "Servicio"
        if len(title) > 128:
            raise ValidationError({"title": "El título no puede superar 128 caracteres."})
        raw_service_date = request.data.get("service_date")
        try:
            if not isinstance(raw_service_date, str) or len(raw_service_date) != 10:
                raise ValueError
            service_date = date.fromisoformat(raw_service_date)
        except ValueError as exc:
            raise ValidationError({"service_date": "Usa una fecha local válida AAAA-MM-DD."}) from exc
        before = _balances(request.space)
        recipe = None
        if request.data.get("recipe"):
            from cuaderno.services.costing import visible_recipes
            recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=request.data.get("recipe"))
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        meal_type, _ = MealType.objects.get_or_create(
            name="Servicio",
            space=request.space,
            defaults={"created_by": request.user, "default": False},
        )
        start = timezone.make_aware(datetime.combine(service_date, time.min), ZoneInfo("Europe/Madrid"))
        meal = MealPlan.objects.create(
            recipe=recipe,
            servings=covers.quantize(Decimal("0.0001")),
            title=title[:64],
            created_by=request.user,
            meal_type=meal_type,
            note=f"comensales={_dec(covers)}",
            from_date=start,
            to_date=start,
            space=request.space,
        )
        plan = ServicePlan.objects.create(
            space=request.space,
            meal_plan=meal,
            title=title,
            covers=covers,
            created_by=request.user,
            household=request.user_space.household,
            service_date=service_date,
        )
        after = _balances(request.space)
        return Response(
            {
                "id": plan.id,
                "covers": _dec(plan.covers),
                "meal_plan": meal.id,
                "payment": None,
                "stock_changed": before != after,
                "timezone": "Europe/Madrid",
                "service_date": service_date.isoformat(),
                "state": plan.state,
            },
            status=201,
        )


class ProductionSheetView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def post(self, request):
        _require(request.space, SpaceProfile.PROFESIONAL)
        if request.data.get("service_plan") is not None:
            plan = get_object_or_404(
                accessible_service_plans(request, request.data.get("service_plan")).select_related("space"),
                pk=request.data.get("service_plan"),
            )
            if request.data.get("action") == "produce":
                try:
                    plan, movement_ids, stock_changed = produce_service_plan(
                        plan, request.user, request.data.get("idempotency_key")
                    )
                except IdempotencyConflict as exc:
                    return Response(exc.detail, status=409)
                return Response(
                    {
                        "service_plan": plan.pk,
                        "state": plan.state,
                        "movement_ids": movement_ids,
                        "stock_changed": stock_changed,
                        "snapshot": plan.snapshot,
                    }
                )
            if plan.state not in (ServicePlan.CONFIRMED, ServicePlan.PRODUCED):
                raise ValidationError({"state": "Confirma el servicio antes de abrir su ficha."})
            return Response(
                {
                    "service_plan": plan.pk,
                    "state": plan.state,
                    "needs": plan.snapshot.get("needs", []),
                    "cost": plan.snapshot.get("cost"),
                    "warnings": plan.snapshot.get("warnings", []),
                    "stock_changed": False,
                }
            )
        before = _balances(request.space)
        edges = request.data.get("edges") or {}
        start = request.data.get("start")
        if start:
            try:
                assert_no_cycle(start, edges)
            except DomainError as exc:
                raise ValidationError({exc.code: exc.message}) from exc
        totals = consolidate([(item["component"], item["quantity"]) for item in request.data.get("usages") or []])
        linked = {}
        if request.data.get("recipe_ids"):
            try:
                linked = sheet_from_recipes(request.data.get("recipe_ids"), request.space, request.user)
            except DomainError as exc:
                raise ValidationError({exc.code: exc.message}) from exc
            for key, value in linked["needs"].items():
                totals[key] = totals.get(key, Decimal("0")) + Decimal(value)
        after = _balances(request.space)
        return Response(
            {
                "needs": {key: _dec(value) for key, value in totals.items()},
                "stock_changed": before != after,
                "edges": linked.get("edges", edges),
                "warnings": linked.get("warnings", []),
                "units": linked.get("units", {}),
            }
        )


class RecipeYieldView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request, recipe_id):
        from cuaderno.services.costing import visible_recipes
        get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        row = get_object_or_404(RecipeYield, space=request.space, recipe_id=recipe_id)
        return Response({"recipe": row.recipe_id, "quantity": _dec(row.quantity), "unit": row.unit_id})

    def put(self, request, recipe_id):
        from cuaderno.services.costing import visible_recipes
        _require(request.space, SpaceProfile.PROFESIONAL)
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        unit = get_object_or_404(Unit, pk=request.data.get("unit"), space=request.space)
        try:
            quantity = parse_decimal(request.data.get("quantity"), allow_zero=False)
        except DomainError as exc:
            raise ValidationError({"quantity": exc.message}) from exc
        row, _ = RecipeYield.objects.update_or_create(recipe=recipe, defaults={
            "space": request.space, "quantity": quantity, "unit": unit, "updated_by": request.user,
        })
        return Response({"recipe": row.recipe_id, "quantity": _dec(row.quantity), "unit": row.unit_id})


class AllergenView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get_permissions(self):
        permissions = self.permission_classes
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            permissions = [CustomIsGuest & CustomTokenHasReadWriteScope]
        return [permission() for permission in permissions]

    def get(self, request):
        from cuaderno.services.allergens import food_allergens, recipe_allergens
        from rest_framework.exceptions import NotFound
        selectors = [field for field in ("food", "recipe") if field in request.query_params]
        if len(selectors) != 1:
            raise ValidationError({"scope": "Indica exactamente un alimento o una receta."})
        field = selectors[0]
        values = request.query_params.getlist(field)
        raw = values[0] if len(values) == 1 else ""
        if not raw or not raw.isascii() or not raw.isdecimal() or len(raw) > 19:
            raise ValidationError({field: "Indica un identificador entero positivo."})
        identifier = int(raw)
        if not 0 < identifier <= 9223372036854775807:
            raise ValidationError({field: "Indica un identificador entero positivo."})
        try:
            if field == "food":
                payload = food_allergens(user=request.user, space=request.space, food_id=identifier)
            else:
                payload = recipe_allergens(user=request.user, space=request.space, recipe_id=identifier)
        except DomainError as exc:
            if exc.code == "recipe_missing":
                raise NotFound("La receta no está disponible.") from exc
            raise ValidationError({exc.code: exc.message}) from exc
        return Response(payload)

    @transaction.atomic
    def post(self, request):
        _require(request.space, SpaceProfile.PROFESIONAL)
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        from cuaderno.services.visibility import visible_foods
        if not isinstance(request.data, dict):
            raise ValidationError({"body": "Envía un objeto con alimento, nombre y estado."})
        identifier = request.data.get("food")
        if type(identifier) is not int or not 0 < identifier <= 9223372036854775807:
            raise ValidationError({"food": "Indica un identificador entero positivo."})
        raw_name = request.data.get("name")
        if not isinstance(raw_name, str):
            raise ValidationError({"name": "Indica el alérgeno declarado como texto."})
        name = raw_name.strip()
        if not name or len(name) > 128 or any(
            ord(character) < 32 or 127 <= ord(character) <= 159
            or 0xD800 <= ord(character) <= 0xDFFF for character in raw_name
        ):
            raise ValidationError({"name": "Indica un nombre de 1 a 128 caracteres, sin caracteres de control."})
        state = request.data.get("state", AllergenDeclaration.UNKNOWN)
        if not isinstance(state, str) or state not in dict(AllergenDeclaration.STATES):
            raise ValidationError({"state": "Estado de alérgeno desconocido."})
        food = get_object_or_404(visible_foods(request.user, request.space), pk=identifier)
        row = AllergenDeclaration.objects.create(
            space=request.space,
            food=food,
            name=name,
            state=state,
        )
        return Response(
            {"id": row.id, "state": row.state, "undeclared_means_absent": False},
            status=201,
        )


class RecipeExchangeView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    @staticmethod
    def export_limit_response():
        return Response({
            "export_limit": "La exportación JSON supera los límites de importación "
                            "(1000 recetas, 2 MB o catálogo de 10000 elementos). "
                            "Utiliza la exportación nativa de Tandoor o una copia de seguridad completa.",
        }, status=413)

    def get(self, request):
        recipes = []
        from cuaderno.services.costing import visible_recipes
        from cuaderno.services.subrecipes import native_recipe_graph
        from cuaderno.models import PackageFormat

        visible = list(visible_recipes(request.user, request.space)[:MAX_EXCHANGE_RECIPES + 1])
        if len(visible) > MAX_EXCHANGE_RECIPES:
            return self.export_limit_response()
        try:
            native_recipe_graph([recipe.pk for recipe in visible], request.space, request.user)
        except DomainError as exc:
            raise ValidationError({exc.code: "Una referencia de receta no está disponible o es circular."}) from exc
        foods, units, packages = {}, {}, []

        def add_unit(unit):
            if unit.space_id != request.space.pk:
                raise ValidationError({"catalog": "Una unidad no pertenece al espacio."})
            units[unit.pk] = {"ref": f"unit:{unit.pk}", "id": unit.pk, "name": unit.name, "base_unit": unit.base_unit,
                              "plural_name": unit.plural_name, "description": unit.description}
            return f"unit:{unit.pk}"

        for recipe in visible:
            steps = []
            for step in recipe.steps.all():
                if step.space_id != request.space.pk:
                    raise ValidationError({"catalog": "Un paso no pertenece al espacio."})
                ingredients = []
                for ingredient in step.ingredients.all():
                    if ingredient.space_id != request.space.pk or (ingredient.food_id and ingredient.food.space_id != request.space.pk):
                        raise ValidationError({"catalog": "Un ingrediente no pertenece al espacio."})
                    if ingredient.food_id:
                        food = ingredient.food
                        foods[food.pk] = {"ref": f"food:{food.pk}", "id": food.pk, "name": food.name,
                                          "recipe": f"tandoor-recipe:{food.recipe_id}" if food.recipe_id else None}
                    ingredients.append(
                        {
                            "food": ingredient.food.name if ingredient.food_id else "",
                            "food_id": ingredient.food_id,
                            "quantity": _dec(ingredient.amount),
                            "quantity_basis": ingredient.quantity_basis,
                            "yield_ratio": None if ingredient.yield_ratio is None else _dec(ingredient.yield_ratio),
                            "unit": ingredient.unit.name if ingredient.unit_id else "",
                            "unit_id": ingredient.unit_id,
                            "note": ingredient.note,
                            "original_text": ingredient.original_text,
                            "is_header": ingredient.is_header,
                            "no_amount": ingredient.no_amount,
                            "food_ref": f"food:{ingredient.food_id}" if ingredient.food_id else None,
                            "unit_ref": add_unit(ingredient.unit) if ingredient.unit_id else None,
                        }
                    )
                steps.append({"name": step.name, "instruction": step.instruction, "ingredients": ingredients,
                              "step_recipe": f"tandoor-recipe:{step.step_recipe_id}" if step.step_recipe_id else None})
            declared = RecipeYield.objects.filter(recipe=recipe).select_related("unit").first()
            if declared and declared.space_id != request.space.pk:
                raise ValidationError({"catalog": "El rendimiento no pertenece al espacio."})
            recipes.append(
                {
                    "external_id": f"tandoor-recipe:{recipe.id}",
                    "name": recipe.name,
                    "description": recipe.description,
                    "private": recipe.private,
                    "servings": str(recipe.servings),
                    "steps": steps,
                    "yield": {"quantity": _dec(declared.quantity), "unit_ref": add_unit(declared.unit)} if declared else None,
                }
            )
        payload = export_recipe_document(recipes)
        for package in PackageFormat.objects.filter(food_id__in=foods).select_related("unit").order_by("id"):
            if package.space_id != request.space.pk or package.prices.exclude(space=request.space).exists():
                raise ValidationError({"catalog": "Un formato o precio no pertenece al espacio."})
            packages.append({"ref": f"package:{package.pk}", "id": package.pk, "food_ref": f"food:{package.food_id}",
                             "unit_ref": add_unit(package.unit), "quantity": _dec(package.quantity), "label": package.label,
                             "is_reference": package.is_reference,
                             "prices": [{"amount": _dec(price.amount), "explicit_free": price.explicit_free,
                                         "valid_from": price.valid_from.isoformat(), "note": price.note}
                                        for price in package.prices.filter(space=request.space).order_by("valid_from", "id")]})
        payload["format"] = "cuaderno-recipes-v2"
        try:
            conversions = _export_exchange_conversions(request.space, foods, units, add_unit)
        except DomainError:
            return self.export_limit_response()
        payload["catalog"] = {"foods": list(foods.values()), "units": list(units.values()), "packages": packages,
                              "conversions": conversions}
        payload["source_space"] = request.space.pk
        payload["media"] = {"included": False, "method": "native-tandoor-zip", "url_downloads": False}
        payload["warnings"] = ["Este JSON incluye pasos, ingredientes, subrecetas, rendimientos y precios. "
                               "Para fotos, archivos, etiquetas y otros metadatos nativos utiliza también la exportación ZIP de Tandoor. "
                               "Incluye las conversiones de unidades alcanzables del catálogo. "
                               "Los alérgenos y ajustes fiscales del espacio no están incluidos."]
        try:
            validate_exchange_limits(payload)
        except DomainError:
            return self.export_limit_response()
        return HttpResponse(json.dumps(payload, ensure_ascii=False), content_type="application/json")

    @transaction.atomic
    def post(self, request):
        from cuaderno.domain.exchange import parse_portable_catalog
        try:
            recipes = parse_recipe_document(request.data)
            catalog = parse_portable_catalog(request.data, recipes)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        # One Space lock makes preview identities and concurrent imports
        # deterministic, including recipes within the same document.
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        document_digest = hashlib.sha256(json.dumps(request.data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if request.data.get("preview_sha256") and request.data["preview_sha256"] != hashlib.sha256(
            json.dumps({key: value for key, value in request.data.items() if key != "preview_sha256"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest():
            raise ImportConflict({"preview": "El documento ha cambiado desde la previsualización."})
        prepared = []
        seen = {}
        for item in recipes:
            payload = _exchange_item_payload(item)
            payload["mapping"] = request.data.get("mapping") or {}
            payload["catalog"] = request.data.get("catalog")
            digest = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            # Canonical default metadata did not exist before cookbook0243.
            # Preserve old replay identities only for semantically unchanged yields.
            legacy_payload = json.loads(json.dumps(payload))
            legacy_equivalent = True
            for ingredient in [*legacy_payload["ingredients"], *(row for step in legacy_payload["steps"] for row in step["ingredients"])]:
                if ingredient.get("quantity_basis") != "gross" or ingredient.get("yield_ratio") is not None:
                    legacy_equivalent = False
                    break
                ingredient.pop("quantity_basis", None)
                ingredient.pop("yield_ratio", None)
            legacy_digest = None
            if legacy_equivalent:
                legacy_digest = hashlib.sha256(
                    json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
            identity = (item["source"], item["external_id"])
            if identity in seen and seen[identity] != digest:
                raise ImportConflict({"external_id": "Identificador repetido con contenidos diferentes."})
            if identity in seen:
                continue
            seen[identity] = digest
            prior = RecipeExchangeRecord.objects.filter(
                space=request.space,
                source=item["source"],
                external_id=item["external_id"],
            ).select_related("recipe").first()
            if prior and prior.payload_sha256 not in {digest, legacy_digest}:
                raise ImportConflict({"external_id": "Ese identificador ya se importó con otro contenido."})
            if prior:
                from cuaderno.services.costing import visible_recipes
                if not visible_recipes(request.user, request.space).filter(pk=prior.recipe_id).exists():
                    raise PermissionDenied("Una receta importada no está disponible.")
            prepared.append((item, digest, prior))

        if request.query_params.get("preview") == "1":
            if catalog and any(prior is None for _, _, prior in prepared):
                _exchange_catalog_plan(request, catalog)
            return Response({"count": len(recipes), "preview": [_exchange_item_payload(item) for item in recipes],
                             "writes": 0, "preview_sha256": document_digest, "mapping_required": True,
                             "warnings": request.data.get("warnings", [])})

        created = []
        replayed = []
        imported = {}
        for item, digest, prior in prepared:
            if prior:
                replayed.append(prior.recipe_id)
                imported[item["external_id"]] = prior.recipe
                continue
            recipe = Recipe.objects.create(name=item["name"], description=item["description"], private=item["private"],
                                           servings=int(item["servings"]), created_by=request.user, space=request.space)
            imported[item["external_id"]] = recipe
            created.append(recipe.id)
        resolved = _exchange_catalog_apply(request, catalog, imported) if catalog and created else None
        for item, digest, prior in prepared:
            if prior:
                continue
            recipe = imported[item["external_id"]]
            for order, step_data in enumerate(item["steps"]):
                step = Step.objects.create(space=request.space, instruction=step_data["instruction"], name=step_data["name"], order=order,
                                           step_recipe=imported.get(step_data["step_recipe"]))
                for position, ingredient in enumerate(step_data["ingredients"]):
                    food = resolved["foods"].get(ingredient["food_ref"]) if resolved else _exchange_resolve(request, ingredient, "food", Food)
                    unit = resolved["units"].get(ingredient["unit_ref"]) if resolved else _exchange_resolve(request, ingredient, "unit", Unit)
                    try:
                        validate_yield_policy(ingredient["quantity_basis"], ingredient["yield_ratio"], is_subrecipe=bool(food and food.recipe_id))
                    except DomainError as exc:
                        raise ValidationError({exc.code: exc.message}) from exc
                    row = Ingredient.objects.create(food=food, unit=unit, amount=ingredient["quantity"], space=request.space,
                                                    order=position, note=ingredient["note"], original_text=ingredient["original_text"],
                                                    is_header=ingredient["is_header"], no_amount=ingredient["no_amount"],
                                                    quantity_basis=ingredient["quantity_basis"], yield_ratio=ingredient["yield_ratio"])
                    step.ingredients.add(row)
                recipe.steps.add(step)
            if item["yield"]:
                RecipeYield.objects.create(space=request.space, recipe=recipe, quantity=item["yield"]["quantity"],
                                           unit=resolved["units"][item["yield"]["unit_ref"]], updated_by=request.user)
            RecipeExchangeRecord.objects.create(
                space=request.space,
                source=item["source"],
                external_id=item["external_id"],
                payload_sha256=digest,
                recipe=recipe,
                created_by=request.user,
            )
        if created:
            from cuaderno.services.subrecipes import native_recipe_graph
            try:
                native_recipe_graph(created, request.space, request.user)
            except DomainError as exc:
                raise ValidationError({exc.code: "El grafo importado no es válido."}) from exc
        return Response({"created": created, "replayed": replayed, "rejected": []}, status=201)


class ImportConflict(APIException):
    status_code = 409
    default_code = "import_conflict"


def _exchange_item_payload(item: dict) -> dict:
    payload = {
        "source": item["source"],
        "external_id": item["external_id"],
        "name": item["name"],
        "description": item["description"],
        "private": item["private"],
        "servings": format(item["servings"], "f"),
        "ingredients": [
            {
                "food": ingredient["food"],
                "quantity": format(ingredient["quantity"], "f"),
                "quantity_basis": ingredient["quantity_basis"],
                "yield_ratio": None if ingredient["yield_ratio"] is None else _dec(ingredient["yield_ratio"]),
                "unit": ingredient["unit"],
                "food_id": ingredient["food_id"], "unit_id": ingredient["unit_id"],
                "note": ingredient["note"], "original_text": ingredient["original_text"],
                "is_header": ingredient["is_header"], "no_amount": ingredient["no_amount"],
            }
            for ingredient in item["ingredients"]
        ],
    }
    payload["steps"] = [
        {"name": step["name"], "instruction": step["instruction"], "step_recipe": step["step_recipe"], "ingredients": [
            {**ingredient, "quantity": format(ingredient["quantity"], "f"),
             "yield_ratio": None if ingredient["yield_ratio"] is None else _dec(ingredient["yield_ratio"])} for ingredient in step["ingredients"]
        ]} for step in item["steps"]
    ]
    payload["yield"] = {**item["yield"], "quantity": _dec(item["yield"]["quantity"])} if item["yield"] else None
    return payload


def _export_exchange_conversions(space, foods, units, add_unit):
    """Native conversion graph reachable from exported units, never hidden foods."""
    rows = list(UnitConversion.objects.filter(space=space).filter(
        Q(food__isnull=True) | Q(food_id__in=foods),
    ).select_related("base_unit", "converted_unit").order_by("pk")[:MAX_CATALOG_ITEMS + 1])
    # Bound candidates, not just the reachable result. Conservatively reject
    # oversized graphs instead of reading an unbounded disconnected catalog
    # or silently dropping conversions that change the native PK precedence.
    if len(rows) > MAX_CATALOG_ITEMS:
        raise DomainError("export_limit", "El catálogo de conversiones supera el límite seguro de exportación.")
    adjacency = {}
    for row in rows:
        adjacency.setdefault(row.base_unit_id, []).append(row)
        adjacency.setdefault(row.converted_unit_id, []).append(row)
    pending = list(units)
    visited = set()
    selected = {}
    for unit_id in pending:
        if unit_id in visited:
            continue
        visited.add(unit_id)
        for row in adjacency.get(unit_id, []):
            if row.pk in selected:
                continue
            if row.base_unit.space_id != space.pk or row.converted_unit.space_id != space.pk:
                raise ValidationError({"catalog": "Una conversión enlaza una unidad de otro espacio."})
            if not row.base_amount.is_finite() or not row.converted_amount.is_finite() or row.base_amount <= 0 or row.converted_amount <= 0:
                raise ValidationError({"catalog": "Revisa las cantidades positivas de las conversiones antes de exportar."})
            selected[row.pk] = {
                "ref": f"conversion:{row.pk}", "id": row.pk,
                "food_ref": f"food:{row.food_id}" if row.food_id else None,
                "base_unit_ref": add_unit(row.base_unit), "converted_unit_ref": add_unit(row.converted_unit),
                "base_amount": _dec(row.base_amount), "converted_amount": _dec(row.converted_amount),
            }
            pending.extend((row.base_unit_id, row.converted_unit_id))
    # Preserve native PK precedence used by the existing conversion BFS.
    return [selected[pk] for pk in sorted(selected)]


def _exchange_conversion_values(item, resolved):
    return {
        "food": resolved["foods"][item["food_ref"]] if item.get("food_ref") else None,
        "base_unit": resolved["units"][item["base_unit_ref"]],
        "converted_unit": resolved["units"][item["converted_unit_ref"]],
        "base_amount": item["base_amount"], "converted_amount": item["converted_amount"],
    }


def _exchange_catalog_plan(request, catalog):
    """Read-only resolution. A repeated name never establishes catalog identity."""
    from cuaderno.models import PackageFormat
    mapping = request.data.get("mapping") or {}
    if not isinstance(mapping, dict) or set(mapping) - {"foods", "units", "packages", "conversions"}:
        raise ValidationError({"mapping": "Mapping de catálogo inválido."})
    resolved = {"foods": {}, "units": {}, "packages": {}, "conversions": {}}
    for kind, model in (("units", Unit), ("foods", Food), ("packages", PackageFormat), ("conversions", UnitConversion)):
        if not isinstance(mapping.get(kind, {}), dict):
            raise ValidationError({"mapping": "El mapping debe contener objetos de identificadores."})
        if set(mapping.get(kind, {})) - (set(catalog[kind]) | {item.get("name", ref) for ref, item in catalog[kind].items()}):
            raise ValidationError({"mapping": "El mapping contiene identidades que no están en el catálogo."})
        seen_targets = set()
        new_names = set()
        for ref, item in catalog[kind].items():
            mapped = mapping.get(kind, {}).get(ref)
            if mapped is None:
                mapped = mapping.get(kind, {}).get(item.get("name", ref))
            if mapped is None and request.data.get("source_space") == request.space.pk:
                mapped = item.get("id")
            if mapped is not None:
                if isinstance(mapped, bool) or not isinstance(mapped, int) or mapped <= 0:
                    raise ValidationError({"mapping": "Los destinos del mapping deben ser identificadores enteros."})
                if mapped in seen_targets:
                    raise ValidationError({"mapping": "Dos identidades no pueden fusionarse implícitamente."})
                seen_targets.add(mapped)
                target = get_object_or_404(model, pk=mapped, space=request.space)
                if kind == "foods" and target.recipe_id:
                    from cuaderno.services.costing import visible_recipes
                    if not visible_recipes(request.user, request.space).filter(pk=target.recipe_id).exists():
                        raise PermissionDenied("Una referencia de alimento no está disponible.")
                if kind == "units" and any(getattr(target, field) != item.get(field) for field in ("name", "base_unit", "plural_name", "description")):
                    raise ImportConflict({"mapping": "La unidad elegida tiene datos diferentes."})
                resolved[kind][ref] = target
            elif kind in ("foods", "units") and model.objects.filter(space=request.space, name=item["name"]).exists():
                raise ValidationError({"mapping_required": f"Confirma el identificador de {kind}: {item['name']}."})
            else:
                if kind in ("foods", "units"):
                    if item["name"] in new_names:
                        raise ValidationError({"mapping_required": "El catálogo contiene nombres duplicados con identidades diferentes."})
                    new_names.add(item["name"])
                resolved[kind][ref] = None
    for ref, item in catalog["packages"].items():
        food = resolved["foods"][item["food_ref"]]
        unit = resolved["units"][item["unit_ref"]]
        package = resolved["packages"][ref]
        if package:
            values = {"food": food, "unit": unit, "quantity": item["quantity"], "label": item["label"], "is_reference": item["is_reference"]}
            if any(getattr(package, key) != value for key, value in values.items()):
                raise ImportConflict({"mapping": "El formato elegido tiene contenido diferente."})
            actual = list(package.prices.filter(space=request.space).order_by("valid_from", "id").values("amount", "explicit_free", "valid_from", "note"))
            if actual != item["prices"]:
                raise ImportConflict({"mapping": "El formato elegido tiene otro historial de precios."})
        if resolved["packages"][ref] is None and food and item["is_reference"] and PackageFormat.objects.filter(space=request.space, food=food, is_reference=True).exists():
            raise ValidationError({"mapping_required": "Confirma el formato de referencia existente."})
    for ref, item in catalog["conversions"].items():
        values = _exchange_conversion_values(item, resolved)
        conversion = resolved["conversions"][ref]
        if conversion is not None:
            if any(getattr(conversion, key) != value for key, value in values.items()):
                raise ImportConflict({"mapping": "La conversión elegida tiene unidades, alimento o proporción diferentes."})
        elif values["base_unit"] is not None and values["converted_unit"] is not None and (
            item.get("food_ref") is None or values["food"] is not None
        ):
            if UnitConversion.objects.filter(space=request.space, food=values["food"]).filter(
                Q(base_unit=values["base_unit"], converted_unit=values["converted_unit"])
                | Q(base_unit=values["converted_unit"], converted_unit=values["base_unit"])
            ).exists():
                raise ValidationError({"mapping_required": "Confirma la conversión existente entre estas unidades y alimento."})
    from cuaderno.domain.exchange_conversions import validate_conversion_precedence, validate_destination_conversion_graph
    try:
        validate_conversion_precedence(catalog["conversions"], resolved["conversions"])
        if catalog["conversions"] and any(unit is not None for unit in resolved["units"].values()):
            mapped_foods = [food.pk for food in resolved["foods"].values() if food is not None]
            destination_rows = UnitConversion.objects.filter(
                space=request.space, base_unit__space=request.space, converted_unit__space=request.space,
            ).filter(Q(food__isnull=True) | Q(food_id__in=mapped_foods)).values(
                "id", "food_id", "base_unit_id", "converted_unit_id",
            )[:10001]
            validate_destination_conversion_graph(
                catalog["conversions"], resolved["conversions"], resolved["units"], resolved["foods"], destination_rows,
            )
    except DomainError as exc:
        raise ImportConflict({exc.code: exc.message}) from exc
    return resolved


def _exchange_catalog_apply(request, catalog, imported):
    from cuaderno.models import PackageFormat, PriceVersion
    resolved = _exchange_catalog_plan(request, catalog)
    for ref, item in catalog["units"].items():
        values = {key: item.get(key) for key in ("name", "base_unit", "plural_name", "description")}
        unit = resolved["units"][ref]
        if unit is None:
            unit = Unit.objects.create(space=request.space, **values)
            resolved["units"][ref] = unit
        elif any(getattr(unit, key) != value for key, value in values.items()):
            raise ImportConflict({"mapping": "La unidad elegida tiene datos diferentes."})
    for ref, item in catalog["foods"].items():
        child = imported.get(item.get("recipe"))
        food = resolved["foods"][ref]
        if food is None:
            food = Food.add_root(space=request.space, name=item["name"], recipe=child)
            resolved["foods"][ref] = food
        elif food.recipe_id != (child.pk if child else None):
            raise ImportConflict({"mapping": "El alimento elegido apunta a otra subreceta."})
    for ref, item in catalog["packages"].items():
        values = {"food": resolved["foods"][item["food_ref"]], "unit": resolved["units"][item["unit_ref"]],
                  "quantity": item["quantity"], "label": item["label"], "is_reference": item["is_reference"]}
        package = resolved["packages"][ref]
        if package is None:
            package = PackageFormat.objects.create(space=request.space, **values)
            for price in item["prices"]:
                PriceVersion.objects.create(space=request.space, package=package, created_by=request.user, **price)
        else:
            if any(getattr(package, key) != value for key, value in values.items()):
                raise ImportConflict({"mapping": "El formato elegido tiene contenido diferente."})
            actual = list(package.prices.filter(space=request.space).order_by("valid_from", "id").values("amount", "explicit_free", "valid_from", "note"))
            if actual != item["prices"]:
                raise ImportConflict({"mapping": "El formato elegido tiene otro historial de precios."})
        resolved["packages"][ref] = package
    for ref, item in catalog["conversions"].items():
        if resolved["conversions"][ref] is None:
            resolved["conversions"][ref] = UnitConversion.objects.create(
                space=request.space, created_by=request.user, **_exchange_conversion_values(item, resolved),
            )
    return resolved


def _exchange_resolve(request, ingredient, field, model):
    name = ingredient[field]
    if not name:
        return None
    resolved = getattr(request, "_cuaderno_resolved", None)
    if resolved is None:
        resolved = request._cuaderno_resolved = {}
    if (field, name) in resolved:
        return resolved[(field, name)]
    mapping = request.data.get("mapping") or {}
    if not isinstance(mapping, dict) or not isinstance(mapping.get(field + "s", {}), dict):
        raise ValidationError({"mapping": "El mapping debe ser un objeto de identificadores."})
    mapped = mapping.get(field + "s", {}).get(name)
    if request.data.get("source_space") == request.space.pk:
        mapped = ingredient.get(field + "_id") or mapped
    if mapped is not None:
        if isinstance(mapped, bool) or not isinstance(mapped, int) or mapped <= 0:
            raise ValidationError({"mapping": "Los destinos del mapping deben ser identificadores enteros positivos."})
        result = get_object_or_404(model, pk=mapped, space=request.space)
        resolved[(field, name)] = result
        return result
    if model.objects.filter(name=name, space=request.space).exists():
        raise ValidationError({"mapping_required": f"Confirma el identificador de {field}: {name}."})
    if model is Food:
        result = Food.add_root(name=name, space=request.space)
    else:
        result = Unit.objects.create(name=name, space=request.space)
    resolved[(field, name)] = result
    return result
