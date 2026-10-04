"""Strict read API for package history and recipe-local price impact."""

from __future__ import annotations

import re

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from cuaderno.api.base import CuadernoAPIView as APIView

from cookbook.helper.permission_helper import CustomRecipePermission, CustomTokenHasReadWriteScope
from cuaderno.api.prices import ExactDecimalField
from cuaderno.domain.errors import DomainError
from cuaderno.models import PackageFormat
from cuaderno.services.costing import visible_recipes
from cuaderno.services.price_history import price_history_payload, recipe_price_impact_payload
from cuaderno.services.visibility import visible_packages


_ASCII_POSITIVE_ID = re.compile(r"^[1-9][0-9]*$")
_ASCII_OFFSET = re.compile(r"^(?:0|[1-9][0-9]*)$")
_ASCII_DECIMAL_32_16 = re.compile(r"^[0-9]{1,16}(?:[.,][0-9]{1,16})?$")
_MAX_BIGINT = 9223372036854775807


class AsciiIntegerField(serializers.Field):
    default_error_messages = {"invalid": "Debe ser un entero ASCII dentro del rango permitido."}

    def __init__(self, *, allow_zero=False, maximum=_MAX_BIGINT, **kwargs):
        self.allow_zero = allow_zero
        self.maximum = maximum
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        pattern = _ASCII_OFFSET if self.allow_zero else _ASCII_POSITIVE_ID
        if pattern.fullmatch(data) is None:
            self.fail("invalid")
        if len(data) > len(str(self.maximum)):
            self.fail("invalid")
        value = int(data)
        if value > self.maximum:
            self.fail("invalid")
        return value


class QueryDecimalField(ExactDecimalField):
    """Exact positive decimal query input; scientific notation is not accepted."""

    def to_internal_value(self, data):
        if not isinstance(data, str) or _ASCII_DECIMAL_32_16.fullmatch(data) is None:
            self.fail("invalid")
        return super().to_internal_value(data)


class PriceHistoryQuerySerializer(serializers.Serializer):
    limit = AsciiIntegerField(maximum=100, default=20)
    offset = AsciiIntegerField(allow_zero=True, default=0)


class RecipePriceImpactQuerySerializer(serializers.Serializer):
    package = AsciiIntegerField()
    servings = QueryDecimalField()


def package_price_history_payload(request, package: PackageFormat) -> dict:
    """Adapter used by the existing package-price route's GET method."""
    # A QueryDict is treated as HTML form input by DRF: an explicit empty
    # value can become "missing" and silently receive the field default.
    # Preserve only keys the caller supplied in a plain mapping so ``?limit=``
    # and ``?offset=`` remain invalid while true absence still uses defaults.
    query_data = {
        key: request.query_params.get(key)
        for key in ("limit", "offset")
        if key in request.query_params
    }
    serializer = PriceHistoryQuerySerializer(data=query_data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    return price_history_payload(
        package,
        timezone.now(),
        limit=values["limit"],
        offset=values["offset"],
    )


class RecipePriceImpactView(APIView):
    permission_classes = [CustomRecipePermission & CustomTokenHasReadWriteScope]

    def get(self, request, recipe_id):
        # Resolve visibility and object permissions before parsing query data so
        # malformed parameters cannot disclose a private recipe's existence.
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)

        raw_servings = request.query_params.get("servings", str(recipe.servings or 1))
        serializer = RecipePriceImpactQuerySerializer(
            data={
                "package": request.query_params.get("package"),
                "servings": raw_servings,
            }
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        package = get_object_or_404(
            visible_packages(request.user, request.space),
            pk=values["package"],
        )
        as_of = timezone.now()
        try:
            payload = recipe_price_impact_payload(
                recipe,
                package,
                values["servings"],
                as_of,
                request.user,
            )
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        return Response(payload)
