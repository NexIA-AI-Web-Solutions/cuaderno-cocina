from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cookbook", "0242_space_household_setup_completed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cuaderno", "0006_stock_movement_balance"),
    ]
    operations = [
        migrations.CreateModel(
            name="RecipeYield",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=16, max_digits=32)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipe", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_yield", to="cookbook.recipe")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_recipe_yields", to="cookbook.space")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.unit")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
