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

urlpatterns = [
    path("health/ready/", readiness),
    path("api/cuaderno/edition/", EditionView.as_view()),
    path("api/cuaderno/packages/", PackageListView.as_view()),
    path("api/cuaderno/packages/<int:pk>/prices/", PriceCreateView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/cost/", RecipeCostView.as_view()),
    path("api/cuaderno/movements/", MovementView.as_view()),
    path("api/cuaderno/orders/", PurchaseOrderView.as_view()),
    path("api/cuaderno/purchase-offers/", PurchaseOfferView.as_view()),
    path("api/cuaderno/purchase-orders/", PurchasingOrderView.as_view()),
    path("api/cuaderno/purchase-orders/<int:order_id>/", PurchasingOrderView.as_view()),
    path("api/cuaderno/purchase-orders/<int:order_id>/receipts/", PurchaseReceiptView.as_view()),
    path("api/cuaderno/purchase-receipts/<int:receipt_id>/reverse/", PurchaseReceiptReverseView.as_view()),
    path("api/cuaderno/replenishment/", ReplenishmentView.as_view()),
    path("api/cuaderno/services/", ServicePlanView.as_view()),
    path("api/cuaderno/services/<int:plan_id>/", ServicePlanView.as_view()),
    path("api/cuaderno/production/", ProductionSheetView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/yield/", RecipeYieldView.as_view()),
    path("api/cuaderno/allergens/", AllergenView.as_view()),
    path("api/cuaderno/exchange/", RecipeExchangeView.as_view()),
]
