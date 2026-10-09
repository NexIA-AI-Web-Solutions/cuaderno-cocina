"""Optional private pictures; native Food and menus remain authoritative."""
import cuaderno.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cuaderno", "0018_recipe_and_planning_extensions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name=name,
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("space", models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)),
                ("image", models.ImageField(upload_to=cuaderno.models.entity_media_path)),
                ("caption", models.CharField(max_length=240, blank=True, default="")),
                ("updated_by", models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (parent, models.OneToOneField(target, on_delete=models.CASCADE, related_name="cuaderno_image")),
            ],
            options={"abstract": False},
        )
        for name, parent, target in [
            ("FoodImage", "food", "cookbook.Food"),
            ("MenuTemplateImage", "template", "cuaderno.MenuTemplate"),
        ]
    ]
