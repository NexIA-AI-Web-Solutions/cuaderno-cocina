"""Finance metadata extends native recipe properties, never invents profit."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.helper.permission_helper import CustomRecipePermission, CustomTokenHasReadWriteScope
from cuaderno.api.operations import _require
from cuaderno.domain.errors import DomainError
from cuaderno.models import SpaceProfile
from cuaderno.services.costing import cost_recipe, visible_recipes
from cuaderno.services.recipe_finance import read_recipe_finance, write_recipe_finance


FinanceValuesSchema = inline_serializer(
    name="CuadernoRecipeFinanceValues",
    fields={
        key: serializers.CharField(allow_null=True)
        for key in (
            "selling_price_per_serving", "budget_per_person", "ingredient_cost_per_serving",
            "difference_per_serving", "food_cost_ratio", "budget_gap_per_person", "price_policy",
            "net_profit",
        )
    } | {
        "status": serializers.CharField(),
        "warnings": serializers.ListField(child=serializers.CharField()),
    },
)
FinanceResponseSchema = inline_serializer(
    name="CuadernoRecipeFinanceResponse",
    fields={"edition": serializers.CharField(), "finance": FinanceValuesSchema},
)
FinanceWriteSchema = inline_serializer(
    name="CuadernoRecipeFinanceWrite",
    fields={key: serializers.CharField(required=False, allow_null=True) for key in (
        "selling_price_per_serving", "budget_per_person",
    )},
)
_SERVINGS_PARAMETER = OpenApiParameter("servings", str, description="Raciones objetivo, sin guardar la receta.")


class RecipeFinanceView(APIView):
    permission_classes = [CustomRecipePermission & CustomTokenHasReadWriteScope]

    @extend_schema(parameters=[_SERVINGS_PARAMETER], responses=FinanceResponseSchema)
    def get(self, request, recipe_id):
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)
        profile, _ = SpaceProfile.objects.get_or_create(space=request.space)
        return self.payload(request, recipe, profile)

    @extend_schema(parameters=[_SERVINGS_PARAMETER], request=FinanceWriteSchema, responses=FinanceResponseSchema)
    @transaction.atomic
    def put(self, request, recipe_id):
        profile = _require(request.space, SpaceProfile.PROFESIONAL)
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)
        allowed = {"selling_price_per_serving", "budget_per_person"}
        if not isinstance(request.data, dict) or set(request.data) - allowed:
            raise ValidationError({"finance": "Envía solo precio de venta por ración y presupuesto por persona."})
        try:
            write_recipe_finance(recipe, request.data, request.user)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        return self.payload(request, recipe, profile)

    @staticmethod
    def payload(request, recipe, profile):
        try:
            cost = cost_recipe(recipe, request.query_params.get("servings", recipe.servings or 1), user=request.user)
            finance = read_recipe_finance(recipe, cost, profile)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        return Response({"edition": profile.edition, "finance": finance})
