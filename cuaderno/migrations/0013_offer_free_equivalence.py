from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cuaderno", "0012_purchaseoffer_purchasereceipt_and_more")]
    operations = [
        migrations.RemoveConstraint(model_name="purchaseoffer", name="cuaderno_offer_explicit_price"),
        migrations.AddConstraint(
            model_name="purchaseoffer",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0, explicit_free=False) | models.Q(amount=0, explicit_free=True),
                name="cuaderno_offer_explicit_price",
            ),
        ),
    ]
