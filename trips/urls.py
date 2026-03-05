from django.urls import path

from trips.views import TripCloseView, TripCreateView, TripDetailView, TripListView

urlpatterns = [
    path("trips/create", TripCreateView.as_view(), name="trip-create"),
    path("trips/<int:trip_id>/close", TripCloseView.as_view(), name="trip-close"),
    path("trips/<int:trip_id>/detail", TripDetailView.as_view(), name="trip-detail"),
    path("trips", TripListView.as_view(), name="trip-list"),
]
