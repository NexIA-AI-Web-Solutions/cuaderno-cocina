"""Change theme and storage labels while retaining all stored values and schema."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cookbook", "0244_customfilter_recipe_default")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="space", name="space_theme",
                    field=models.CharField(
                        choices=[("BLANK", "-------"), ("TANDOOR", "Cuaderno Cocina"),
                                 ("BOOTSTRAP", "Cuaderno clásico claro"), ("DARKLY", "Cuaderno clásico oscuro"),
                                 ("FLATLY", "Cuaderno plano"), ("SUPERHERO", "Cuaderno contraste"),
                                 ("TANDOOR_DARK", "Cuaderno Cocina oscuro (incompleto)")],
                        default="BLANK", max_length=128,
                    ),
                ),
                migrations.AlterField(
                    model_name="userpreference", name="theme",
                    field=models.CharField(
                        choices=[("TANDOOR", "Cuaderno Cocina"), ("BOOTSTRAP", "Cuaderno clásico claro"),
                                 ("DARKLY", "Cuaderno clásico oscuro"), ("FLATLY", "Cuaderno plano"),
                                 ("SUPERHERO", "Cuaderno contraste"),
                                 ("TANDOOR_DARK", "Cuaderno Cocina oscuro (incompleto)")],
                        default="TANDOOR", max_length=128,
                    ),
                ),
                migrations.AlterField(
                    model_name="storage", name="method",
                    field=models.CharField(
                        choices=[("DB", "Archivos remotos · token"),
                                 ("NEXTCLOUD", "Archivos remotos · usuario y contraseña"),
                                 ("LOCAL", "Archivos locales")],
                        default="DB", max_length=128,
                    ),
                ),
            ],
        ),
    ]
