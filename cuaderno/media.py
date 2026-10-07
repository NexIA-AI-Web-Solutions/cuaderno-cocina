"""Authorize local media against the same native objects as the application."""
from pathlib import PurePosixPath

from django.conf import settings
from django.db.models import F, Q
from django.http import Http404
from django.views.static import serve

from cookbook.models import Recipe, UserFile
from cuaderno.services.costing import visible_recipes


def can_download_user_file(user, space, uploaded):
    """Use the native recipe attachment ACL for every delivery route."""
    if not user.is_authenticated or uploaded.space_id != space.pk:
        return False
    references = Recipe.objects.filter(space=space, steps__file=uploaded)
    return (
        uploaded.created_by_id == user.pk
        or not references.exists()
        or visible_recipes(user, space).filter(steps__file=uploaded).exists()
    )


def authorized_media(request, path):
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or ".." in normalized.parts or "\\" in path or ":" in path:
        raise Http404
    path = normalized.as_posix()
    allowed = False
    if request.user.is_authenticated and getattr(request, "space", None):
        visible = visible_recipes(request.user, request.space)
        allowed = visible.filter(image=path).exists()
        if not allowed:
            allowed = visible.filter(cuaderno_gallery__space=request.space, cuaderno_gallery__image=path).exists()
        if not allowed:
            uploaded = UserFile.objects.filter(space=request.space, file=path).first()
            if uploaded:
                allowed = can_download_user_file(request.user, request.space, uploaded)
    if not allowed and request.GET.get("share"):
        from cookbook.helper.permission_helper import share_link_valid
        from django_scopes import scopes_disabled
        with scopes_disabled():
            candidates = Recipe.objects.filter(
                Q(image=path) | Q(steps__file__file=path)
                | Q(cuaderno_gallery__image=path, cuaderno_gallery__space_id=F("space_id")),
            ).distinct()
            allowed = any(share_link_valid(recipe, request.GET["share"]) for recipe in candidates)
    if not allowed:
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    # Files cannot run active HTML/SVG on the application's authenticated origin.
    if response.get("Content-Type", "").split(";")[0] not in {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}:
        response["Content-Disposition"] = "attachment"
    return response
