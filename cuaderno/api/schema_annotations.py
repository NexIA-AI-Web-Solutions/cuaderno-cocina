"""Explicit operation contracts for Cuaderno collection and detail routes."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter, OpenApiResponse, PolymorphicProxySerializer,
    extend_schema, extend_schema_view,
)

from cuaderno.api import finance, ingredient_yields, operations, preparation, price_history, purchasing, stock_minimums, views
from cuaderno.api.finance import FinanceResponseSchema, FinanceWriteSchema
from cuaderno.api.ingredient_yields import IngredientYieldWriteSerializer
from cuaderno.api.preparation import PreparationWriteSerializer
from cuaderno.api.prices import PackageWriteSerializer, PriceWriteSerializer
from cuaderno.api.purchasing import (
    OfferWriteSerializer, OrderActionSerializer, OrderWriteSerializer,
    ReceiptReverseSerializer, ReceiptWriteSerializer, ReplenishmentQuerySerializer,
)
from cuaderno.api.stock_minimums import MinimumWriteSerializer
from cuaderno.health import readiness
from cuaderno.api import schema as s
from cuaderno.api import functional_schema as fs, planning, recipe_extras, entity_media


SERVINGS = OpenApiParameter("servings", OpenApiTypes.STR, description="Decimal objetivo enviado como texto.")
LIMIT = OpenApiParameter("limit", OpenApiTypes.STR, description="Entero ASCII de 1 a 100.")
OFFSET = OpenApiParameter("offset", OpenApiTypes.STR, description="Entero ASCII no negativo.")
HOUSEHOLD = OpenApiParameter("household", OpenApiTypes.INT)
PACKAGE = OpenApiParameter("package", OpenApiTypes.STR, required=True, description="Identificador entero ASCII positivo.")
PREVIEW = OpenApiParameter("preview", OpenApiTypes.STR, enum=("1",), description="Valida y previsualiza sin escribir.")
FOOD = OpenApiParameter("food", OpenApiTypes.INT, description="Exactamente uno de food o recipe.")
RECIPE = OpenApiParameter("recipe", OpenApiTypes.INT, description="Exactamente uno de food o recipe.")

# For cookbook ShoppingListEntry update annotations.  The wire value includes
# quotes; the body ``revision`` fields used by Cuaderno preparation/yields do not.
IF_MATCH_REVISION = OpenApiParameter(
    "If-Match", OpenApiTypes.STR, location=OpenApiParameter.HEADER, required=False,
    description=('Required when PATCH changes checked; send the opaque revision including quotes, '
                 'e.g. "<64 lowercase hex>". A quoted exact updated_at is temporarily accepted for legacy clients.'),
)


def _many(serializer):
    return serializer(many=True)


def apply_schema_annotations():
    """Attach exact contracts to collection views; call once from cuaderno.urls."""
    revision = OpenApiParameter("revision", OpenApiTypes.STR, required=True,
                                description="Revisión SHA256 de la última respuesta leída.")
    operation_specs = [
        (recipe_extras.RecipeExtrasView, dict(
            get=extend_schema(operation_id="cuaderno_recipe_extras_retrieve", responses=fs.RecipeExtrasSchema),
            put=extend_schema(operation_id="cuaderno_recipe_extras_update", request=fs.RecipeExtrasWriteSchema, responses=fs.RecipeExtrasSchema))),
        (recipe_extras.RecipeFavoriteView, dict(put=extend_schema(
            operation_id="cuaderno_recipe_favorite_update", request=fs.FavoriteWriteSchema, responses=fs.FavoriteResultSchema))),
        (recipe_extras.FavoriteListView, dict(get=extend_schema(
            operation_id="cuaderno_favorites_list", parameters=[LIMIT, OFFSET], responses=fs.FavoritesSchema))),
        (recipe_extras.RecipeGalleryView, dict(post=extend_schema(
            operation_id="cuaderno_recipe_gallery_create", request={"multipart/form-data": fs.GalleryWriteSchema},
            responses={201: fs.RecipeExtrasSchema}))),
        (recipe_extras.RecipeGalleryDetailView, dict(delete=extend_schema(
            operation_id="cuaderno_recipe_gallery_destroy", responses=fs.RecipeExtrasSchema))),
        (planning.PlanningView, dict(get=extend_schema(
            operation_id="cuaderno_planning_retrieve", responses=fs.PlanningSchema,
            parameters=[OpenApiParameter("from_date", OpenApiTypes.DATE, required=True),
                        OpenApiParameter("to_date", OpenApiTypes.DATE, required=True),
                        OpenApiParameter("diet", OpenApiTypes.STR, enum=[slug for slug, _ in fs.DIETS]),
                        OpenApiParameter("diet_status", OpenApiTypes.STR, enum=fs.STATUSES)]))),
        (planning.CourseView, dict(post=extend_schema(
            operation_id="cuaderno_planning_courses_create", request=fs.CourseWriteSchema, responses={201: fs.CourseSchema}))),
        (planning.CourseDetailView, dict(
            put=extend_schema(operation_id="cuaderno_planning_courses_update", request=fs.CourseUpdateSchema, responses=fs.CourseSchema),
            delete=extend_schema(operation_id="cuaderno_planning_courses_destroy", parameters=[revision], responses={204: None}))),
        (planning.MealPlanCourseView, dict(put=extend_schema(
            operation_id="cuaderno_meal_plan_course_update", request=fs.MealCourseWriteSchema, responses=fs.PlanningMealSchema))),
        (planning.MenuTemplateView, dict(
            get=extend_schema(operation_id="cuaderno_menu_templates_list", parameters=[LIMIT, OFFSET], responses=fs.MenuTemplatesSchema),
            post=extend_schema(operation_id="cuaderno_menu_templates_create", request=fs.TemplateWriteSchema, responses={201: fs.MenuTemplateSchema}))),
        (planning.MenuTemplateDetailView, dict(
            get=extend_schema(operation_id="cuaderno_menu_template_retrieve", responses=fs.MenuTemplateSchema),
            put=extend_schema(operation_id="cuaderno_menu_template_update", request=fs.TemplateUpdateSchema, responses=fs.MenuTemplateSchema),
            delete=extend_schema(operation_id="cuaderno_menu_template_destroy", parameters=[revision], responses={204: None}))),
        (planning.MenuTemplateApplyView, dict(post=extend_schema(
            operation_id="cuaderno_menu_template_apply", request=fs.TemplateApplyWriteSchema, responses={201: fs.TemplateApplyResultSchema}))),
        (planning.CalendarEntryView, dict(post=extend_schema(
            operation_id="cuaderno_calendar_entries_create", request=fs.CalendarWriteSchema, responses={201: fs.CalendarEntrySchema}))),
        (planning.CalendarEntryDetailView, dict(
            put=extend_schema(operation_id="cuaderno_calendar_entry_update", request=fs.CalendarUpdateSchema, responses=fs.CalendarEntrySchema),
            delete=extend_schema(operation_id="cuaderno_calendar_entry_destroy", parameters=[revision], responses={204: None}))),
        (planning.MenuPrintView, dict(post=extend_schema(
            operation_id="cuaderno_menu_print", request=fs.MenuPrintWriteSchema, responses=fs.MenuPrintSchema))),
    ]
    for view, methods in operation_specs:
        extend_schema_view(**methods)(view)
    for prefix, view, content in (
        ("food", entity_media.FoodImageView, entity_media.FoodImageContentView),
        ("template", entity_media.MenuTemplateImageView, entity_media.MenuTemplateImageContentView),
    ):
        extend_schema_view(
            get=extend_schema(operation_id=f"cuaderno_{prefix}_image_retrieve", responses=fs.EntityImageResultSchema),
            put=extend_schema(operation_id=f"cuaderno_{prefix}_image_update",
                              request={"multipart/form-data": fs.EntityImageWriteSchema}, responses=fs.EntityImageResultSchema),
            delete=extend_schema(operation_id=f"cuaderno_{prefix}_image_destroy", responses=fs.EntityImageResultSchema),
        )(view)
        extend_schema_view(get=extend_schema(
            operation_id=f"cuaderno_{prefix}_image_content", responses={
                (200, "image/jpeg"): OpenApiTypes.BINARY, (200, "image/png"): OpenApiTypes.BINARY,
                (200, "image/webp"): OpenApiTypes.BINARY, (200, "image/gif"): OpenApiTypes.BINARY,
            },
        ))(content)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_edition_retrieve", responses=s.EditionSchema),
        put=extend_schema(operation_id="cuaderno_edition_update", request=s.EditionWriteSchema, responses=s.EditionSchema),
    )(views.EditionView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_packages_list", responses=_many(s.PackageSchema)),
        post=extend_schema(operation_id="cuaderno_packages_create", request=PackageWriteSerializer, responses={201: s.PackageSchema}),
    )(views.PackageListView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_package_prices_list", parameters=[LIMIT, OFFSET], responses=s.PriceHistorySchema),
        post=extend_schema(operation_id="cuaderno_package_prices_create", request=PriceWriteSerializer, responses={201: s.PriceSummarySchema}),
    )(views.PriceCreateView)
    extend_schema_view(get=extend_schema(
        operation_id="cuaderno_recipe_cost_retrieve", parameters=[SERVINGS], responses=s.RecipeCostSchema,
    ))(views.RecipeCostView)
    extend_schema_view(get=extend_schema(
        operation_id="cuaderno_recipe_price_impact_retrieve", parameters=[PACKAGE, SERVINGS], responses=s.PriceImpactSchema,
    ))(price_history.RecipePriceImpactView)

    # Finance already has exact decorators; assign explicit operation IDs only.
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_recipe_finance_retrieve", parameters=[SERVINGS], responses=FinanceResponseSchema),
        put=extend_schema(operation_id="cuaderno_recipe_finance_update", parameters=[SERVINGS], request=FinanceWriteSchema, responses=FinanceResponseSchema),
    )(finance.RecipeFinanceView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_recipe_ingredient_yields_retrieve", responses=s.IngredientYieldSchema),
        put=extend_schema(operation_id="cuaderno_recipe_ingredient_yields_update", request=IngredientYieldWriteSerializer,
                          responses={200: s.IngredientYieldSchema, 409: OpenApiResponse(description="Revision conflict"),
                                     428: OpenApiResponse(description="Revision required")}),
    )(ingredient_yields.IngredientYieldView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_movements_list", responses=_many(s.MovementSchema)),
        post=extend_schema(operation_id="cuaderno_movements_create", request=s.MovementWriteSchema, responses={201: s.MovementResultSchema}),
    )(operations.MovementView)
    extend_schema_view(post=extend_schema(
        operation_id="cuaderno_legacy_order_create", request=s.LegacyOrderWriteSchema, responses={201: s.LegacyOrderResultSchema},
    ))(operations.PurchaseOrderView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_purchase_offers_list", responses=_many(s.OfferSchema)),
        post=extend_schema(operation_id="cuaderno_purchase_offers_create", request=OfferWriteSerializer, responses={201: s.OfferSchema}),
    )(purchasing.PurchaseOfferView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_purchase_orders_list", responses=_many(s.OrderSchema)),
        post=extend_schema(operation_id="cuaderno_purchase_orders_create", request=OrderWriteSerializer, responses={201: s.OrderSchema}),
    )(purchasing.PurchaseOrderView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_purchase_receipts_list", responses=_many(s.ReceiptSchema)),
        post=extend_schema(operation_id="cuaderno_purchase_receipts_create", request=ReceiptWriteSerializer,
                           responses={200: s.ReceiptSchema, 201: s.ReceiptSchema}),
    )(purchasing.PurchaseReceiptView)
    extend_schema_view(post=extend_schema(
        operation_id="cuaderno_purchase_receipt_reverse", request=ReceiptReverseSerializer,
        responses={200: s.ReceiptSchema, 201: s.ReceiptSchema},
    ))(purchasing.PurchaseReceiptReverseView)
    extend_schema_view(post=extend_schema(
        operation_id="cuaderno_replenishment_calculate", request=ReplenishmentQuerySerializer, responses=s.ReplenishmentSchema,
    ))(purchasing.ReplenishmentView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_stock_minimums_retrieve", parameters=[HOUSEHOLD], responses=s.StockMinimumSchema),
        put=extend_schema(operation_id="cuaderno_stock_minimums_update", request=MinimumWriteSerializer, responses=s.StockMinimumSchema),
    )(stock_minimums.StockMinimumView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_services_list", responses=_many(s.ServicePlanSchema)),
        post=extend_schema(operation_id="cuaderno_services_create", request=s.ServiceCreateSchema, responses={201: s.ServiceCreateResultSchema}),
    )(operations.ServicePlanView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_service_preparation_retrieve", responses=s.PreparationSchema),
        put=extend_schema(operation_id="cuaderno_service_preparation_update", request=PreparationWriteSerializer,
                          responses={200: s.PreparationSchema, 409: OpenApiResponse(description="Revision conflict"),
                                     428: OpenApiResponse(description="Revision required")}),
    )(preparation.ServicePreparationView)
    extend_schema_view(post=extend_schema(
        operation_id="cuaderno_production_calculate", request=s.ProductionWriteSchema,
        responses=PolymorphicProxySerializer(
            component_name="CuadernoProductionResponse",
            serializers=[s.ManualProductionResultSchema, s.ServiceProductionSheetSchema, s.ServiceProductionResultSchema],
            resource_type_field_name=None,
        ),
    ))(operations.ProductionSheetView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_recipe_yield_retrieve", responses=s.RecipeYieldSchema),
        put=extend_schema(operation_id="cuaderno_recipe_yield_update", request=s.RecipeYieldWriteSchema, responses=s.RecipeYieldSchema),
    )(operations.RecipeYieldView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_allergens_assess", parameters=[FOOD, RECIPE], responses=s.AllergenAssessmentSchema),
        post=extend_schema(operation_id="cuaderno_allergens_declare", request=s.AllergenWriteSchema,
                           responses={201: s.AllergenWriteResultSchema}),
    )(operations.AllergenView)
    extend_schema_view(
        get=extend_schema(operation_id="cuaderno_exchange_export", responses={200: s.ExchangeDocumentSchema, 413: s.ExportLimitSchema}),
        post=extend_schema(operation_id="cuaderno_exchange_import", parameters=[PREVIEW], request=s.ExchangeImportDocumentSchema,
                           responses={200: s.ExchangePreviewSchema, 201: s.ExchangeImportResultSchema,
                                      409: OpenApiResponse(description="Import identity conflict")}),
    )(operations.RecipeExchangeView)


@extend_schema_view(
    get=extend_schema(operation_id="cuaderno_purchase_order_retrieve", responses=s.OrderSchema),
    post=extend_schema(operation_id="cuaderno_purchase_order_action", request=OrderActionSerializer, responses=s.OrderSchema),
)
class PurchaseOrderDetailView(purchasing.PurchaseOrderView):
    """Use only for /purchase-orders/<order_id>/ to avoid list/detail unions."""


@extend_schema_view(
    get=extend_schema(operation_id="cuaderno_service_retrieve", responses=s.ServicePlanSchema),
    post=extend_schema(operation_id="cuaderno_service_action", request=s.ServiceActionWriteSchema,
                       responses={200: s.ServiceActionResultSchema, 409: OpenApiResponse(description="Idempotency conflict")}),
)
class ServicePlanDetailView(operations.ServicePlanView):
    """Use only for /services/<plan_id>/ to avoid list/detail unions."""


readiness_schema = extend_schema(
    operation_id="cuaderno_readiness", request=None, responses={200: s.ReadySerializer, 503: s.ReadySerializer},
)(readiness)


# URL integration after apply_schema_annotations():
# path("health/ready/", readiness_schema)
# path("api/cuaderno/purchase-orders/<int:order_id>/", PurchaseOrderDetailView.as_view())
# path("api/cuaderno/services/<int:plan_id>/", ServicePlanDetailView.as_view())
