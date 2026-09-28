from django.conf import settings
from django.db import models


class SpaceProfile(models.Model):
    """Commercial edition and price policy for one Tandoor Space. Not a billing engine."""

    ESENCIAL = "esencial"
    PROFESIONAL = "profesional"
    INTEGRAL = "integral"
    EDITIONS = (
        (ESENCIAL, "Esencial"),
        (PROFESIONAL, "Profesional"),
        (INTEGRAL, "Integral"),
    )
    NET = "net"
    GROSS = "gross"
    POLICIES = (
        ("", "Sin elegir"),
        (NET, "Neto"),
        (GROSS, "Bruto"),
    )

    space = models.OneToOneField("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_profile")
    edition = models.CharField(max_length=16, choices=EDITIONS, default=ESENCIAL)
    currency = models.CharField(max_length=3, default="EUR")
    price_policy = models.CharField(max_length=16, choices=POLICIES, default="", blank=True)

    class Meta:
        verbose_name = "perfil de cuaderno"


class PackageFormat(models.Model):
    """Purchase format tied to a native Food and Unit. Not a stock balance."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_packages")
    food = models.ForeignKey("cookbook.Food", on_delete=models.PROTECT, related_name="cuaderno_packages")
    unit = models.ForeignKey("cookbook.Unit", on_delete=models.PROTECT, related_name="cuaderno_packages")
    label = models.CharField(max_length=128)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    is_reference = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["space", "food"],
                condition=models.Q(is_reference=True),
                name="cuaderno_one_reference_package_per_food",
            ),
        ]


class PriceVersion(models.Model):
    """A dated price. Absence means unknown; zero is stored only when explicitly free."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_prices")
    package = models.ForeignKey(PackageFormat, on_delete=models.PROTECT, related_name="prices")
    amount = models.DecimalField(max_digits=32, decimal_places=16)
    explicit_free = models.BooleanField(default=False)
    valid_from = models.DateTimeField()
    note = models.CharField(max_length=256, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-valid_from", "-id")
        indexes = [
            models.Index(fields=["package", "valid_from"]),
        ]
