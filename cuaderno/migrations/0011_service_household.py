from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cuaderno", "0010_service_workflow")]
    operations = [
        # Historical membership is unknown: never infer ownership from today's membership.
        migrations.AddField(
            model_name="serviceplan", name="household",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="cookbook.household"),
        ),
    ]
