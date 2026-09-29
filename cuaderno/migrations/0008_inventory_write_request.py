from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cuaderno", "0007_recipe_yield")]
    operations = [
        migrations.CreateModel(
            name="InventoryWriteRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=128)),
                ("operation", models.CharField(max_length=64)),
                ("payload_sha256", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.inventoryentry")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="cookbook.space")),
            ],
        ),
        migrations.AddConstraint(
            model_name="inventorywriterequest",
            constraint=models.UniqueConstraint(fields=("space", "idempotency_key"), name="cuaderno_native_inventory_request"),
        ),
    ]
