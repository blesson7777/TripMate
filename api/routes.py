from django.urls import path

from api.views import OptimizeRouteView

urlpatterns = [
    path("optimize-route", OptimizeRouteView.as_view(), name="optimize-route"),
]
