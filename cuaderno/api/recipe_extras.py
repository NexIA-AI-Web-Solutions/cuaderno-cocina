"""Small native recipe extensions; sharing never grants edit permission."""
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from cookbook.helper.permission_helper import CustomIsGuest, CustomTokenHasReadWriteScope
from cuaderno.api.base import CuadernoAPIView, CuadernoIsOperator
from cuaderno.models import RecipeDietDeclaration, RecipeFavorite, RecipeGalleryImage
from cuaderno.services.costing import visible_recipes
from cuaderno.services.functional_access import checked, lock_space, page_window, require_revision
from cuaderno.services.planning_inputs import diet_rows, fields, integer, text
from cuaderno.services.recipe_extras import extras_payload, recipe_for, set_variant, validated_raster


class RecipeExtrasView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]

    def get(self, request, recipe_id):
        return Response(extras_payload(request, recipe_for(request, recipe_id)))

    @transaction.atomic
    def put(self, request, recipe_id):
        checked(fields, request.data, ("revision", "diets", "variant_of"))
        lock_space(request)
        recipe = recipe_for(request, recipe_id, write=True)
        require_revision(request.data, extras_payload(request, recipe)["revision"])
        if "diets" in request.data:
            for row in checked(diet_rows, request.data["diets"]):
                RecipeDietDeclaration.objects.update_or_create(
                    space=request.space, recipe=recipe, slug=row["slug"],
                    defaults={"status": row["status"], "note": row["note"], "updated_by": request.user},
                )
        if "variant_of" in request.data:
            set_variant(request, recipe, checked(integer, request.data["variant_of"], nullable=True))
        return Response(extras_payload(request, recipe))


class RecipeFavoriteView(CuadernoAPIView):
    # Deliberately separate from recipe mutation: Consulta may toggle only its own favorite.
    permission_classes = [CustomIsGuest & CustomTokenHasReadWriteScope]

    @transaction.atomic
    def put(self, request, recipe_id):
        checked(fields, request.data, ("favorite",), ("favorite",))
        if type(request.data["favorite"]) is not bool:
            raise ValidationError({"favorite": "Indica verdadero o falso."})
        lock_space(request)
        recipe = recipe_for(request, recipe_id)
        query = {"space": request.space, "recipe": recipe, "user": request.user}
        if request.data["favorite"]:
            RecipeFavorite.objects.get_or_create(**query)
        else:
            RecipeFavorite.objects.filter(**query).delete()
        return Response({"recipe_id": recipe.pk, "is_favorite": request.data["favorite"]})


class FavoriteListView(CuadernoAPIView):
    permission_classes = [CustomIsGuest & CustomTokenHasReadWriteScope]

    def get(self, request):
        offset, limit = page_window(request)
        rows = visible_recipes(request.user, request.space).filter(
            cuaderno_favorites__space=request.space, cuaderno_favorites__user=request.user,
        ).order_by("name", "pk")
        return Response({"count": rows.count(), "results": [
            {"id": row.pk, "name": row.name, "image": row.image.url if row.image else None}
            for row in rows[offset:offset + limit]
        ]})


class RecipeGalleryView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]
    http_method_names = ["post", "options"]

    def post(self, request, recipe_id):
        if set(request.data) - {"image", "caption"}:
            raise ValidationError({"image": "Envía imagen y texto de la foto."})
        if len(request.FILES.getlist("image")) != 1:
            raise ValidationError({"image": "Envía una sola imagen por petición."})
        # Reject authorization before decoding user-controlled image data.
        recipe_for(request, recipe_id, write=True)
        upload = validated_raster(request.FILES.get("image"))
        caption = checked(text, request.data.get("caption", ""), 256, empty=True)
        row = None
        try:
            with transaction.atomic():
                lock_space(request)
                recipe = recipe_for(request, recipe_id, write=True)
                current = list(RecipeGalleryImage.objects.filter(space=request.space, recipe=recipe))
                if len(current) >= 20:
                    raise ValidationError({"image": "La galería admite hasta 20 fotos."})
                position = next(i for i in range(20) if i not in {x.position for x in current})
                row = RecipeGalleryImage(space=request.space, recipe=recipe, caption=caption,
                                         position=position, created_by=request.user)
                row.image.save(upload.name, upload, save=False)
                row.save()
                payload = extras_payload(request, recipe)
            return Response(payload, status=201)
        except Exception:
            if row is not None and row.image.name:
                row.image.storage.delete(row.image.name)
            raise

    @transaction.atomic
    def delete(self, request, recipe_id, image_id):
        from django.shortcuts import get_object_or_404
        lock_space(request)
        recipe = recipe_for(request, recipe_id, write=True)
        row = get_object_or_404(RecipeGalleryImage.objects.filter(space=request.space, recipe=recipe), pk=image_id)
        row.delete()
        return Response(extras_payload(request, recipe))


class RecipeGalleryDetailView(RecipeGalleryView):
    http_method_names = ["delete", "options"]
