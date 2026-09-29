from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cookbook", "0242_space_household_setup_completed"),
        ("cuaderno", "0004_stock_reversal_constraint"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RecipeExchangeRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=64)),
                ("external_id", models.CharField(max_length=256)),
                ("payload_sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("recipe", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cuaderno_import_records", to="cookbook.recipe")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_recipe_imports", to="cookbook.space")),
            ],
        ),
        migrations.AddConstraint(
            model_name="recipeexchangerecord",
            constraint=models.UniqueConstraint(
                fields=("space", "source", "external_id"),
                name="cuaderno_recipe_import_identity",
            ),
        ),
    ]
