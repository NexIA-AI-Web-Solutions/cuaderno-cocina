from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cuaderno", "0008_inventory_write_request"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        # Legacy metadata cannot be inferred from today's mutable entry.
        migrations.AddField(model_name="stockmovement", name="metadata_snapshot", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="inventorywriterequest", name="metadata_before", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="inventorywriterequest", name="metadata_after", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(
            model_name="inventorywriterequest", name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
    ]
