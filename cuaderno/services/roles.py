"""Spanish names for existing Space groups; never a replacement authorization."""

from cookbook.helper.permission_helper import has_group_permission


def operational_role(request):
    # Reuse the native request-bound snapshot already checked by EditionView.
    # A member may have several groups: resolve the highest native rank.
    for code, label in (("admin", "Responsable"), ("user", "Cocina"), ("guest", "Consulta")):
        if has_group_permission(request, [code]):
            return {
                "code": code,
                "label": label,
                "space": request.space.pk,
                "can_operate_cuaderno": code in ("admin", "user"),
                "can_manage_edition": code == "admin",
                "native_permissions_preserved": True,
            }
    return None
