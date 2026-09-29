from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cookbook", "0242_space_household_setup_completed")]
    operations = [
        migrations.AddField(
            model_name="ingredient", name="quantity_basis",
            field=models.CharField(max_length=16, choices=(("gross", "Bruta"), ("net_usable", "Neta útil")), default="gross"),
        ),
        migrations.AddField(
            model_name="ingredient", name="yield_ratio",
            field=models.DecimalField(max_digits=17, decimal_places=16, null=True, blank=True),
        ),
        migrations.AddConstraint(
            model_name="ingredient",
            constraint=models.CheckConstraint(
                condition=(models.Q(quantity_basis="gross") | models.Q(quantity_basis="net_usable", yield_ratio__isnull=False))
                & (models.Q(yield_ratio__isnull=True) | models.Q(yield_ratio__gt=0, yield_ratio__lte=1)),
                name="cuaderno_ingredient_yield_policy",
            ),
        ),
    ]
