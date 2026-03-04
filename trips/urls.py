from django.urls import path

from trips.views import TripCreateView, TripListView

urlpatterns = [
    path("trips/create", TripCreateView.as_view(), name="trip-create"),
    path("trips", TripListView.as_view(), name="trip-list"),
]
