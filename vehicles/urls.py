from django.urls import path

from vehicles.views import VehicleListView

urlpatterns = [
    path("vehicles", VehicleListView.as_view(), name="vehicle-list"),
]
