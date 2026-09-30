from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cuaderno", "0015_stockminimum"),
        ("cookbook", "0243_ingredient_yield_policy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # Historical service snapshots do not contain frozen instructions. Do not
    # backfill them from today's recipes and misrepresent those as historical.
    operations = [migrations.CreateModel(
        name="ServicePreparationItem",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("task_key", models.CharField(max_length=128)),
            ("position", models.PositiveIntegerField()),
            ("recipe_id_snapshot", models.PositiveBigIntegerField()),
            ("name", models.TextField(blank=True, default="")),
            ("instruction", models.TextField(blank=True, default="")),
            ("checked", models.BooleanField(default=False)),
            ("checked_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="cookbook.space")),
            ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="preparation_items", to="cuaderno.serviceplan")),
            ("source_step", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="cookbook.step")),
            ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ],
        options={
            "ordering": ("position", "pk"),
            "constraints": [
                models.UniqueConstraint(fields=("service", "task_key"), name="cuaderno_preparation_task_unique"),
                models.UniqueConstraint(fields=("service", "position"), name="cuaderno_preparation_position_unique"),
                models.CheckConstraint(
                    condition=(models.Q(checked=True, checked_at__isnull=False)
                               | models.Q(checked=False, checked_at__isnull=True)),
                    name="cuaderno_preparation_checked_time",
                ),
            ],
        },
    )]
