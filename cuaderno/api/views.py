from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from cookbook.helper.permission_helper import CustomIsAdmin, CustomIsGuest, CustomIsUser, CustomRecipePermission, CustomTokenHasReadWriteScope
from cookbook.models import Food, Unit
from cuaderno.domain.errors import DomainError
from cuaderno.domain.money import parse_decimal
from cuaderno.models import PackageFormat, PriceVersion, SpaceProfile
from cuaderno.services.costing import cost_recipe, visible_recipes


def _profile(space) -> SpaceProfile:
    profile, _created = SpaceProfile.objects.get_or_create(space=space)
    return profile


class EditionView(APIView):
    permission_classes = [CustomIsGuest & CustomTokenHasReadWriteScope]

    def get_permissions(self):
        permission_classes = self.permission_classes
        if self.request.method == "PUT":
            permission_classes = [CustomIsAdmin & CustomTokenHasReadWriteScope]
        return [permission() for permission in permission_classes]

    def get(self, request):
        profile = _profile(request.space)
        return Response(
            {
                "edition": profile.edition,
                "currency": profile.currency,
                "price_policy": profile.price_policy,
                "target_food_cost_ratio": None if profile.target_food_cost_ratio is None else format(profile.target_food_cost_ratio, "f"),
                "prices_are_metadata": True,
                "net_profit": None,
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
        if "target_food_cost_ratio" in request.data:
            raw = request.data.get("target_food_cost_ratio")
            if raw in (None, ""):
                profile.target_food_cost_ratio = None
            else:
                try:
                    ratio = parse_decimal(raw, allow_zero=False)
                except DomainError as exc:
                    raise ValidationError({"target_food_cost_ratio": exc.message}) from exc
                if ratio > 1:
                    raise ValidationError({"target_food_cost_ratio": "El objetivo de coste de materia es una fracción entre 0 y 1."})
                profile.target_food_cost_ratio = ratio
        profile.save(update_fields=["edition", "price_policy", "target_food_cost_ratio"])
        return Response(
            {
                "edition": profile.edition,
                "currency": profile.currency,
                "price_policy": profile.price_policy,
                "target_food_cost_ratio": None if profile.target_food_cost_ratio is None else format(profile.target_food_cost_ratio, "f"),
                "net_profit": None,
            }
        )


class PackageListView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    def get(self, request):
        rows = list(PackageFormat.objects.filter(space=request.space).select_related("food", "unit").order_by("pk"))
        latest_by_package = {
            price.package_id: price
            for price in PriceVersion.objects.filter(
                space=request.space, package_id__in=[row.pk for row in rows], valid_from__lte=timezone.now(),
            ).order_by("package_id", "-valid_from", "-id").distinct("package_id")
        }
        return Response([_package_payload(row, latest_by_package.get(row.pk)) for row in rows])

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
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def post(self, request, pk):
        package = get_object_or_404(PackageFormat, pk=pk, space=request.space)
        price = _add_price(request, package, request.data.get("amount"), bool(request.data.get("explicit_free")))
        return Response(_price_payload(price), status=201)


class RecipeCostView(APIView):
    permission_classes = [CustomRecipePermission & CustomTokenHasReadWriteScope]

    def get(self, request, recipe_id):
        recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
        self.check_object_permissions(request, recipe)
        servings = request.query_params.get("servings", recipe.servings or 1)
        try:
            payload = cost_recipe(recipe, servings, user=request.user)
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


_UNSET_PRICE = object()


def _package_payload(package: PackageFormat, latest=_UNSET_PRICE) -> dict:
    if latest is _UNSET_PRICE:
        latest = package.prices.filter(valid_from__lte=timezone.now()).order_by("-valid_from", "-id").first()
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
