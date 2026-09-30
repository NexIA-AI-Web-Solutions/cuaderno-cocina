from django.conf import settings
from django.db import models
from django.utils import timezone


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
    target_food_cost_ratio = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)

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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0, explicit_free=False) | models.Q(amount=0, explicit_free=True),
                name="cuaderno_price_explicit_free",
            ),
        ]
        indexes = [
            models.Index(fields=["package", "valid_from"]),
        ]


class StockMovement(models.Model):
    """Idempotent professional movement. The balance remains InventoryEntry."""

    RECEIPT = "receipt"
    CONSUME = "consume"
    WASTE = "waste"
    KINDS = ((RECEIPT, "Recepción"), (CONSUME, "Consumo"), (WASTE, "Desperdicio"))

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_movements")
    entry = models.ForeignKey("cookbook.InventoryEntry", on_delete=models.PROTECT, related_name="cuaderno_movements")
    kind = models.CharField(max_length=16, choices=KINDS)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    idempotency_key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=128)
    balance_after = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    metadata_snapshot = models.JSONField(default=dict, blank=True)
    reverses = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["space", "idempotency_key"], name="cuaderno_movement_idempotency"),
            models.UniqueConstraint(
                fields=["reverses"],
                condition=models.Q(reverses__isnull=False),
                name="cuaderno_one_reversal_per_movement",
            ),
        ]
        indexes = [
            models.Index(fields=["space", "created_at"], name="cuaderno_movement_space_time"),
        ]


class PurchaseOrder(models.Model):
    """An order is not a receipt and does not change stock."""

    DRAFT = "draft"
    ORDERED = "ordered"
    PART_RECEIVED = "part_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    STATES = ((DRAFT, "Borrador"), (ORDERED, "Pedido"), (PART_RECEIVED, "Recibido parcialmente"), (RECEIVED, "Recibido"), (CANCELLED, "Cancelado"))

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_orders")
    food = models.ForeignKey("cookbook.Food", on_delete=models.PROTECT)
    unit = models.ForeignKey("cookbook.Unit", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    supplier_name = models.CharField(max_length=128, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    household = models.ForeignKey("cookbook.Household", on_delete=models.PROTECT, null=True, blank=True)
    supplier = models.ForeignKey("cookbook.Supermarket", on_delete=models.PROTECT, null=True, blank=True)
    package = models.ForeignKey(PackageFormat, on_delete=models.PROTECT, null=True, blank=True)
    state = models.CharField(max_length=16, choices=STATES, default=DRAFT, db_index=True)
    received_quantity = models.DecimalField(max_digits=32, decimal_places=16, default=0)
    package_count = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    package_quantity_snapshot = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    package_unit_snapshot = models.ForeignKey("cookbook.Unit", on_delete=models.PROTECT, null=True, blank=True, related_name="cuaderno_order_package_units")
    price_snapshot = models.DecimalField(max_digits=32, decimal_places=16, null=True, blank=True)
    currency_snapshot = models.CharField(max_length=3, default="EUR")
    ordered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_order_positive"),
            models.CheckConstraint(condition=models.Q(received_quantity__gte=0, received_quantity__lte=models.F("quantity")), name="cuaderno_order_received_bounds"),
            models.CheckConstraint(condition=models.Q(state__in=["draft", "ordered", "part_received", "received", "cancelled"]), name="cuaderno_order_valid_state"),
        ]


class PurchaseOffer(models.Model):
    """Dated supplier offer; not the recipe's reference price or a stock receipt."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    package = models.ForeignKey(PackageFormat, on_delete=models.PROTECT, related_name="supplier_offers")
    supplier = models.ForeignKey("cookbook.Supermarket", on_delete=models.PROTECT, related_name="cuaderno_offers")
    amount = models.DecimalField(max_digits=32, decimal_places=16)
    explicit_free = models.BooleanField(default=False)
    currency = models.CharField(max_length=3, default="EUR")
    valid_from = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["package", "supplier", "valid_from"], name="cuaderno_offer_supplier_date")]
        constraints = [models.CheckConstraint(
            condition=models.Q(amount__gt=0, explicit_free=False) | models.Q(amount=0, explicit_free=True), name="cuaderno_offer_explicit_price",
        )]


class PurchaseReceipt(models.Model):
    """Protected receipt document in order units, linked to its native stock movement."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    entry = models.ForeignKey("cookbook.InventoryEntry", on_delete=models.PROTECT)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="purchase_receipt")
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    idempotency_key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    reversed_by = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_receipt_reversal")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["space", "idempotency_key"], name="cuaderno_receipt_idempotency"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_receipt_positive"),
        ]


class ServicePlan(models.Model):
    """Internal covers. Not a payment, a public booking, or a table."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PRODUCED = "produced"
    CANCELLED = "cancelled"
    STATES = ((DRAFT, "Borrador"), (CONFIRMED, "Confirmado"), (PRODUCED, "Producido"), (CANCELLED, "Cancelado"))

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_services")
    household = models.ForeignKey("cookbook.Household", on_delete=models.PROTECT, null=True, blank=True)
    meal_plan = models.ForeignKey("cookbook.MealPlan", null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=128)
    covers = models.DecimalField(max_digits=12, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    service_date = models.DateField(default=timezone.localdate, db_index=True, null=True)
    state = models.CharField(max_length=16, choices=STATES, default=DRAFT, db_index=True)
    snapshot = models.JSONField(default=dict, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    produced_at = models.DateTimeField(null=True, blank=True)
    produced_key = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["space", "produced_key"], condition=~models.Q(produced_key=""), name="cuaderno_service_produced_key",
        )]


class ServicePreparationItem(models.Model):
    """A Step copy frozen at service confirmation, not another recipe editor."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    service = models.ForeignKey(ServicePlan, on_delete=models.CASCADE, related_name="preparation_items")
    source_step = models.ForeignKey("cookbook.Step", on_delete=models.SET_NULL, null=True, blank=True)
    task_key = models.CharField(max_length=128)
    position = models.PositiveIntegerField()
    recipe_id_snapshot = models.PositiveBigIntegerField()
    name = models.TextField(blank=True, default="")
    instruction = models.TextField(blank=True, default="")
    checked = models.BooleanField(default=False)
    checked_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(fields=["service", "task_key"], name="cuaderno_preparation_task_unique"),
            models.UniqueConstraint(fields=["service", "position"], name="cuaderno_preparation_position_unique"),
            models.CheckConstraint(
                condition=(models.Q(checked=True, checked_at__isnull=False)
                           | models.Q(checked=False, checked_at__isnull=True)),
                name="cuaderno_preparation_checked_time",
            ),
        ]


class AllergenDeclaration(models.Model):
    """Declared or unknown. Absence of a row is not proof the allergen is absent."""

    DECLARED = "declared"
    UNKNOWN = "unknown"
    STATES = ((DECLARED, "Declarado"), (UNKNOWN, "Desconocido"))

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    food = models.ForeignKey("cookbook.Food", on_delete=models.PROTECT, related_name="cuaderno_allergens")
    name = models.CharField(max_length=128)
    state = models.CharField(max_length=16, choices=STATES, default=UNKNOWN)


class RecipeExchangeRecord(models.Model):
    """Stable source identity for replay-safe generic recipe imports."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_recipe_imports")
    source = models.CharField(max_length=64)
    external_id = models.CharField(max_length=256)
    payload_sha256 = models.CharField(max_length=64)
    recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.PROTECT, related_name="cuaderno_import_records")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["space", "source", "external_id"],
                name="cuaderno_recipe_import_identity",
            ),
        ]


class RecipeYield(models.Model):
    """Declared usable output of a native Recipe for exact sub-recipe scaling."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE, related_name="cuaderno_recipe_yields")
    recipe = models.OneToOneField("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_yield")
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    unit = models.ForeignKey("cookbook.Unit", on_delete=models.PROTECT)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)


class InventoryWriteRequest(models.Model):
    """Replay identity for native writes, including zero and metadata-only writes."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    entry = models.ForeignKey("cookbook.InventoryEntry", on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128)
    operation = models.CharField(max_length=64)
    payload_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    metadata_before = models.JSONField(default=dict, blank=True)
    metadata_after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["space", "idempotency_key"], name="cuaderno_native_inventory_request")]


class StockMinimum(models.Model):
    """Reserve metadata only. InventoryEntry remains the sole stock balance."""

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    household = models.ForeignKey("cookbook.Household", on_delete=models.PROTECT)
    food = models.ForeignKey("cookbook.Food", on_delete=models.PROTECT)
    unit = models.ForeignKey("cookbook.Unit", on_delete=models.PROTECT)
    location = models.ForeignKey("cookbook.InventoryLocation", on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=32, decimal_places=16)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_minimum_positive"),
            models.UniqueConstraint(
                fields=["space", "household", "food", "location"], nulls_distinct=False,
                name="cuaderno_minimum_scope_unique",
            ),
        ]
