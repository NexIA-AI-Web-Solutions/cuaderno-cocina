from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cuaderno", "0014_price_explicit_free"),
        ("cookbook", "0243_ingredient_yield_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.CreateModel(
        name="StockMinimum",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("quantity", models.DecimalField(decimal_places=16, max_digits=32)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="cookbook.space")),
            ("household", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.household")),
            ("food", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.food")),
            ("unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.unit")),
            ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="cookbook.inventorylocation")),
            ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ],
        options={"constraints": [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_minimum_positive"),
            models.UniqueConstraint(fields=("space", "household", "food", "location"), nulls_distinct=False, name="cuaderno_minimum_scope_unique"),
        ]},
    )]
