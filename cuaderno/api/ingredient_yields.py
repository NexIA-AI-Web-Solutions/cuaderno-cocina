"""Edit yield metadata on native Ingredient rows, scoped through their recipe."""
import hashlib
import json
import re
from collections.abc import Mapping

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from cuaderno.services.profiles import profile_for_space
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from cuaderno.api.base import CuadernoAPIView as APIView

from cookbook.helper.permission_helper import (
    CustomRecipePermission,
    CustomTokenHasReadWriteScope,
    has_group_permission,
)
from cookbook.models import Ingredient, Recipe, Space
from cuaderno.api.operations import _require
from cuaderno.api.prices import JsonIdentifierField
from cuaderno.api.yield_fields import IngredientYieldValidationMixin, YieldRatioField
from cuaderno.domain.errors import DomainError
from cuaderno.domain.ingredient_yields import validate_yield_policy
from cuaderno.models import SpaceProfile
from cuaderno.services.costing import visible_recipes


class RevisionField(serializers.CharField):
    default_error_messages = {"invalid": "La revisión debe ser un SHA-256 hexadecimal de 64 caracteres."}

    def to_internal_value(self, data):
        if type(data) is not str or re.fullmatch(r"[0-9a-f]{64}", data) is None:
            self.fail("invalid")
        return data


class IngredientYieldWriteSerializer(IngredientYieldValidationMixin, serializers.Serializer):
    ingredient = JsonIdentifierField()
    quantity_basis = serializers.ChoiceField(choices=("gross", "net_usable"))
    yield_ratio = YieldRatioField(allow_null=True)
    revision = RevisionField()


class YieldRevisionRequired(APIException):
    status_code = 428
    default_detail = "Incluye la revisión obtenida al leer las mermas."
    default_code = "yield_revision_required"


class YieldRevisionConflict(APIException):
    status_code = 409
    default_detail = "Las mermas han cambiado; vuelve a cargarlas antes de guardar."
    default_code = "yield_revision_conflict"


def _canonical_decimal(value):
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _ingredient_rows(recipe, *, lock=False):
    ingredient_ids = Ingredient.objects.filter(
        space_id=recipe.space_id, step__recipe=recipe,
    ).values_list("pk", flat=True).distinct()
    rows = Ingredient.objects.filter(space_id=recipe.space_id, pk__in=ingredient_ids)
    if lock:
        rows = rows.select_for_update(of=("self",))
    return list(rows.select_related("food", "unit").order_by("order", "pk"))


def _recipe_log_revision(recipe):
    content_type = ContentType.objects.get_for_model(Recipe)
    return (
        LogEntry.objects.filter(content_type=content_type, object_id=str(recipe.pk))
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )


def _yield_revision(recipe, ingredients):
    envelope = {
        "recipe_id": recipe.pk,
        "recipe_updated_at": recipe.updated_at.isoformat(),
        "latest_recipe_log": _recipe_log_revision(recipe),
        "ingredients": [
            {
                "id": row.pk,
                "amount": _canonical_decimal(row.amount),
                "unit_id": row.unit_id,
                "food_id": row.food_id,
                "child_recipe_id": row.food.recipe_id if row.food_id else None,
                "quantity_basis": row.quantity_basis,
                "yield_ratio": _canonical_decimal(row.yield_ratio),
                "order": row.order,
            }
            for row in ingredients
        ],
    }
    encoded = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IngredientYieldView(APIView):
    permission_classes = [CustomRecipePermission & CustomTokenHasReadWriteScope]

    def locked_recipe(self, request, recipe_id):
        Space._base_manager.select_for_update().get(pk=request.space.pk)
        recipe = get_object_or_404(
            Recipe._base_manager.select_for_update(),
            pk=recipe_id,
            space_id=request.space.pk,
        )
        if not visible_recipes(request.user, request.space).filter(pk=recipe.pk).exists():
            raise Http404
        self.check_object_permissions(request, recipe)
        return recipe

    @staticmethod
    def payload(request, recipe, ingredients=None):
        profile = profile_for_space(request.space)
        ingredients = _ingredient_rows(recipe, lock=True) if ingredients is None else ingredients
        return Response({
            "recipe_id": recipe.pk,
            "edition": profile.edition,
            "revision": _yield_revision(recipe, ingredients),
            "can_edit": (
                profile.edition in {SpaceProfile.PROFESIONAL, SpaceProfile.INTEGRAL}
                and has_group_permission(request, ["user"])
            ),
            "ingredients": [{
                "id": row.pk, "food_name": row.food.name if row.food_id else None,
                "amount": format(row.amount, "f"), "unit": row.unit.name if row.unit_id else None,
                "quantity_basis": row.quantity_basis,
                "yield_ratio": None if row.yield_ratio is None else format(row.yield_ratio, "f"),
                "is_subrecipe": bool(row.food_id and row.food.recipe_id),
            } for row in ingredients],
        })

    @transaction.atomic
    def get(self, request, recipe_id):
        recipe = self.locked_recipe(request, recipe_id)
        return self.payload(request, recipe, _ingredient_rows(recipe, lock=True))

    @transaction.atomic
    def put(self, request, recipe_id):
        recipe = self.locked_recipe(request, recipe_id)
        _require(request.space, SpaceProfile.PROFESIONAL)
        if not isinstance(request.data, Mapping):
            raise ValidationError({"yield": "El cuerpo debe ser un objeto JSON."})
        if "revision" not in request.data:
            raise YieldRevisionRequired({"revision": YieldRevisionRequired.default_detail})
        serializer = IngredientYieldWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ingredients = _ingredient_rows(recipe, lock=True)
        if data["revision"] != _yield_revision(recipe, ingredients):
            raise YieldRevisionConflict({"revision": YieldRevisionConflict.default_detail})
        ingredient = next((row for row in ingredients if row.pk == data["ingredient"]), None)
        if ingredient is None:
            raise Http404
        if Recipe.objects.filter(steps__ingredients=ingredient).exclude(pk=recipe.pk).exists():
            raise ValidationError({
                "ingredient": "La línea se comparte entre recetas; duplica la línea antes de cambiar su merma.",
            })
        try:
            validate_yield_policy(
                data["quantity_basis"],
                data["yield_ratio"],
                is_subrecipe=bool(ingredient.food_id and ingredient.food.recipe_id),
            )
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        before = {
            "quantity_basis": ingredient.quantity_basis,
            "yield_ratio": _canonical_decimal(ingredient.yield_ratio),
        }
        after = {
            "quantity_basis": data["quantity_basis"],
            "yield_ratio": _canonical_decimal(data["yield_ratio"]),
        }
        if before == after:
            return self.payload(request, recipe, ingredients)
        ingredient.quantity_basis = data["quantity_basis"]
        ingredient.yield_ratio = data["yield_ratio"]
        ingredient.save(update_fields=["quantity_basis", "yield_ratio"])
        recipe.updated_at = timezone.now()
        recipe.save(update_fields=["updated_at"])
        changed_fields = [key for key in before if before[key] != after[key]]
        LogEntry.objects.create(
            user_id=request.user.pk,
            content_type=ContentType.objects.get_for_model(Recipe),
            object_id=str(recipe.pk),
            object_repr=str(recipe)[:200],
            action_flag=CHANGE,
            change_message=json.dumps([{"changed": {
                "fields": changed_fields,
                "ingredient_id": ingredient.pk,
                "before": before,
                "after": after,
            }}], ensure_ascii=False, separators=(",", ":")),
        )
        return self.payload(request, recipe, _ingredient_rows(recipe, lock=True))
