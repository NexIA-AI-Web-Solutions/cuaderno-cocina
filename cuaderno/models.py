from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid
from pathlib import PurePosixPath


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
        constraints = [models.CheckConstraint(
            condition=models.Q(target_food_cost_ratio__isnull=True)
            | (models.Q(target_food_cost_ratio__gt=0) & models.Q(target_food_cost_ratio__lte=1)),
            name="cuaderno_profile_target_ratio",
        )]


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
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_package_positive_quantity"),
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
            models.Index(fields=["space", "package", "-valid_from", "-id"],
                         include=["amount", "explicit_free"], name="cuaderno_price_current_cover"),
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
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_movement_positive_quantity"),
            models.CheckConstraint(condition=models.Q(kind__in=("receipt", "consume", "waste")), name="cuaderno_movement_valid_kind"),
            models.CheckConstraint(condition=~models.Q(reverses=models.F("pk")), name="cuaderno_movement_no_self_reversal"),
            models.UniqueConstraint(fields=["space", "idempotency_key"], name="cuaderno_movement_idempotency"),
            models.UniqueConstraint(
                fields=["reverses"],
                condition=models.Q(reverses__isnull=False),
                name="cuaderno_one_reversal_per_movement",
            ),
        ]
        indexes = [
            models.Index(fields=["space", "created_at"], name="cuaderno_movement_space_time"),
            models.Index(fields=["space", "-id"], name="cuaderno_movement_space_id"),
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
        constraints = [
            models.CheckConstraint(condition=models.Q(covers__gt=0), name="cuaderno_service_positive_covers"),
            models.CheckConstraint(condition=models.Q(state__in=("draft", "confirmed", "produced", "cancelled")), name="cuaderno_service_valid_state"),
            models.UniqueConstraint(
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
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(state__in=("declared", "unknown")), name="cuaderno_allergen_valid_state",
        )]


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

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="cuaderno_yield_positive_quantity")]


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


def recipe_gallery_path(instance, filename):
    """Only validated raster uploads reach this UUID namespace."""
    return f"recipes/gallery/{uuid.uuid4().hex}{PurePosixPath(filename).suffix.lower()}"


class RecipeGalleryImage(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_gallery")
    image = models.ImageField(upload_to=recipe_gallery_path)
    caption = models.CharField(max_length=256, blank=True, default="")
    position = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(position__lte=19), name="cuaderno_gallery_position"),
            models.UniqueConstraint(fields=["recipe", "position"], name="cuaderno_gallery_slot"),
        ]


class RecipeFavorite(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_favorites")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "recipe"], name="cuaderno_favorite_unique")]


class RecipeVariant(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    recipe = models.OneToOneField("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_variant")
    source_recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_variants")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(recipe=models.F("source_recipe")), name="cuaderno_variant_not_self")]


class RecipeDietDeclaration(models.Model):
    """User assertions only; no clinical or missing-allergen inference."""
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.CASCADE, related_name="cuaderno_diets")
    slug = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="unknown")
    note = models.CharField(max_length=1000, blank=True, default="")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe", "slug"], name="cuaderno_diet_unique"),
            models.CheckConstraint(condition=models.Q(slug__in=["celiacos", "colesterol", "diabetes", "hiposodica", "gastrica", "fibra", "sinfructosa", "sinlactosa"]), name="cuaderno_diet_slug"),
            models.CheckConstraint(condition=models.Q(status__in=["unknown", "suitable", "unsuitable"]), name="cuaderno_diet_status"),
        ]


class MealCourse(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    meal_type = models.ForeignKey("cookbook.MealType", on_delete=models.CASCADE, related_name="cuaderno_courses")
    name = models.CharField(max_length=128)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = [models.UniqueConstraint(fields=["meal_type", "name"], name="cuaderno_course_name")]


class MenuTemplate(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    weeks = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(weeks__gte=1, weeks__lte=5), name="cuaderno_template_weeks")]


class MenuTemplateEntry(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    template = models.ForeignKey(MenuTemplate, on_delete=models.CASCADE, related_name="entries")
    day_index = models.PositiveSmallIntegerField()
    meal_type = models.ForeignKey("cookbook.MealType", on_delete=models.PROTECT)
    course = models.ForeignKey(MealCourse, on_delete=models.PROTECT, null=True, blank=True)
    recipe = models.ForeignKey("cookbook.Recipe", on_delete=models.PROTECT, null=True, blank=True)
    title = models.CharField(max_length=64, blank=True, default="")
    source_url = models.URLField(max_length=1024, blank=True, default="")
    servings = models.DecimalField(max_digits=8, decimal_places=4, default=1)

    class Meta:
        ordering = ("day_index", "meal_type_id", "course_id", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(day_index__lte=34), name="cuaderno_template_day"),
            models.CheckConstraint(condition=models.Q(servings__gt=0), name="cuaderno_template_servings"),
            models.UniqueConstraint(fields=["template", "day_index", "meal_type", "course"], nulls_distinct=False, name="cuaderno_template_slot"),
        ]


class CustomerReservation(models.Model):
    """An internal customer commitment backed by existing production services."""

    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    IN_KITCHEN = "in_kitchen"
    SERVED = "served"
    CANCELLED = "cancelled"
    STATES = ((REQUESTED, "Solicitada"), (CONFIRMED, "Confirmada"),
              (IN_KITCHEN, "En cocina"), (SERVED, "Servida"), (CANCELLED, "Anulada"))

    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    household = models.ForeignKey("cookbook.Household", on_delete=models.PROTECT, null=True, blank=True)
    customer_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    service_date = models.DateField(db_index=True)
    service_time = models.TimeField()
    template = models.ForeignKey(MenuTemplate, on_delete=models.PROTECT)
    template_day = models.PositiveSmallIntegerField(default=0)
    meal_type = models.ForeignKey("cookbook.MealType", on_delete=models.PROTECT)
    covers = models.PositiveIntegerField()
    note = models.TextField(blank=True, default="")
    state = models.CharField(max_length=16, choices=STATES, default=REQUESTED, db_index=True)
    menu_snapshot = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cuaderno_reservations_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cuaderno_reservations_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("service_date", "service_time", "pk")
        indexes = [models.Index(fields=["space", "service_date", "state"], name="cuaderno_reservation_day")]
        constraints = [
            models.CheckConstraint(condition=models.Q(covers__gte=1, covers__lte=9999), name="cuaderno_reservation_covers"),
            models.CheckConstraint(condition=models.Q(template_day__lte=34), name="cuaderno_reservation_menu_day"),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="cuaderno_reservation_revision"),
            models.CheckConstraint(condition=~models.Q(phone="", email=""), name="cuaderno_reservation_contact"),
            models.CheckConstraint(condition=models.Q(state__in=("requested", "confirmed", "in_kitchen", "served", "cancelled")), name="cuaderno_reservation_state"),
        ]


class ReservationRevision(models.Model):
    """Append-only application history; previous commitments remain reviewable."""

    reservation = models.ForeignKey(CustomerReservation, on_delete=models.PROTECT, related_name="history")
    revision = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    reason = models.CharField(max_length=1000, blank=True, default="")
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("revision", "pk")
        constraints = [models.UniqueConstraint(fields=["reservation", "revision"], name="cuaderno_reservation_history")]


class ReservationService(models.Model):
    """Versioned links, never a second stock or production ledger."""

    reservation = models.ForeignKey(CustomerReservation, on_delete=models.PROTECT, related_name="service_links")
    service = models.OneToOneField(ServicePlan, on_delete=models.PROTECT, related_name="reservation_link")
    revision = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("revision", "position", "pk")
        constraints = [models.UniqueConstraint(fields=["reservation", "revision", "position"], name="cuaderno_reservation_dish")]


class MealPlanCourse(models.Model):
    """Extend the native calendar; do not copy its recipes or shopping rows."""
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    meal_plan = models.OneToOneField("cookbook.MealPlan", on_delete=models.CASCADE, related_name="cuaderno_course")
    course = models.ForeignKey(MealCourse, on_delete=models.PROTECT, null=True, blank=True)
    source_template = models.ForeignKey(MenuTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    application_date = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=1024, blank=True, default="")


class CalendarEntry(models.Model):
    """Events and administrator-only absence annotations on the same calendar."""
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, default="event")
    title = models.CharField(max_length=128)
    member_name = models.CharField(max_length=128, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    note = models.CharField(max_length=1000, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("start_date", "pk")
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=["event", "absence"]), name="cuaderno_calendar_kind"),
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="cuaderno_calendar_dates"),
        ]


def _gallery_file_deleted(sender, instance, using, **kwargs):
    """Native Recipe/Space cascades revoke and remove only committed own images."""
    import re
    from django.db import transaction
    name, storage = instance.image.name, instance.image.storage
    if not name or not re.fullmatch(r"recipes/gallery/[a-f0-9]{32}\.(jpg|png|webp|gif)", name):
        return

    def remove_unreferenced():
        from cookbook.models import Recipe, UserFile
        if (RecipeGalleryImage._base_manager.using(using).filter(image=name).exists()
                or Recipe._base_manager.using(using).filter(image=name).exists()
                or UserFile._base_manager.using(using).filter(file=name).exists()):
            return
        storage.delete(name)

    transaction.on_commit(remove_unreferenced, using=using)


from django.db.models.signals import post_delete
post_delete.connect(_gallery_file_deleted, sender=RecipeGalleryImage, weak=False,
                    dispatch_uid="cuaderno.gallery.committed-file-delete")


def entity_media_path(instance, filename):
    """Never retain a user-supplied filename in the private storage namespace."""
    return f"cuaderno/entity-media/{uuid.uuid4().hex}{PurePosixPath(filename).suffix.lower()}"


class EntityImageBase(models.Model):
    space = models.ForeignKey("cookbook.Space", on_delete=models.CASCADE)
    image = models.ImageField(upload_to=entity_media_path)
    caption = models.CharField(max_length=240, blank=True, default="")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def clean(self):
        from django.core.exceptions import ValidationError
        parent = self.food if isinstance(self, FoodImage) else self.template
        if parent.space_id != self.space_id:
            raise ValidationError("La imagen debe pertenecer al mismo espacio que su ingrediente o menú.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class FoodImage(EntityImageBase):
    food = models.OneToOneField("cookbook.Food", on_delete=models.CASCADE, related_name="cuaderno_image")


class MenuTemplateImage(EntityImageBase):
    template = models.OneToOneField(MenuTemplate, on_delete=models.CASCADE, related_name="cuaderno_image")


def _entity_image_file_deleted(sender, instance, using, **kwargs):
    from django.db import transaction
    from cuaderno.services.entity_media import delete_unreferenced_file
    storage, name = instance.image.storage, instance.image.name
    transaction.on_commit(lambda: delete_unreferenced_file(storage, name, using), using=using, robust=True)


for _image_model in (FoodImage, MenuTemplateImage):
    post_delete.connect(_entity_image_file_deleted, sender=_image_model, weak=False,
                        dispatch_uid=f"cuaderno.{_image_model.__name__}.committed-file-delete")
