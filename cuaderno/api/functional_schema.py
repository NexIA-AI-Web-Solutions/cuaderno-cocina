"""Explicit wire contracts for extensions of native recipes and calendars."""
from rest_framework import serializers as f

from cuaderno.api.schema import DecimalInput, DecimalText, Sha256
from cuaderno.services.planning_inputs import DIETS, STATUSES


class RecipeReferenceSchema(f.Serializer):
    id = f.IntegerField()
    name = f.CharField()


class GalleryImageSchema(f.Serializer):
    id = f.IntegerField()
    url = f.CharField()
    caption = f.CharField()
    position = f.IntegerField()


class DietWriteSchema(f.Serializer):
    slug = f.ChoiceField(choices=[slug for slug, _ in DIETS])
    status = f.ChoiceField(choices=STATUSES)
    note = f.CharField(required=False, allow_blank=True, max_length=1000)


class DietDeclarationSchema(DietWriteSchema):
    label = f.CharField()
    updated_at = f.DateTimeField(allow_null=True)


class RecipeExtrasSchema(f.Serializer):
    recipe_id = f.IntegerField()
    revision = Sha256()
    can_edit = f.BooleanField()
    is_favorite = f.BooleanField()
    gallery = GalleryImageSchema(many=True)
    diets = DietDeclarationSchema(many=True)
    variant_of = RecipeReferenceSchema(allow_null=True)
    variants = RecipeReferenceSchema(many=True)
    variants_truncated = f.BooleanField()
    declaration = f.CharField()


class RecipeExtrasWriteSchema(f.Serializer):
    revision = Sha256()
    diets = DietWriteSchema(many=True, required=False)
    variant_of = f.IntegerField(allow_null=True, required=False)


class FavoriteWriteSchema(f.Serializer):
    favorite = f.BooleanField()


class FavoriteResultSchema(f.Serializer):
    recipe_id = f.IntegerField()
    is_favorite = f.BooleanField()


class FavoriteRecipeSchema(RecipeReferenceSchema):
    image = f.CharField(allow_null=True)


class FavoritesSchema(f.Serializer):
    count = f.IntegerField()
    results = FavoriteRecipeSchema(many=True)


class GalleryWriteSchema(f.Serializer):
    image = f.FileField()
    caption = f.CharField(required=False, allow_blank=True, max_length=256)


class EntityImageSchema(f.Serializer):
    url = f.CharField(help_text="Ruta autenticada del contenido de la imagen.")
    caption = f.CharField(help_text="Descripción de la imagen.")


class EntityImageResultSchema(f.Serializer):
    image = EntityImageSchema(allow_null=True, help_text="Imagen actual; null si no existe.")
    can_edit = f.BooleanField(help_text="Permiso actual para modificar esta imagen.")
    revision = Sha256(required=False, help_text="Revisión actual de la plantilla, cuando corresponda.")


class EntityImageWriteSchema(f.Serializer):
    image = f.FileField(help_text="Imagen JPG, PNG, WebP o GIF de un fotograma, hasta 5 MiB.")
    caption = f.CharField(required=False, allow_blank=True, max_length=240, help_text="Descripción opcional de la imagen.")


class CourseWriteSchema(f.Serializer):
    name = f.CharField(max_length=128)
    meal_type = f.IntegerField()
    position = f.IntegerField(required=False, min_value=0, max_value=199)


class CourseUpdateSchema(CourseWriteSchema):
    revision = Sha256()


class CourseSchema(CourseWriteSchema):
    id = f.IntegerField()
    revision = Sha256()


class PlanningMealSchema(f.Serializer):
    id = f.IntegerField()
    title = f.CharField()
    recipe = RecipeReferenceSchema(allow_null=True)
    meal_type = RecipeReferenceSchema()
    course = f.IntegerField(allow_null=True)
    course_name = f.CharField(allow_null=True)
    servings = DecimalText()
    from_date = f.DateTimeField()
    to_date = f.DateTimeField()
    note = f.CharField()
    source_url = f.CharField()
    diet_status = f.ChoiceField(choices=STATUSES)


class MealCourseWriteSchema(f.Serializer):
    course = f.IntegerField(allow_null=True)


class CalendarWriteSchema(f.Serializer):
    kind = f.ChoiceField(choices=("event", "absence"))
    title = f.CharField(max_length=128)
    member_name = f.CharField(required=False, allow_blank=True, max_length=128)
    start_date = f.DateField()
    end_date = f.DateField()
    note = f.CharField(required=False, allow_blank=True, max_length=1000)


class CalendarUpdateSchema(CalendarWriteSchema):
    revision = Sha256()


class CalendarEntrySchema(CalendarWriteSchema):
    id = f.IntegerField()
    revision = Sha256()


class PlanningSchema(f.Serializer):
    courses = CourseSchema(many=True)
    meal_plans = PlanningMealSchema(many=True)
    events = CalendarEntrySchema(many=True)
    can_edit = f.BooleanField()
    can_manage_absences = f.BooleanField()
    can_merge_print = f.BooleanField()
    declaration = f.CharField()


class TemplateEntryWriteSchema(f.Serializer):
    day_index = f.IntegerField(min_value=0, max_value=34)
    meal_type = f.IntegerField()
    course = f.IntegerField(required=False, allow_null=True)
    recipe = f.IntegerField(required=False, allow_null=True)
    title = f.CharField(required=False, allow_blank=True, max_length=64)
    source_url = f.CharField(required=False, allow_blank=True, max_length=1024)
    servings = DecimalInput()


class TemplateEntrySchema(TemplateEntryWriteSchema):
    id = f.IntegerField()
    meal_type_name = f.CharField()
    course_name = f.CharField(allow_null=True)
    recipe_name = f.CharField(allow_null=True)
    servings = DecimalText()


class TemplateWriteSchema(f.Serializer):
    name = f.CharField(max_length=128)
    weeks = f.IntegerField(min_value=1, max_value=5)
    entries = TemplateEntryWriteSchema(many=True)


class TemplateUpdateSchema(TemplateWriteSchema):
    revision = Sha256()


class MenuTemplateSchema(TemplateWriteSchema):
    id = f.IntegerField()
    revision = Sha256()
    entries = TemplateEntrySchema(many=True)
    image = EntityImageSchema(required=False, allow_null=True, help_text="Portada opcional de la plantilla.")


class MenuTemplatesSchema(f.Serializer):
    count = f.IntegerField()
    results = MenuTemplateSchema(many=True)


class TemplateApplyWriteSchema(f.Serializer):
    revision = Sha256()
    start_date = f.DateField()
    overwrite = f.BooleanField(required=False)


class TemplateApplyResultSchema(f.Serializer):
    created_ids = f.ListField(child=f.IntegerField())
    replaced_ids = f.ListField(child=f.IntegerField())


class PrintMenuWriteSchema(f.Serializer):
    name = f.CharField(max_length=128)
    meal_plan_ids = f.ListField(child=f.IntegerField(), min_length=1, max_length=100)
    template_id = f.IntegerField(required=False, min_value=1, help_text="Plantilla visible cuya portada se usará en el documento.")


class MenuPrintWriteSchema(f.Serializer):
    orientation = f.ChoiceField(choices=("portrait", "landscape"))
    menus = PrintMenuWriteSchema(many=True)
    diet = f.ChoiceField(choices=[slug for slug, _ in DIETS], required=False, allow_null=True)


class PrintedMenuSchema(f.Serializer):
    name = f.CharField()
    entries = PlanningMealSchema(many=True)
    image = EntityImageSchema(required=False, allow_null=True, help_text="Portada autorizada del menú.")


class MenuPrintSchema(f.Serializer):
    orientation = f.ChoiceField(choices=("portrait", "landscape"))
    merged = f.BooleanField()
    menus = PrintedMenuSchema(many=True)
    diet = f.CharField(allow_null=True)
    diet_label = f.CharField(allow_null=True)
    declaration = f.CharField()
