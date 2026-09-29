"""Edit yield metadata on native Ingredient rows, scoped through their recipe."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.helper.permission_helper import CustomRecipePermission, CustomTokenHasReadWriteScope, has_group_permission
from cookbook.models import Ingredient, Recipe
from cuaderno.api.operations import _require
from cuaderno.api.prices import JsonIdentifierField
from cuaderno.api.yield_fields import IngredientYieldValidationMixin, YieldRatioField
from cuaderno.domain.errors import DomainError
from cuaderno.domain.ingredient_yields import validate_yield_policy
from cuaderno.models import SpaceProfile
from cuaderno.services.costing import visible_recipes


class IngredientYieldWriteSerializer(IngredientYieldValidationMixin, serializers.Serializer):
    ingredient = JsonIdentifierField()
    quantity_basis = serializers.ChoiceField(choices=("gross", "net_usable"))
    yield_ratio = YieldRatioField(allow_null=True)


class IngredientYieldView(APIView):
    permission_classes = [CustomRecipePermission & CustomTokenHasReadWriteScope]

    def recipe(self, request, recipe_id):
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)
        return recipe

    @staticmethod
    def payload(request, recipe):
        profile, _ = SpaceProfile.objects.get_or_create(space=request.space)
        ingredients = Ingredient.objects.filter(space=request.space, step__recipe=recipe).select_related("food", "unit").distinct().order_by("order", "pk")
        return Response({
            "recipe_id": recipe.pk, "edition": profile.edition,
            "can_edit": profile.edition in {SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL} and has_group_permission(request, ["user"]),
            "ingredients": [{
                "id": row.pk, "food_name": row.food.name if row.food_id else None,
                "amount": format(row.amount, "f"), "unit": row.unit.name if row.unit_id else None,
                "quantity_basis": row.quantity_basis,
                "yield_ratio": None if row.yield_ratio is None else format(row.yield_ratio, "f"),
                "is_subrecipe": bool(row.food_id and row.food.recipe_id),
            } for row in ingredients],
        })

    def get(self, request, recipe_id):
        return self.payload(request, self.recipe(request, recipe_id))

    @transaction.atomic
    def put(self, request, recipe_id):
        recipe = self.recipe(request, recipe_id)
        _require(request.space, SpaceProfile.PROFESIONAL)
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        serializer = IngredientYieldWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ingredient = get_object_or_404(
            Ingredient.objects.filter(space=request.space, step__recipe=recipe).distinct(), pk=data["ingredient"],
        )
        if Recipe.objects.filter(steps__ingredients=ingredient).exclude(pk=recipe.pk).exists():
            raise ValidationError({"ingredient": "La línea se comparte entre recetas; duplica la línea antes de cambiar su merma."})
        try:
            validate_yield_policy(data["quantity_basis"], data["yield_ratio"], is_subrecipe=bool(ingredient.food_id and ingredient.food.recipe_id))
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        ingredient.quantity_basis = data["quantity_basis"]
        ingredient.yield_ratio = data["yield_ratio"]
        ingredient.save(update_fields=["quantity_basis", "yield_ratio"])
        return self.payload(request, recipe)
