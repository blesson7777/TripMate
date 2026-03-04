from django.urls import path

from drivers.views import DriverListView

urlpatterns = [
    path("drivers", DriverListView.as_view(), name="driver-list"),
]
