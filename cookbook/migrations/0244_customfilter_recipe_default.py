"""Persist the choice value and repair only the former tuple default."""
import ast

from django.db import migrations, models


def repair_tuple_defaults(apps, schema_editor):
    filters = apps.get_model("cookbook", "CustomFilter").objects.using(schema_editor.connection.alias)
    for primary_key, previous in filters.filter(type__startswith="(").values_list("pk", "type").iterator():
        if not isinstance(previous, str) or len(previous) > 512:
            continue
        try:
            value = ast.literal_eval(previous)
        except (ValueError, SyntaxError, TypeError, RecursionError):
            continue
        if (isinstance(value, tuple) and len(value) == 2 and value[0] == "RECIPE"
                and isinstance(value[1], str)):
            filters.filter(pk=primary_key, type=previous).update(type="RECIPE")


class Migration(migrations.Migration):
    dependencies = [("cookbook", "0243_ingredient_yield_policy")]
    operations = [
        migrations.AlterField(
            model_name="customfilter", name="type",
            field=models.CharField(choices=[("RECIPE", "Recipe"), ("FOOD", "Food"), ("KEYWORD", "Keyword")],
                                   default="RECIPE", max_length=128),
        ),
        migrations.RunPython(repair_tuple_defaults, migrations.RunPython.noop),
    ]
