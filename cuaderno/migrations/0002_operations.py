import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuaderno", "0001_initial"),
        ("cookbook", "0242_space_household_setup_completed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("receipt", "Recepción"), ("consume", "Consumo"), ("waste", "Desperdicio")], max_length=16)),
                ("quantity", models.DecimalField(decimal_places=16, max_digits=32)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("fingerprint", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cuaderno_movements", to="cookbook.inventoryentry")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_movements", to="cookbook.space")),
            ],
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(fields=("space", "idempotency_key"), name="cuaderno_movement_idempotency"),
        ),
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=16, max_digits=32)),
                ("supplier_name", models.CharField(blank=True, default="", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("food", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.food")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_orders", to="cookbook.space")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cookbook.unit")),
            ],
        ),
        migrations.CreateModel(
            name="ServicePlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=128)),
                ("covers", models.DecimalField(decimal_places=2, max_digits=12)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("meal_plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="cookbook.mealplan")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cuaderno_services", to="cookbook.space")),
            ],
        ),
        migrations.CreateModel(
            name="AllergenDeclaration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("state", models.CharField(choices=[("declared", "Declarado"), ("unknown", "Desconocido")], default="unknown", max_length=16)),
                ("food", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cuaderno_allergens", to="cookbook.food")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="cookbook.space")),
            ],
        ),
    ]
