"""Household boundary for native inventory; Space admins retain oversight."""
from cookbook.helper.permission_helper import has_group_permission


def household_inventory(request, queryset, path="inventory_location__household_id"):
    queryset = queryset.filter(space=request.space)
    if has_group_permission(request, ["admin"]):
        return queryset
    membership = getattr(request, "user_space", None)
    if membership is None or not membership.household_id:
        return queryset.none()
    return queryset.filter(**{path: membership.household_id})
