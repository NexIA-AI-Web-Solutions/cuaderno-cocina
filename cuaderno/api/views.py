from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.helper.permission_helper import CustomRecipePermission
from cookbook.models import Food, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
from cuaderno.services.costing import cost_recipe, visible_recipes


def _profile(space) -> SpaceProfile:
    profile, _created = SpaceProfile.objects.get_or_create(space=space)
    return profile


class EditionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _profile(request.space)
        return Response(
            {
                "edition": profile.edition,
                "currency": profile.currency,
                "price_policy": profile.price_policy,
                "prices_are_metadata": True,
            }
        )

    def put(self, request):
        profile = _profile(request.space)
        edition = request.data.get("edition", profile.edition)
        policy = request.data.get("price_policy", profile.price_policy)
        if edition not in dict(SpaceProfile.EDITIONS):
            raise ValidationError({"edition": "Edición desconocida."})
        if policy not in dict(SpaceProfile.POLICIES):
            raise ValidationError({"price_policy": "Política de precio desconocida. Elige neto o bruto."})
        profile.edition = edition
        profile.price_policy = policy
        profile.save(update_fields=["edition", "price_policy"])
        return Response({"edition": profile.edition, "currency": profile.currency, "price_policy": profile.price_policy})


class PackageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = PackageFormat.objects.filter(space=request.space).select_related("food", "unit")
        return Response([_package_payload(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        food = get_object_or_404(Food, pk=request.data.get("food"), space=request.space)
        unit = get_object_or_404(Unit, pk=request.data.get("unit"), space=request.space)
        try:
            quantity = parse_decimal(request.data.get("quantity"), allow_zero=False)
        except DomainError as exc:
            raise ValidationError({"quantity": exc.message}) from exc
        label = (request.data.get("label") or "").strip()
        if not label:
            raise ValidationError({"label": "Indica el formato de compra."})
        has_reference = PackageFormat.objects.filter(space=request.space, food=food, is_reference=True).exists()
        package = PackageFormat.objects.create(
            space=request.space,
            food=food,
            unit=unit,
            label=label,
            quantity=quantity,
            is_reference=not has_reference,
        )
        if "price" in request.data and request.data.get("price") is not None:
            _add_price(request, package, request.data.get("price"), bool(request.data.get("explicit_free")))
        return Response(_package_payload(package), status=201)


class PriceCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        package = get_object_or_404(PackageFormat, pk=pk, space=request.space)
        price = _add_price(request, package, request.data.get("amount"), bool(request.data.get("explicit_free")))
        return Response(_price_payload(price), status=201)


class RecipeCostView(APIView):
    permission_classes = [IsAuthenticated, CustomRecipePermission]

    def get(self, request, recipe_id):
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)
        servings = request.query_params.get("servings", recipe.servings or 1)
        try:
            payload = cost_recipe(recipe, servings)
        except DomainError as exc:
            raise ValidationError({exc.code: exc.message}) from exc
        payload["currency"] = _profile(request.space).currency
        payload["recipe_id"] = recipe.id
        payload["saved_recipe"] = False
        return Response(payload)


def _add_price(request, package, amount, explicit_free: bool) -> PriceVersion:
    try:
        parsed = parse_decimal(amount, allow_zero=explicit_free)
    except DomainError as exc:
        raise ValidationError({"amount": exc.message}) from exc
    if parsed == 0 and not explicit_free:
        raise ValidationError({"amount": "Un precio cero solo vale si marcas el ingrediente como gratuito."})
    return PriceVersion.objects.create(
        space=request.space,
        package=package,
        amount=parsed,
        explicit_free=explicit_free,
        valid_from=timezone.now(),
        created_by=request.user,
    )


def _price_payload(price: PriceVersion) -> dict:
    return {
        "id": price.id,
        "amount": format(price.amount, "f"),
        "explicit_free": price.explicit_free,
        "valid_from": price.valid_from.isoformat(),
    }


def _package_payload(package: PackageFormat) -> dict:
    latest = package.prices.order_by("-valid_from", "-id").first()
    return {
        "id": package.id,
        "food": package.food_id,
        "food_name": package.food.name,
        "unit": package.unit_id,
        "unit_name": package.unit.name,
        "label": package.label,
        "quantity": format(package.quantity, "f"),
        "is_reference": package.is_reference,
        "current_price": None if latest is None else _price_payload(latest),
    }
