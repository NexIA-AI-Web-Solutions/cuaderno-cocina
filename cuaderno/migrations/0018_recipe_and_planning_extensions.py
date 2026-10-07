"""Add native recipe/calendar extensions; no historical data is rewritten."""
import cuaderno.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cuaderno", "0017_release_integrity_and_allergen_audit"),
        ("cookbook", "0245_cuaderno_theme_labels"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='RecipeGalleryImage',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('recipe', models.ForeignKey('cookbook.Recipe', on_delete=models.CASCADE, related_name='cuaderno_gallery')),
                ('image', models.ImageField(upload_to=cuaderno.models.recipe_gallery_path)),
                ('caption', models.CharField(max_length=256, blank=True, default='')),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('created_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ('position', 'pk'), 'constraints': [models.CheckConstraint(condition=models.Q(position__lte=19), name='cuaderno_gallery_position'), models.UniqueConstraint(fields=['recipe', 'position'], name='cuaderno_gallery_slot')]},
        ),
        migrations.CreateModel(
            name='RecipeFavorite',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('user', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('recipe', models.ForeignKey('cookbook.Recipe', on_delete=models.CASCADE, related_name='cuaderno_favorites')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=['user', 'recipe'], name='cuaderno_favorite_unique')]},
        ),
        migrations.CreateModel(
            name='RecipeVariant',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('recipe', models.OneToOneField('cookbook.Recipe', on_delete=models.CASCADE, related_name='cuaderno_variant')),
                ('source_recipe', models.ForeignKey('cookbook.Recipe', on_delete=models.CASCADE, related_name='cuaderno_variants')),
                ('created_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
            ],
            options={'constraints': [models.CheckConstraint(condition=~models.Q(recipe=models.F('source_recipe')), name='cuaderno_variant_not_self')]},
        ),
        migrations.CreateModel(
            name='RecipeDietDeclaration',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('recipe', models.ForeignKey('cookbook.Recipe', on_delete=models.CASCADE, related_name='cuaderno_diets')),
                ('slug', models.CharField(max_length=16)),
                ('status', models.CharField(max_length=16, default='unknown')),
                ('note', models.CharField(max_length=1000, blank=True, default='')),
                ('updated_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=['recipe', 'slug'], name='cuaderno_diet_unique'), models.CheckConstraint(condition=models.Q(slug__in=['celiacos', 'colesterol', 'diabetes', 'hiposodica', 'gastrica', 'fibra', 'sinfructosa', 'sinlactosa']), name='cuaderno_diet_slug'), models.CheckConstraint(condition=models.Q(status__in=['unknown', 'suitable', 'unsuitable']), name='cuaderno_diet_status')]},
        ),
        migrations.CreateModel(
            name='MealCourse',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('meal_type', models.ForeignKey('cookbook.MealType', on_delete=models.CASCADE, related_name='cuaderno_courses')),
                ('name', models.CharField(max_length=128)),
                ('position', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'ordering': ('position', 'pk'), 'constraints': [models.UniqueConstraint(fields=['meal_type', 'name'], name='cuaderno_course_name')]},
        ),
        migrations.CreateModel(
            name='MenuTemplate',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('name', models.CharField(max_length=128)),
                ('weeks', models.PositiveSmallIntegerField(default=1)),
                ('created_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'constraints': [models.CheckConstraint(condition=models.Q(weeks__gte=1, weeks__lte=5), name='cuaderno_template_weeks')]},
        ),
        migrations.CreateModel(
            name='MenuTemplateEntry',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('template', models.ForeignKey('cuaderno.menutemplate', on_delete=models.CASCADE, related_name='entries')),
                ('day_index', models.PositiveSmallIntegerField()),
                ('meal_type', models.ForeignKey('cookbook.MealType', on_delete=models.PROTECT)),
                ('course', models.ForeignKey('cuaderno.mealcourse', on_delete=models.PROTECT, null=True, blank=True)),
                ('recipe', models.ForeignKey('cookbook.Recipe', on_delete=models.PROTECT, null=True, blank=True)),
                ('title', models.CharField(max_length=64, blank=True, default='')),
                ('source_url', models.URLField(max_length=1024, blank=True, default='')),
                ('servings', models.DecimalField(max_digits=8, decimal_places=4, default=1)),
            ],
            options={'ordering': ('day_index', 'meal_type_id', 'course_id', 'pk'), 'constraints': [models.CheckConstraint(condition=models.Q(day_index__lte=34), name='cuaderno_template_day'), models.CheckConstraint(condition=models.Q(servings__gt=0), name='cuaderno_template_servings'), models.UniqueConstraint(fields=['template', 'day_index', 'meal_type', 'course'], nulls_distinct=False, name='cuaderno_template_slot')]},
        ),
        migrations.CreateModel(
            name='MealPlanCourse',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('meal_plan', models.OneToOneField('cookbook.MealPlan', on_delete=models.CASCADE, related_name='cuaderno_course')),
                ('course', models.ForeignKey('cuaderno.mealcourse', on_delete=models.PROTECT, null=True, blank=True)),
                ('source_template', models.ForeignKey('cuaderno.menutemplate', on_delete=models.SET_NULL, null=True, blank=True)),
                ('application_date', models.DateField(null=True, blank=True)),
                ('source_url', models.URLField(max_length=1024, blank=True, default='')),
            ],
            options={},
        ),
        migrations.CreateModel(
            name='CalendarEntry',
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ('space', models.ForeignKey('cookbook.Space', on_delete=models.CASCADE)),
                ('kind', models.CharField(max_length=16, default='event')),
                ('title', models.CharField(max_length=128)),
                ('member_name', models.CharField(max_length=128, blank=True, default='')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('note', models.CharField(max_length=1000, blank=True, default='')),
                ('created_by', models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('start_date', 'pk'), 'constraints': [models.CheckConstraint(condition=models.Q(kind__in=['event', 'absence']), name='cuaderno_calendar_kind'), models.CheckConstraint(condition=models.Q(end_date__gte=models.F('start_date')), name='cuaderno_calendar_dates')]},
        ),
    ]
