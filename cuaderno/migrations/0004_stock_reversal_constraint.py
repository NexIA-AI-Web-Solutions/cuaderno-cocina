from django.db import migrations, models


def check_legacy_reversals(apps, schema_editor):
    movement = apps.get_model("cuaderno", "StockMovement")
    duplicates = movement.objects.exclude(reverses_id=None).values("reverses_id").annotate(total=models.Count("pk")).filter(total__gt=1)
    if duplicates.exists():
        raise RuntimeError(
            "Hay reversiones duplicadas previas. Migración abortada sin borrar historial; "
            "reconciliar los movimientos y saldos en una copia aislada antes de actualizar."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cuaderno", "0003_margin_reversal"),
    ]

    operations = [
        migrations.RunPython(check_legacy_reversals, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                condition=models.Q(("reverses__isnull", False)),
                fields=("reverses",),
                name="cuaderno_one_reversal_per_movement",
            ),
        ),
    ]
