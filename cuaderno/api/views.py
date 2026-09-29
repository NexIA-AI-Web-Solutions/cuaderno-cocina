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
from cuaderno.api.prices import PackageWriteSerializer, PriceWriteSerializer, validate_free_flag


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
        rows = list(PackageFormat.objects.filter(space=request.space).order_by("pk").values(
            "id", "food_id", "food__name", "unit_id", "unit__name", "label", "quantity", "is_reference",
        ))
        latest_by_package = {
            price["package_id"]: {
                "id": price["id"], "amount": format(price["amount"], "f"),
                "explicit_free": price["explicit_free"], "valid_from": price["valid_from"].isoformat(),
            }
            for price in PriceVersion.objects.filter(
                space=request.space, package_id__in=[row["id"] for row in rows], valid_from__lte=timezone.now(),
            ).order_by("package_id", "-valid_from", "-id").distinct("package_id").values(
                "id", "package_id", "amount", "explicit_free", "valid_from",
            )
        }
        return Response([
            {
                "id": row["id"], "food": row["food_id"], "food_name": row["food__name"],
                "unit": row["unit_id"], "unit_name": row["unit__name"], "label": row["label"],
                "quantity": format(row["quantity"], "f"), "is_reference": row["is_reference"],
                "current_price": latest_by_package.get(row["id"]),
            }
            for row in rows
        ])

    @transaction.atomic
    def post(self, request):
        serializer = PackageWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        food = get_object_or_404(Food, pk=data["food"], space=request.space)
        unit = get_object_or_404(Unit, pk=data["unit"], space=request.space)
        type(request.space).objects.select_for_update().get(pk=request.space.pk)
        has_reference = PackageFormat.objects.filter(space=request.space, food=food, is_reference=True).exists()
        package = PackageFormat.objects.create(
            space=request.space,
            food=food,
            unit=unit,
            label=data["label"],
            quantity=data["quantity"],
            is_reference=not has_reference,
        )
        if data.get("price") is not None:
            _add_price(request, package, data["price"], data["explicit_free"])
        return Response(_package_payload(package), status=201)


class PriceCreateView(APIView):
    permission_classes = [CustomIsUser & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def post(self, request, pk):
        package = get_object_or_404(PackageFormat, pk=pk, space=request.space)
        serializer = PriceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        price = _add_price(request, package, data["amount"], data["explicit_free"])
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
    validate_free_flag(parsed, explicit_free)
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
