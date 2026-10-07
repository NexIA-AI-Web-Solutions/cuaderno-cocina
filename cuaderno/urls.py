from django.urls import path

from cuaderno.api.operations import (
    AllergenView,
    MovementView,
    ProductionSheetView,
    PurchaseOrderView,
    RecipeExchangeView,
    RecipeYieldView,
    ServicePlanView,
)
from cuaderno.api.views import EditionView, PackageListView, PriceCreateView, RecipeCostView
from cuaderno.api.purchasing import (
    PurchaseOfferView,
    PurchaseOrderView as PurchasingOrderView,
    PurchaseReceiptView,
    PurchaseReceiptReverseView,
    ReplenishmentView,
)
from cuaderno.health import readiness
from cuaderno.api.finance import RecipeFinanceView
from cuaderno.api.ingredient_yields import IngredientYieldView
from cuaderno.api.stock_minimums import StockMinimumView
from cuaderno.api.price_history import RecipePriceImpactView
from cuaderno.api.preparation import ServicePreparationView
from cuaderno.api.schema_annotations import (
    PurchaseOrderDetailView, ServicePlanDetailView, apply_schema_annotations,
)
from cuaderno.api.recipe_extras import FavoriteListView, RecipeExtrasView, RecipeFavoriteView, RecipeGalleryView, RecipeGalleryDetailView
from cuaderno.api.planning import (
    CalendarEntryView, CourseView, MealPlanCourseView, MenuPrintView,
    MenuTemplateApplyView, MenuTemplateView, PlanningView,
    CalendarEntryDetailView, CourseDetailView, MenuTemplateDetailView,
)

apply_schema_annotations()

urlpatterns = [
    path("api/cuaderno/recipes/<int:recipe_id>/extras/", RecipeExtrasView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/favorite/", RecipeFavoriteView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/gallery/", RecipeGalleryView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/gallery/<int:image_id>/", RecipeGalleryDetailView.as_view()),
    path("api/cuaderno/favorites/", FavoriteListView.as_view()),
    path("api/cuaderno/planning/", PlanningView.as_view()),
    path("api/cuaderno/planning/courses/", CourseView.as_view()),
    path("api/cuaderno/planning/courses/<int:course_id>/", CourseDetailView.as_view()),
    path("api/cuaderno/planning/meal-plans/<int:meal_plan_id>/", MealPlanCourseView.as_view()),
    path("api/cuaderno/planning/templates/", MenuTemplateView.as_view()),
    path("api/cuaderno/planning/templates/<int:template_id>/", MenuTemplateDetailView.as_view()),
    path("api/cuaderno/planning/templates/<int:template_id>/apply/", MenuTemplateApplyView.as_view()),
    path("api/cuaderno/planning/events/", CalendarEntryView.as_view()),
    path("api/cuaderno/planning/events/<int:entry_id>/", CalendarEntryDetailView.as_view()),
    path("api/cuaderno/planning/print/", MenuPrintView.as_view()),
    path("health/ready/", readiness),
    path("api/cuaderno/edition/", EditionView.as_view()),
    path("api/cuaderno/packages/", PackageListView.as_view()),
    path("api/cuaderno/packages/<int:pk>/prices/", PriceCreateView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/cost/", RecipeCostView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/price-impact/", RecipePriceImpactView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/finance/", RecipeFinanceView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/ingredient-yields/", IngredientYieldView.as_view()),
    path("api/cuaderno/movements/", MovementView.as_view()),
    path("api/cuaderno/orders/", PurchaseOrderView.as_view()),
    path("api/cuaderno/purchase-offers/", PurchaseOfferView.as_view()),
    path("api/cuaderno/purchase-orders/", PurchasingOrderView.as_view()),
    path("api/cuaderno/purchase-orders/<int:order_id>/", PurchaseOrderDetailView.as_view()),
    path("api/cuaderno/purchase-orders/<int:order_id>/receipts/", PurchaseReceiptView.as_view()),
    path("api/cuaderno/purchase-receipts/<int:receipt_id>/reverse/", PurchaseReceiptReverseView.as_view()),
    path("api/cuaderno/replenishment/", ReplenishmentView.as_view()),
    path("api/cuaderno/stock-minimums/", StockMinimumView.as_view()),
    path("api/cuaderno/services/", ServicePlanView.as_view()),
    path("api/cuaderno/services/<int:plan_id>/", ServicePlanDetailView.as_view()),
    path("api/cuaderno/services/<int:plan_id>/preparation/", ServicePreparationView.as_view()),
    path("api/cuaderno/production/", ProductionSheetView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/yield/", RecipeYieldView.as_view()),
    path("api/cuaderno/allergens/", AllergenView.as_view()),
    path("api/cuaderno/exchange/", RecipeExchangeView.as_view()),
]
