import json
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.models import Food, Ingredient, InventoryEntry, MealPlan, MealType, Recipe, Step, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.exchange import export_recipe_document, parse_recipe_document
from cuaderno.domain.margin import food_cost_gap
from cuaderno.domain.production import assert_no_cycle, consolidate, scale_covers
from cuaderno.domain.stock import packs_to_buy, waste_value
from cuaderno.models import AllergenDeclaration, PurchaseOrder, ServicePlan, SpaceProfile, StockMovement
from cuaderno.services.ledger import IdempotencyConflict, apply_movement, reverse_movement
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require(request.space, SpaceProfile.INTEGRAL)
        rows = StockMovement.objects.filter(space=request.space).select_related("entry").order_by("-id")[:100]
        return Response(
            [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "quantity": _dec(row.quantity),
                    "entry": row.entry_id,
                    "balance": _dec(row.entry.amount),
                    "reverses": row.reverses_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
        )

    def post(self, request):
        _require(request.space, SpaceProfile.INTEGRAL)
        try:
            if request.data.get("reverse_of"):
                movement = reverse_movement(
                    movement_id=request.data.get("reverse_of"),
                    space=request.space,
                    user=request.user,
                    idempotency_key=request.data.get("idempotency_key", ""),
                )
            else:
                entry = get_object_or_404(InventoryEntry, pk=request.data.get("entry"), space=request.space)
                movement = apply_movement(
                    entry_id=entry.id,
                    space=request.space,
                    user=request.user,
                    kind=request.data.get("kind"),
                    quantity=request.data.get("quantity"),
                    idempotency_key=request.data.get("idempotency_key", ""),
                )
        except IdempotencyConflict as exc:
            return Response(exc.detail, status=409)
        except StockMovement.DoesNotExist:
            raise ValidationError({"reverse_of": "Ese movimiento no está en este espacio."})
        movement.entry.refresh_from_db()
        return Response(
            {
                "movement_id": movement.id,
                "balance": _dec(movement.entry.amount),
                "kind": movement.kind,
                "reverses": movement.reverses_id,
            },
            status=201,
        )


class PurchaseOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        _require(request.space, SpaceProfile.INTEGRAL)
        food = get_object_or_404(Food, pk=request.data.get("food"), space=request.space)
        unit = get_object_or_404(Unit, pk=request.data.get("unit"), space=request.space)
        before = _balances(request.space)
        order = PurchaseOrder.objects.create(
            space=request.space,
            food=food,
            unit=unit,
            quantity=request.data.get("quantity"),
            supplier_name=request.data.get("supplier_name", ""),
            created_by=request.user,
        )
        after = _balances(request.space)
        return Response(
            {"id": order.id, "stock_unchanged": before == after, "quantity": _dec(order.quantity)},
            status=201,
        )


class ReplenishmentView(APIView):
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _require(request.space, SpaceProfile.PROFESIONAL)
        try:
            covers = scale_covers(request.data.get("base_covers", "0"), request.data.get("extra", "0"), request.data.get("cancelled", "0"))
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        before = _balances(request.space)
        meal_type, _ = MealType.objects.get_or_create(
            name="Servicio",
            space=request.space,
            defaults={"created_by": request.user, "default": False},
        )
        start = timezone.now()
        recipe = None
        if request.data.get("recipe"):
            recipe = get_object_or_404(Recipe, pk=request.data.get("recipe"), space=request.space)
        meal = MealPlan.objects.create(
            recipe=recipe,
            servings=covers.quantize(Decimal("0.0001")),
            title=(request.data.get("title") or "Servicio")[:64],
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
            title=request.data.get("title") or "Servicio",
            covers=covers,
            created_by=request.user,
        )
        after = _balances(request.space)
        return Response(
            {
                "id": plan.id,
                "covers": _dec(plan.covers),
                "meal_plan": meal.id,
                "payment": None,
                "stock_changed": before != after,
                "timezone": timezone.get_current_timezone_name(),
            },
            status=201,
        )


class ProductionSheetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _require(request.space, SpaceProfile.PROFESIONAL)
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
                linked = sheet_from_recipes(request.data.get("recipe_ids"), request.space)
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
            }
        )


class AllergenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _require(request.space, SpaceProfile.PROFESIONAL)
        food = get_object_or_404(Food, pk=request.data.get("food"), space=request.space)
        row = AllergenDeclaration.objects.create(
            space=request.space,
            food=food,
            name=request.data.get("name") or "",
            state=request.data.get("state") or AllergenDeclaration.UNKNOWN,
        )
        return Response(
            {"id": row.id, "state": row.state, "undeclared_means_absent": False},
            status=201,
        )


class RecipeExchangeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        recipes = []
        for recipe in Recipe.objects.filter(space=request.space, private=False):
            ingredients = []
            for step in recipe.steps.all():
                for ingredient in step.ingredients.all():
                    ingredients.append(
                        {
                            "food": ingredient.food.name if ingredient.food_id else "",
                            "quantity": _dec(ingredient.amount),
                            "unit": ingredient.unit.name if ingredient.unit_id else "",
                        }
                    )
            recipes.append({"name": recipe.name, "servings": str(recipe.servings), "ingredients": ingredients})
        payload = export_recipe_document(recipes)
        return HttpResponse(json.dumps(payload, ensure_ascii=False), content_type="application/json")

    @transaction.atomic
    def post(self, request):
        try:
            recipes = parse_recipe_document(request.data)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        created = []
        for item in recipes:
            recipe = Recipe.objects.create(name=item["name"], servings=int(item["servings"]), created_by=request.user, space=request.space)
            step = Step.objects.create(space=request.space, instruction="")
            for ingredient in item["ingredients"]:
                food = Food.objects.filter(name=ingredient["food"], space=request.space).first()
                if food is None:
                    food = Food.add_root(name=ingredient["food"], space=request.space)
                unit = None
                if ingredient["unit"]:
                    unit, _ = Unit.objects.get_or_create(name=ingredient["unit"], space=request.space)
                row = Ingredient.objects.create(food=food, unit=unit, amount=ingredient["quantity"], space=request.space)
                step.ingredients.add(row)
            recipe.steps.add(step)
            created.append(recipe.id)
        return Response({"created": created}, status=201)
