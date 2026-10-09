"""Space-scoped singleton photos with authenticated, private content routes."""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from cookbook.helper.permission_helper import CustomTokenHasReadWriteScope
from cuaderno.api.base import CuadernoAPIView, CuadernoIsOperator
from cuaderno.models import MenuTemplate
from cuaderno.services.entity_media import (
    delete_unreferenced_file, entity_for, image_model, image_response, image_row, media_payload, optimized_raster,
)
from cuaderno.services.functional_access import checked, lock_space
from cuaderno.services.planning_inputs import text
from cuaderno.services.recipe_extras import validated_raster


class EntityImageView(CuadernoAPIView):
    permission_classes = [CuadernoIsOperator & CustomTokenHasReadWriteScope]
    http_method_names = ["get", "head", "put", "delete", "options"]
    kind = None

    def parent(self, request, kwargs, *, write=False):
        return entity_for(request, self.kind, kwargs[f"{self.kind}_id"], write=write)

    def touch_template(self, parent):
        if self.kind == "template":
            parent.updated_at = timezone.now()
            MenuTemplate.objects.filter(pk=parent.pk, space_id=parent.space_id).update(updated_at=parent.updated_at)

    def get(self, request, **kwargs):
        return Response(media_payload(request, self.kind, self.parent(request, kwargs)))

    def put(self, request, **kwargs):
        # Authorization precedes multipart parsing and image decoding. The
        # permission is refreshed again under the shared Space writer lock.
        self.parent(request, kwargs, write=True)
        if (set(request.data) - {"image", "caption"}
                or set(request.FILES) != {"image"}
                or len(request.FILES.getlist("image")) != 1
                or any(len(request.data.getlist(key)) != 1 for key in request.data)):
            raise ValidationError({"image": "Envía una sola imagen y un texto opcional."})
        caption = checked(text, request.data.get("caption", ""), 240, empty=True)
        upload = optimized_raster(validated_raster(request.FILES.get("image")))
        row, stored_name, committed = None, None, False
        try:
            with transaction.atomic():
                lock_space(request)
                parent = self.parent(request, kwargs, write=True)
                row = image_row(self.kind, parent)
                old_name, old_storage = (row.image.name, row.image.storage) if row else (None, None)
                if row is None:
                    row = image_model(self.kind)(space=request.space, **{self.kind: parent})
                row.caption, row.updated_by = caption, request.user
                row.image.save(upload.name, upload, save=False)
                stored_name = row.image.name
                row.save()
                self.touch_template(parent)
                payload = media_payload(request, self.kind, parent)
                if old_name:
                    transaction.on_commit(lambda: delete_unreferenced_file(old_storage, old_name, row._state.db), robust=True)
            committed = True
            return Response(payload)
        except Exception:
            # The previous file remains referenced until the transaction is
            # committed. A failed DB write or response construction removes
            # only the new UUID file, leaving the previous image intact.
            if not committed and row is not None and stored_name:
                row.image.storage.delete(stored_name)
            raise
        finally:
            upload.close()

    def delete(self, request, **kwargs):
        with transaction.atomic():
            lock_space(request)
            parent = self.parent(request, kwargs, write=True)
            row = image_row(self.kind, parent)
            if row:
                row.delete()
                self.touch_template(parent)
            return Response(media_payload(request, self.kind, parent))


class FoodImageView(EntityImageView):
    kind = "food"


class MenuTemplateImageView(EntityImageView):
    kind = "template"


class EntityImageContentView(EntityImageView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, **kwargs):
        return image_response(self.kind, self.parent(request, kwargs))


class FoodImageContentView(EntityImageContentView):
    kind = "food"


class MenuTemplateImageContentView(EntityImageContentView):
    kind = "template"
