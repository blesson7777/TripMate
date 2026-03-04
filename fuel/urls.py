from django.urls import path

from fuel.views import FuelAddView, FuelRecordListView

urlpatterns = [
    path("fuel/add", FuelAddView.as_view(), name="fuel-add"),
    path("fuel", FuelRecordListView.as_view(), name="fuel-list"),
]
