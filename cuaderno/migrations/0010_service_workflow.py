from django.db import migrations, models
from django.utils import timezone
from zoneinfo import ZoneInfo


def preserve_legacy_dates(apps, schema_editor):
    plan_model = apps.get_model("cuaderno", "ServicePlan")
    for plan in plan_model.objects.select_related("meal_plan").iterator():
        # The old model never stored a creation timestamp: unknown, not migration time.
        plan.created_at = None
        instant = plan.meal_plan.from_date if plan.meal_plan_id else None
        plan.service_date = timezone.localtime(instant, ZoneInfo("Europe/Madrid")).date() if instant else None
        plan.save(update_fields=["created_at", "service_date"])


class Migration(migrations.Migration):
    dependencies = [("cuaderno", "0009_inventory_audit_metadata")]
    operations = [
        migrations.AddField(model_name="serviceplan", name="confirmed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="serviceplan", name="created_at", field=models.DateTimeField(auto_now_add=True, null=True)),
        migrations.AddField(model_name="serviceplan", name="produced_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="serviceplan", name="produced_key", field=models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField(model_name="serviceplan", name="service_date", field=models.DateField(db_index=True, default=timezone.localdate, null=True)),
        migrations.AddField(model_name="serviceplan", name="snapshot", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(
            model_name="serviceplan", name="state",
            field=models.CharField(choices=[("draft", "Borrador"), ("confirmed", "Confirmado"), ("produced", "Producido"), ("cancelled", "Cancelado")],
                                   db_index=True, default="draft", max_length=16),
        ),
        migrations.RunPython(preserve_legacy_dates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="serviceplan",
            constraint=models.UniqueConstraint(condition=~models.Q(produced_key=""), fields=("space", "produced_key"), name="cuaderno_service_produced_key"),
        ),
    ]
