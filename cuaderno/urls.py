from django.urls import path

from cuaderno.api.operations import (
    AllergenView,
    MovementView,
    ProductionSheetView,
    PurchaseOrderView,
    RecipeExchangeView,
    ReplenishmentView,
    ServicePlanView,
)
from cuaderno.api.views import EditionView, PackageListView, PriceCreateView, RecipeCostView

urlpatterns = [
    path("api/cuaderno/edition/", EditionView.as_view()),
    path("api/cuaderno/packages/", PackageListView.as_view()),
    path("api/cuaderno/packages/<int:pk>/prices/", PriceCreateView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/cost/", RecipeCostView.as_view()),
    path("api/cuaderno/movements/", MovementView.as_view()),
    path("api/cuaderno/orders/", PurchaseOrderView.as_view()),
    path("api/cuaderno/replenishment/", ReplenishmentView.as_view()),
    path("api/cuaderno/services/", ServicePlanView.as_view()),
    path("api/cuaderno/production/", ProductionSheetView.as_view()),
    path("api/cuaderno/allergens/", AllergenView.as_view()),
    path("api/cuaderno/exchange/", RecipeExchangeView.as_view()),
]
