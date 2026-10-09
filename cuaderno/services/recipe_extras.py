"""Native recipe extras keep the root recipe's Space and visibility."""
from io import BytesIO
import warnings

from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError

from cookbook.helper.permission_helper import CustomRecipePermission, has_group_permission
from cuaderno.models import RecipeDietDeclaration, RecipeFavorite, RecipeGalleryImage, RecipeVariant
from cuaderno.services.costing import visible_recipes
from cuaderno.services.functional_access import revision
from cuaderno.services.planning_inputs import DIETS, DECLARATION


def recipe_for(request, recipe_id, *, write=False):
    recipe = get_object_or_404(visible_recipes(request.user, request.space), pk=recipe_id)
    if write and (not has_group_permission(request, ["user"])
                  or not CustomRecipePermission().has_object_permission(request, None, recipe)):
        raise PermissionDenied("No puedes modificar esta receta.")
    return recipe


def extras_payload(request, recipe):
    visible = visible_recipes(request.user, request.space)
    gallery = [{"id": row.pk, "url": row.image.url, "caption": row.caption, "position": row.position}
               for row in RecipeGalleryImage.objects.filter(space=request.space, recipe=recipe)]
    declarations = {row.slug: row for row in RecipeDietDeclaration.objects.filter(space=request.space, recipe=recipe)}
    diets = [{"slug": slug, "label": label, "status": declarations[slug].status if slug in declarations else "unknown",
              "note": declarations[slug].note if slug in declarations else "",
              "updated_at": declarations[slug].updated_at.isoformat() if slug in declarations else None}
             for slug, label in DIETS]
    link = RecipeVariant.objects.filter(space=request.space, recipe=recipe,
                                       source_recipe_id__in=visible.values("pk")).select_related("source_recipe").first()
    variant_of = {"id": link.source_recipe_id, "name": link.source_recipe.name} if link else None
    variants = list(RecipeVariant.objects.filter(space=request.space, source_recipe=recipe,
                                                 recipe_id__in=visible.values("pk"))
                    .order_by("recipe_id").values_list("recipe_id", "recipe__name")[:101])
    payload = {"recipe_id": recipe.pk, "gallery": gallery, "diets": diets, "variant_of": variant_of,
               "variants": [{"id": pk, "name": name} for pk, name in variants[:100]],
               "variants_truncated": len(variants) > 100, "declaration": DECLARATION}
    payload["revision"] = revision(payload)
    payload["can_edit"] = has_group_permission(request, ["user"])
    payload["is_favorite"] = RecipeFavorite.objects.filter(space=request.space, recipe=recipe, user=request.user).exists()
    return payload


def set_variant(request, recipe, source_id):
    if source_id is None:
        RecipeVariant.objects.filter(space=request.space, recipe=recipe).delete()
        return
    source = recipe_for(request, source_id)
    # Cycles and long lineage are rejected without exposing hidden ancestor IDs.
    seen = {recipe.pk}
    current = source
    for _ in range(32):
        if current.pk in seen:
            raise ValidationError({"variant_of": "La relación crearía un ciclo de variantes."})
        seen.add(current.pk)
        link = RecipeVariant.objects.filter(recipe=current).first()
        if link is None:
            break
        if link.space_id != request.space.pk:
            raise ValidationError({"variant_of": "No se puede vincular esa variante."})
        current = recipe_for(request, link.source_recipe_id)
    else:
        raise ValidationError({"variant_of": "La cadena de variantes es demasiado larga."})
    RecipeVariant.objects.update_or_create(space=request.space, recipe=recipe,
                                          defaults={"source_recipe": source, "created_by": request.user})


def validated_raster(upload):
    if upload is None or upload.size > 5 * 1024 * 1024 or upload.size <= 0:
        raise ValidationError({"image": "Selecciona una imagen de hasta 5 MiB."})
    raw = upload.read(5 * 1024 * 1024 + 1)
    if len(raw) != upload.size or len(raw) > 5 * 1024 * 1024:
        raise ValidationError({"image": "La imagen excede el límite permitido."})
    formats = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                extension = formats.get(image.format)
                if extension is None or image.width * image.height > 25000000 or image.width <= 0 or image.height <= 0:
                    raise ValueError
                # Single-frame images keep decompression work bounded. Re-encode
                # decoded pixels to strip appended active content and metadata.
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                image.load()
                output = BytesIO()
                # Apply phone/camera rotation before removing EXIF (including
                # location). Retain palette transparency, not other metadata.
                with ImageOps.exif_transpose(image) as normalized:
                    transparency = normalized.info.get("transparency")
                    normalized.info.clear()
                    if transparency is not None:
                        normalized.info["transparency"] = transparency
                    normalized.save(output, format=image.format)
                if output.tell() > 5 * 1024 * 1024:
                    raise ValueError
                return ContentFile(output.getvalue(), name="upload" + extension)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError({"image": "Usa una imagen JPEG, PNG, WebP o GIF de un solo fotograma y hasta 25 megapíxeles."}) from exc
