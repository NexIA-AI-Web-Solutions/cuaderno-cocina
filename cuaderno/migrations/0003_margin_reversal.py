from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuaderno", "0002_operations"),
    ]

    operations = [
        migrations.AddField(
            model_name="spaceprofile",
            name="target_food_cost_ratio",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="reverses",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT, related_name="reversals", to="cuaderno.stockmovement"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["space", "created_at"], name="cuaderno_movement_space_time"),
        ),
    ]
