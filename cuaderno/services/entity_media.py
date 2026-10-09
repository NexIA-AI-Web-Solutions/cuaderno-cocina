"""Bounded image metadata and authorized delivery for native Food and templates."""
import re
import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from cookbook.helper.permission_helper import has_group_permission
from cuaderno.models import FoodImage, MenuTemplateImage
from cuaderno.services.visibility import visible_foods

IMAGE_NAME = re.compile(r"cuaderno/entity-media/[a-f0-9]{32}\.(jpg|png|webp|gif)")
CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


def entity_for(request, kind, pk, *, write=False):
    if not has_group_permission(request, ["user" if write else "guest"], no_cache=True):
        raise PermissionDenied("No puedes modificar esta imagen." if write else "No tienes acceso a esta imagen.")
    if kind == "food":
        parent = get_object_or_404(visible_foods(request.user, request.space), pk=pk)
    else:
        from cuaderno.services.planning import require_professional, visible_templates
        require_professional(request.space)
        parent = get_object_or_404(visible_templates(request), pk=pk)
    # An incoherent imported one-to-one relation cannot be overwritten by
    # treating it as an absent image; neither its file nor metadata is exposed.
    if write and image_model(kind).objects.filter(**{kind: parent}).exclude(space=request.space).exists():
        raise NotFound("La imagen no está disponible.")
    return parent


def image_model(kind):
    return FoodImage if kind == "food" else MenuTemplateImage


def image_row(kind, parent):
    return image_model(kind).objects.filter(space_id=parent.space_id, **{kind: parent}).first()


def image_payload(kind, parent):
    row = image_row(kind, parent)
    if row is None or not row.image or not IMAGE_NAME.fullmatch(row.image.name):
        return None
    version = hashlib.sha256(row.image.name.encode()).hexdigest()[:16]
    url = reverse(f"cuaderno-{kind}-image-content", kwargs={f"{kind}_id": parent.pk})
    return {"url": f"{url}?v={version}", "caption": row.caption}


def media_payload(request, kind, parent):
    payload = {"image": image_payload(kind, parent), "can_edit": has_group_permission(request, ["user"])}
    if kind == "template":
        from cuaderno.services.planning import template_payload
        payload["revision"] = template_payload(parent)["revision"]
    return payload


def image_response(kind, parent):
    row = image_row(kind, parent)
    if row is None or not row.image:
        raise NotFound("La imagen no está disponible.")
    match = IMAGE_NAME.fullmatch(row.image.name)
    if match is None:
        raise NotFound("La imagen no está disponible.")
    extension = match.group(1)
    source = None
    try:
        # This fixed namespace and decoded UUID filename belong to our own
        # upload path. No caller controls an arbitrary storage lookup.
        if not 0 < row.image.size <= 5 * 1024 * 1024:
            raise NotFound("La imagen no está disponible.")
        source = row.image.open("rb")
        response = FileResponse(source, content_type=CONTENT_TYPES[extension],
                                filename=f"{kind}-{parent.pk}.{extension}", as_attachment=False)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except (OSError, ValueError) as exc:
        if source is not None:
            source.close()
        raise NotFound("La imagen no está disponible.") from exc
    except Exception:
        if source is not None:
            source.close()
        raise


def delete_unreferenced_file(storage, name, using="default"):
    """Remove only this extension's own unreferenced file after a DB commit."""
    if not name or not IMAGE_NAME.fullmatch(name):
        return
    from cookbook.models import Recipe, UserFile
    from cuaderno.models import RecipeGalleryImage
    if (FoodImage._base_manager.using(using).filter(image=name).exists()
            or MenuTemplateImage._base_manager.using(using).filter(image=name).exists()
            or RecipeGalleryImage._base_manager.using(using).filter(image=name).exists()
            or Recipe._base_manager.using(using).filter(image=name).exists()
            or UserFile._base_manager.using(using).filter(file=name).exists()):
        return
    storage.delete(name)


def optimized_raster(upload):
    """Keep decoded uploads useful for display and bounded for browser exports."""
    try:
        with Image.open(upload) as image:
            image_format = image.format
            image.load()
            image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            transparency = image.info.get("transparency")
            image.info.clear()
            if transparency is not None:
                image.info["transparency"] = transparency
            output = BytesIO()
            image.save(output, format=image_format)
            if output.tell() > 5 * 1024 * 1024:
                raise ValidationError({"image": "La imagen optimizada excede el límite de 5 MiB."})
            return ContentFile(output.getvalue(), name=upload.name)
    finally:
        upload.close()
