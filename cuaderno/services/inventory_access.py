"""Household boundary for native inventory; Space admins retain oversight."""
from cookbook.helper.permission_helper import has_group_permission
from django.db.models import Q

from cuaderno.services.visibility import visible_foods


def household_inventory(request, queryset, path="inventory_location__household_id"):
    queryset = queryset.filter(space=request.space)
    if path == "household_id":
        queryset = queryset.filter(household__space=request.space)
    else:
        prefix = path.removesuffix("inventory_location__household_id")
        # Native entries can have a missing Food/Unit. Preserve that legacy
        # state, but never resolve a private or cross-Space foreign key.
        queryset = queryset.filter(
            Q(**{f"{prefix}food_id__isnull": True})
            | Q(**{f"{prefix}food_id__in": visible_foods(request.user, request.space).values("pk")}),
            Q(**{f"{prefix}unit_id__isnull": True}) | Q(**{f"{prefix}unit__space": request.space}),
            **{f"{prefix}inventory_location__space": request.space,
               f"{prefix}inventory_location__household__space": request.space},
        )
        if prefix:
            queryset = queryset.filter(**{f"{prefix}space": request.space})
    if has_group_permission(request, ["admin"]):
        return queryset
    membership = getattr(request, "user_space", None)
    if membership is None or not membership.household_id:
        return queryset.none()
    return queryset.filter(**{path: membership.household_id})
