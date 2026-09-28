from django.urls import path

from cuaderno.api.views import EditionView, PackageListView, PriceCreateView, RecipeCostView

urlpatterns = [
    path("api/cuaderno/edition/", EditionView.as_view()),
    path("api/cuaderno/packages/", PackageListView.as_view()),
    path("api/cuaderno/packages/<int:pk>/prices/", PriceCreateView.as_view()),
    path("api/cuaderno/recipes/<int:recipe_id>/cost/", RecipeCostView.as_view()),
]
