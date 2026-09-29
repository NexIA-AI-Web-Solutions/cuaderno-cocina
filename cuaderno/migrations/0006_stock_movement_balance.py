from datetime import timedelta

from django.db import migrations, models


def backfill_balances(apps, schema_editor):
    StockMovement = apps.get_model("cuaderno", "StockMovement")
    InventoryLog = apps.get_model("cookbook", "InventoryLog")
    used_logs = set()
    for movement in StockMovement.objects.order_by("created_at", "pk").iterator():
        # Only recover from a matching native audit event; never substitute
        # today's balance for a historical value that cannot be proven.
        logs = InventoryLog.objects.filter(
            entry_id=movement.entry_id, note=movement.kind,
            created_at__lte=movement.created_at,
            created_at__gte=movement.created_at - timedelta(seconds=5),
        ).exclude(pk__in=used_logs).order_by("created_at", "pk")
        matches = []
        for log in logs:
            delta = log.new_amount - log.old_amount
            expected = movement.quantity if movement.kind == "receipt" else -movement.quantity
            if delta != expected:
                continue
            matches.append(log)
        # Ambiguous legacy data remains unknown rather than inventing a match.
        if len(matches) == 1:
            log = matches[0]
            movement.balance_after = log.new_amount
            movement.save(update_fields=["balance_after"])
            used_logs.add(log.pk)


class Migration(migrations.Migration):
    dependencies = [("cuaderno", "0005_recipe_exchange_record")]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="balance_after",
            field=models.DecimalField(blank=True, decimal_places=16, max_digits=32, null=True),
        ),
        migrations.RunPython(backfill_balances, migrations.RunPython.noop),
    ]
