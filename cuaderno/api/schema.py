"""Wire contracts; runtime write validation belongs to the endpoint serializers."""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from cookbook.models import Ingredient


class DecimalText(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$", **kwargs)


@extend_schema_field({"oneOf": [
    {"type": "string", "description": "Exact finite decimal text; point or comma, without thousands grouping. Binary floating point is rejected."},
    {"type": "integer", "description": "Exact integer JSON input."},
]})
class DecimalInput(serializers.Field):
    """Describe legacy exact input without narrowing its existing integer/text API."""

    def to_internal_value(self, data):
        from cuaderno.domain.money import parse_decimal
        return parse_decimal(data)

    def to_representation(self, value):
        return format(value, "f")


class Sha256(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(r"^[0-9a-f]{64}$", **kwargs)


class ReadySerializer(serializers.Serializer):
    ready = serializers.BooleanField()


class EditionWriteSchema(serializers.Serializer):
    edition = serializers.ChoiceField(choices=("esencial", "profesional", "integral"), required=False)
    price_policy = serializers.ChoiceField(choices=("", "net", "gross"), required=False)
    target_food_cost_ratio = DecimalInput(required=False, allow_null=True)


class OperationalRoleSchema(serializers.Serializer):
    code = serializers.ChoiceField(choices=("guest", "user", "admin")); label = serializers.CharField()
    space = serializers.IntegerField(); can_operate_cuaderno = serializers.BooleanField()
    can_manage_edition = serializers.BooleanField(); native_permissions_preserved = serializers.BooleanField()


class EditionSchema(serializers.Serializer):
    edition = serializers.CharField()
    currency = serializers.CharField()
    price_policy = serializers.CharField()
    target_food_cost_ratio = DecimalText(allow_null=True)
    prices_are_metadata = serializers.BooleanField(required=False)
    net_profit = serializers.CharField(allow_null=True)
    operational_role = OperationalRoleSchema(allow_null=True)


class PriceSummarySchema(serializers.Serializer):
    id = serializers.IntegerField()
    amount = DecimalText()
    explicit_free = serializers.BooleanField()
    valid_from = serializers.DateTimeField()


class PackageSchema(serializers.Serializer):
    id = serializers.IntegerField(); food = serializers.IntegerField(); food_name = serializers.CharField()
    unit = serializers.IntegerField(); unit_name = serializers.CharField(); label = serializers.CharField()
    quantity = DecimalText(); is_reference = serializers.BooleanField()
    current_price = PriceSummarySchema(allow_null=True)


class CostLineSchema(serializers.Serializer):
    status = serializers.ChoiceField(choices=("complete", "incomplete", "needs_conversion", "invalid"))
    unrounded = DecimalText(allow_null=True); display = DecimalText(allow_null=True)
    known_subtotal = DecimalText(allow_null=True); total = DecimalText(allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField())


class CostSheetSchema(CostLineSchema):
    base_servings = DecimalText(); servings = DecimalText(); per_serving = DecimalText(allow_null=True)
    lines = CostLineSchema(many=True)


class RecipeCostSchema(CostSheetSchema):
    currency = serializers.CharField(); recipe_id = serializers.IntegerField(); saved_recipe = serializers.BooleanField()


class PriceHistoryItemSchema(serializers.Serializer):
    id = serializers.IntegerField(); amount = DecimalText(); explicit_free = serializers.BooleanField()
    valid_from = serializers.DateTimeField(); created_at = serializers.DateTimeField()
    created_by = serializers.IntegerField(); note = serializers.CharField(); is_current = serializers.BooleanField()


class PriceHistorySchema(serializers.Serializer):
    package = serializers.IntegerField(); currency = serializers.CharField(); as_of = serializers.DateTimeField()
    current_price_id = serializers.IntegerField(allow_null=True); count = serializers.IntegerField()
    next_offset = serializers.IntegerField(allow_null=True); items = PriceHistoryItemSchema(many=True)


class PriceImpactSchema(serializers.Serializer):
    recipe_id = serializers.IntegerField(); package = serializers.IntegerField(); as_of = serializers.DateTimeField()
    current_price_id = serializers.IntegerField(allow_null=True); previous_price_id = serializers.IntegerField(allow_null=True)
    affected = serializers.BooleanField(); before = CostSheetSchema(); after = CostSheetSchema()
    difference = DecimalText(allow_null=True); difference_per_serving = DecimalText(allow_null=True)
    currency = serializers.CharField(); price_policy = serializers.CharField()


class IngredientYieldRowSchema(serializers.Serializer):
    id = serializers.IntegerField(); food_name = serializers.CharField(allow_null=True); amount = DecimalText()
    unit = serializers.CharField(allow_null=True); quantity_basis = serializers.ChoiceField(choices=Ingredient._meta.get_field("quantity_basis").choices)
    yield_ratio = DecimalText(allow_null=True); is_subrecipe = serializers.BooleanField()


class IngredientYieldSchema(serializers.Serializer):
    recipe_id = serializers.IntegerField(); edition = serializers.CharField(); revision = Sha256()
    can_edit = serializers.BooleanField(); ingredients = IngredientYieldRowSchema(many=True)


class MovementSchema(serializers.Serializer):
    id = serializers.IntegerField(); kind = serializers.ChoiceField(choices=("receipt", "consume", "waste"))
    quantity = DecimalText(); entry = serializers.IntegerField(); balance = DecimalText(allow_null=True)
    reverses = serializers.IntegerField(allow_null=True); created_at = serializers.DateTimeField()
    created_by = serializers.IntegerField(); metadata_snapshot = serializers.JSONField(help_text="Versioned ledger metadata extension")


class MovementWriteSchema(serializers.Serializer):
    entry = serializers.IntegerField(required=False); kind = serializers.ChoiceField(choices=("receipt", "consume", "waste"), required=False)
    quantity = DecimalInput(required=False); idempotency_key = serializers.CharField(required=False)
    cause = serializers.CharField(required=False); reverse_of = serializers.IntegerField(required=False)


class MovementResultSchema(serializers.Serializer):
    movement_id = serializers.IntegerField(); balance = DecimalText(allow_null=True); current_balance = DecimalText()
    metadata_snapshot = serializers.JSONField(help_text="Versioned ledger metadata extension")
    kind = serializers.CharField(); reverses = serializers.IntegerField(allow_null=True)


class LegacyOrderResultSchema(serializers.Serializer):
    id = serializers.IntegerField(); stock_unchanged = serializers.BooleanField(); quantity = DecimalText()


class LegacyOrderWriteSchema(serializers.Serializer):
    food = serializers.IntegerField(required=False); unit = serializers.IntegerField(required=False); quantity = DecimalInput()
    supplier = serializers.IntegerField(required=False, allow_null=True); supplier_name = serializers.CharField(required=False, max_length=128)
    package = serializers.IntegerField(required=False, allow_null=True); offer = serializers.IntegerField(required=False, allow_null=True)
    package_count = DecimalInput(required=False, allow_null=True)


class OfferSchema(serializers.Serializer):
    id = serializers.IntegerField(); package = serializers.IntegerField(); supplier = serializers.IntegerField()
    amount = DecimalText(); explicit_free = serializers.BooleanField(); currency = serializers.CharField()
    valid_from = serializers.DateTimeField(); created_by = serializers.IntegerField(); created_at = serializers.DateTimeField()


class OrderSchema(serializers.Serializer):
    id = serializers.IntegerField(); food = serializers.IntegerField(); unit = serializers.IntegerField()
    quantity = DecimalText(); received_quantity = DecimalText(); household = serializers.IntegerField()
    supplier = serializers.IntegerField(allow_null=True); supplier_name = serializers.CharField()
    package = serializers.IntegerField(allow_null=True); package_count = DecimalText(allow_null=True)
    package_quantity_snapshot = DecimalText(allow_null=True); package_unit_snapshot = serializers.IntegerField(allow_null=True)
    price_snapshot = DecimalText(allow_null=True); currency_snapshot = serializers.CharField(allow_null=True)
    state = serializers.CharField(); ordered_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True); created_by = serializers.IntegerField(); created_at = serializers.DateTimeField()


class ReceiptSchema(serializers.Serializer):
    id = serializers.IntegerField(); order = serializers.IntegerField(); entry = serializers.IntegerField()
    quantity = DecimalText(); movement = serializers.IntegerField(); reversed_by = serializers.IntegerField(allow_null=True)
    idempotency_key = serializers.CharField(); created_by = serializers.IntegerField(); created_at = serializers.DateTimeField()


class LocationShortfallSchema(serializers.Serializer):
    location = serializers.IntegerField(); location_name = serializers.CharField(); minimum_stock = DecimalText()
    usable_stock = DecimalText(); missing = DecimalText()


class ReplenishmentItemSchema(serializers.Serializer):
    food = serializers.IntegerField(); unit = serializers.IntegerField(); required = DecimalText(); minimum_stock = DecimalText()
    target_stock = DecimalText(); location_shortfalls = LocationShortfallSchema(many=True)
    usable_stock = DecimalText(); missing = DecimalText(); package = serializers.IntegerField(allow_null=True)
    packages = DecimalText(allow_null=True); purchase_quantity = DecimalText(allow_null=True)
    reference_price = DecimalText(allow_null=True); currency = serializers.CharField()


class ReplenishmentSchema(serializers.Serializer):
    items = ReplenishmentItemSchema(many=True)


class NamedIdSchema(serializers.Serializer):
    id = serializers.IntegerField(); name = serializers.CharField()


class StockMinimumRowSchema(serializers.Serializer):
    id = serializers.IntegerField(); household = serializers.IntegerField(); food = serializers.IntegerField(); food_name = serializers.CharField()
    unit = serializers.IntegerField(); unit_name = serializers.CharField(); quantity = DecimalText()
    location = serializers.IntegerField(allow_null=True); location_name = serializers.CharField(allow_null=True)
    updated_by = serializers.IntegerField(); updated_at = serializers.DateTimeField()


class StockMinimumSchema(serializers.Serializer):
    edition = serializers.CharField(); household = NamedIdSchema(); locations = NamedIdSchema(many=True)
    items = StockMinimumRowSchema(many=True)


class ServicePlanSchema(serializers.Serializer):
    id = serializers.IntegerField(); title = serializers.CharField(); covers = DecimalText(); service_date = serializers.DateField(allow_null=True)
    state = serializers.CharField(); meal_plan = serializers.IntegerField(allow_null=True); household = serializers.IntegerField(allow_null=True)
    snapshot = serializers.JSONField(allow_null=True, help_text="Versioned historical service snapshot; schema_version is authoritative")
    confirmed_at = serializers.DateTimeField(allow_null=True); produced_at = serializers.DateTimeField(allow_null=True)
    created_by = serializers.IntegerField()


class ServiceCreateSchema(serializers.Serializer):
    covers = DecimalInput(required=False); base_covers = DecimalInput(required=False); extra = DecimalInput(required=False)
    cancelled = DecimalInput(required=False); title = serializers.CharField(required=False); service_date = serializers.DateField()
    recipe = serializers.IntegerField(required=False, allow_null=True)


class ServiceCreateResultSchema(serializers.Serializer):
    id = serializers.IntegerField(); covers = DecimalText(); meal_plan = serializers.IntegerField(); payment = serializers.CharField(allow_null=True)
    stock_changed = serializers.BooleanField(); timezone = serializers.CharField(); service_date = serializers.DateField(); state = serializers.CharField()


class ServiceActionWriteSchema(serializers.Serializer):
    action = serializers.ChoiceField(choices=("confirm", "cancel", "produce", "reverse"))
    idempotency_key = serializers.CharField(required=False)


class ServiceActionResultSchema(ServicePlanSchema):
    stock_changed = serializers.BooleanField(); movement_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    reversal_movement_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class PreparationItemSchema(serializers.Serializer):
    id = serializers.IntegerField(); source_step_id = serializers.IntegerField(allow_null=True); position = serializers.IntegerField()
    recipe_id = serializers.IntegerField(allow_null=True); name = serializers.CharField(); instruction = serializers.CharField()
    checked = serializers.BooleanField(); checked_at = serializers.DateTimeField(allow_null=True); updated_by = serializers.IntegerField(allow_null=True)


class PreparationSchema(serializers.Serializer):
    service_id = serializers.IntegerField(); state = serializers.CharField(); can_edit = serializers.BooleanField()
    revision = Sha256(); items = PreparationItemSchema(many=True)


class GraphWarningSchema(serializers.Serializer):
    code = serializers.CharField(); ingredient = serializers.IntegerField(required=False)
    recipe = serializers.IntegerField(required=False); food = serializers.CharField(required=False)


class ProductionUsageSchema(serializers.Serializer):
    component = serializers.CharField(max_length=256); quantity = DecimalInput()


class ProductionWriteSchema(serializers.Serializer):
    service_plan = serializers.IntegerField(required=False); action = serializers.ChoiceField(choices=("produce",), required=False)
    idempotency_key = serializers.CharField(required=False, max_length=128)
    usages = ProductionUsageSchema(many=True, required=False); recipe_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    edges = serializers.DictField(child=serializers.ListField(child=serializers.CharField()), required=False)
    start = serializers.CharField(required=False, max_length=256)


class ProductionNeedSchema(serializers.Serializer):
    food_id = serializers.IntegerField(); food_name = serializers.CharField(); unit_id = serializers.IntegerField(allow_null=True)
    unit_name = serializers.CharField(allow_null=True); quantity = DecimalText()


class ManualProductionResultSchema(serializers.Serializer):
    needs = serializers.DictField(child=DecimalText()); stock_changed = serializers.BooleanField()
    edges = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    warnings = GraphWarningSchema(many=True); units = serializers.DictField(child=serializers.CharField(allow_null=True))


class ServiceProductionSheetSchema(serializers.Serializer):
    service_plan = serializers.IntegerField(); state = serializers.CharField(); needs = ProductionNeedSchema(many=True)
    cost = CostSheetSchema(allow_null=True)
    warnings = serializers.ListField(child=serializers.JSONField(), help_text="Warnings retained in historical snapshots")
    stock_changed = serializers.BooleanField()


class ServiceProductionResultSchema(serializers.Serializer):
    service_plan = serializers.IntegerField(); state = serializers.CharField(); movement_ids = serializers.ListField(child=serializers.IntegerField())
    stock_changed = serializers.BooleanField()
    snapshot = serializers.JSONField(help_text="Frozen versioned service snapshot")


class RecipeYieldWriteSchema(serializers.Serializer):
    quantity = DecimalInput(); unit = serializers.IntegerField()


class RecipeYieldSchema(serializers.Serializer):
    recipe = serializers.IntegerField(); quantity = DecimalText(); unit = serializers.IntegerField()


class AllergenDeclarationSchema(serializers.Serializer):
    id = serializers.IntegerField(); name = serializers.CharField(); state = serializers.ChoiceField(choices=("declared", "unknown"))
    created_by = serializers.IntegerField(allow_null=True); created_at = serializers.DateTimeField(allow_null=True)


class AllergenFoodSchema(serializers.Serializer):
    id = serializers.IntegerField(); name = serializers.CharField(); declarations = AllergenDeclarationSchema(many=True)


class AllergenScopeSchema(serializers.Serializer):
    type = serializers.ChoiceField(choices=("food", "recipe")); id = serializers.IntegerField(); name = serializers.CharField()


class AllergenAssessmentSchema(serializers.Serializer):
    scope = AllergenScopeSchema(); assessment = serializers.ChoiceField(choices=("declared", "unknown"))
    undeclared_means_absent = serializers.BooleanField(); unknown_ingredients = serializers.BooleanField(); foods = AllergenFoodSchema(many=True)


class AllergenWriteSchema(serializers.Serializer):
    food = serializers.IntegerField(); name = serializers.CharField(max_length=128)
    state = serializers.ChoiceField(choices=("declared", "unknown"), required=False)


class AllergenWriteResultSchema(serializers.Serializer):
    id = serializers.IntegerField(); state = serializers.CharField(); created_by = serializers.IntegerField()
    created_at = serializers.DateTimeField(); undeclared_means_absent = serializers.BooleanField()


class ExchangeIngredientSchema(serializers.Serializer):
    food = serializers.CharField(); food_id = serializers.IntegerField(allow_null=True); quantity = DecimalText()
    quantity_basis = serializers.ChoiceField(choices=Ingredient._meta.get_field("quantity_basis").choices); yield_ratio = DecimalText(allow_null=True)
    unit = serializers.CharField(); unit_id = serializers.IntegerField(allow_null=True); note = serializers.CharField(allow_null=True)
    original_text = serializers.CharField(allow_null=True); is_header = serializers.BooleanField(); no_amount = serializers.BooleanField()
    food_ref = serializers.CharField(required=False, allow_null=True); unit_ref = serializers.CharField(required=False, allow_null=True)


class ExchangeStepSchema(serializers.Serializer):
    name = serializers.CharField(); instruction = serializers.CharField(); ingredients = ExchangeIngredientSchema(many=True)
    step_recipe = serializers.CharField(allow_null=True)


class ExchangeYieldSchema(serializers.Serializer):
    quantity = DecimalText(); unit_ref = serializers.CharField()


class ExchangeRecipeSchema(serializers.Serializer):
    source = serializers.CharField(required=False); external_id = serializers.CharField(); name = serializers.CharField(); description = serializers.CharField(); private = serializers.BooleanField()
    servings = DecimalText(); ingredients = ExchangeIngredientSchema(many=True, required=False)
    steps = ExchangeStepSchema(many=True)
    locals()["yield"] = ExchangeYieldSchema(allow_null=True)


class ExchangeFoodSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(); name = serializers.CharField(); recipe = serializers.CharField(allow_null=True)


class ExchangeUnitSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(); name = serializers.CharField(); base_unit = serializers.CharField(allow_null=True)
    plural_name = serializers.CharField(allow_null=True); description = serializers.CharField(allow_null=True)


class ExchangePriceSchema(serializers.Serializer):
    amount = DecimalText(); explicit_free = serializers.BooleanField(); valid_from = serializers.DateTimeField(); note = serializers.CharField()


class ExchangePackageSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(); food_ref = serializers.CharField(); unit_ref = serializers.CharField()
    quantity = DecimalText(); label = serializers.CharField(); is_reference = serializers.BooleanField(); prices = ExchangePriceSchema(many=True)


class ExchangeConversionSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(); food_ref = serializers.CharField(allow_null=True)
    base_unit_ref = serializers.CharField(); converted_unit_ref = serializers.CharField(); base_amount = DecimalText(); converted_amount = DecimalText()


class ExchangeCatalogSchema(serializers.Serializer):
    foods = ExchangeFoodSchema(many=True); units = ExchangeUnitSchema(many=True)
    packages = ExchangePackageSchema(many=True); conversions = ExchangeConversionSchema(many=True)


class ExchangeMappingSchema(serializers.Serializer):
    foods = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    units = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    packages = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    conversions = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)


class ExchangeMediaSchema(serializers.Serializer):
    included = serializers.BooleanField(); method = serializers.CharField(); url_downloads = serializers.BooleanField()


class ExchangeDocumentSchema(serializers.Serializer):
    format = serializers.ChoiceField(choices=("cuaderno-recipes-v1", "cuaderno-recipes-v2"), required=False)
    source = serializers.CharField(required=False); source_space = serializers.IntegerField(required=False)
    recipes = ExchangeRecipeSchema(many=True); catalog = ExchangeCatalogSchema(required=False)
    mapping = ExchangeMappingSchema(required=False); preview_sha256 = Sha256(required=False)
    media = ExchangeMediaSchema(required=False); warnings = serializers.ListField(child=serializers.CharField(), required=False)


class ExchangeImportIngredientSchema(serializers.Serializer):
    food = serializers.CharField(required=False, allow_blank=True); food_id = serializers.IntegerField(required=False, allow_null=True)
    food_ref = serializers.CharField(required=False, allow_null=True); quantity = DecimalInput(required=False)
    unit = serializers.CharField(required=False, allow_blank=True); unit_id = serializers.IntegerField(required=False, allow_null=True)
    unit_ref = serializers.CharField(required=False, allow_null=True); note = serializers.CharField(required=False, allow_null=True)
    original_text = serializers.CharField(required=False, allow_null=True); is_header = serializers.BooleanField(required=False)
    no_amount = serializers.BooleanField(required=False); quantity_basis = serializers.ChoiceField(choices=Ingredient._meta.get_field("quantity_basis").choices, required=False)
    yield_ratio = DecimalInput(required=False, allow_null=True)


class ExchangeImportStepSchema(serializers.Serializer):
    name = serializers.CharField(required=False); instruction = serializers.CharField(required=False)
    ingredients = ExchangeImportIngredientSchema(many=True, required=False); step_recipe = serializers.CharField(required=False, allow_null=True)


class ExchangeImportYieldSchema(serializers.Serializer):
    quantity = DecimalInput(); unit_ref = serializers.CharField()


class ExchangeImportRecipeSchema(serializers.Serializer):
    id_externo = serializers.CharField(required=False); external_id = serializers.CharField(required=False)
    name = serializers.CharField(); servings = DecimalInput(required=False); description = serializers.CharField(required=False)
    private = serializers.BooleanField(required=False); ingredients = ExchangeImportIngredientSchema(many=True, required=False)
    steps = ExchangeImportStepSchema(many=True, required=False)
    locals()["yield"] = ExchangeImportYieldSchema(required=False, allow_null=True)


class ExchangeImportFoodSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(required=False); name = serializers.CharField()
    recipe = serializers.CharField(required=False, allow_null=True)


class ExchangeImportUnitSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(required=False); name = serializers.CharField()
    base_unit = serializers.CharField(required=False, allow_null=True); plural_name = serializers.CharField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_null=True)


class ExchangeImportPriceSchema(serializers.Serializer):
    amount = DecimalInput(); explicit_free = serializers.BooleanField(); valid_from = serializers.DateTimeField()
    note = serializers.CharField(required=False)


class ExchangeImportPackageSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(required=False); food_ref = serializers.CharField(); unit_ref = serializers.CharField()
    quantity = DecimalInput(); label = serializers.CharField(); is_reference = serializers.BooleanField(); prices = ExchangeImportPriceSchema(many=True)


class ExchangeImportConversionSchema(serializers.Serializer):
    ref = serializers.CharField(); id = serializers.IntegerField(required=False); food_ref = serializers.CharField(required=False, allow_null=True)
    base_unit_ref = serializers.CharField(); converted_unit_ref = serializers.CharField(); base_amount = DecimalInput(); converted_amount = DecimalInput()


class ExchangeImportCatalogSchema(serializers.Serializer):
    foods = ExchangeImportFoodSchema(many=True, required=False); units = ExchangeImportUnitSchema(many=True, required=False)
    packages = ExchangeImportPackageSchema(many=True, required=False); conversions = ExchangeImportConversionSchema(many=True, required=False)


class ExchangeImportDocumentSchema(serializers.Serializer):
    format = serializers.ChoiceField(choices=("cuaderno-recipes-v1", "cuaderno-recipes-v2"), required=False)
    source = serializers.CharField(required=False); source_space = serializers.IntegerField(required=False)
    recipes = ExchangeImportRecipeSchema(many=True); catalog = ExchangeImportCatalogSchema(required=False)
    mapping = ExchangeMappingSchema(required=False); preview_sha256 = Sha256(required=False)
    media = ExchangeMediaSchema(required=False); warnings = serializers.ListField(child=serializers.CharField(), required=False)


class ExchangePreviewSchema(serializers.Serializer):
    count = serializers.IntegerField(); preview = ExchangeRecipeSchema(many=True); writes = serializers.IntegerField()
    preview_sha256 = Sha256(); mapping_required = serializers.BooleanField(); warnings = serializers.ListField(child=serializers.CharField())


class ExchangeImportResultSchema(serializers.Serializer):
    created = serializers.ListField(child=serializers.IntegerField()); replayed = serializers.ListField(child=serializers.IntegerField())
    rejected = serializers.ListField(child=serializers.IntegerField())


class ExportLimitSchema(serializers.Serializer):
    export_limit = serializers.CharField()
