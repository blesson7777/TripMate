from django.urls import path

from diesel.views import (
    TowerDieselAddView,
    TowerDieselDeleteView,
    TowerDieselListView,
    TowerDieselLogbookPhotoView,
    TowerDieselNearbySitesView,
    TowerDieselSiteListView,
    TowerDieselSiteByIdView,
    TowerDieselTripSheetPdfView,
    TowerDieselTripSheetView,
)

urlpatterns = [
    path("diesel/add", TowerDieselAddView.as_view(), name="diesel-add"),
    path("diesel", TowerDieselListView.as_view(), name="diesel-list"),
    path("diesel/sites", TowerDieselSiteListView.as_view(), name="diesel-sites"),
    path("diesel/nearby-sites", TowerDieselNearbySitesView.as_view(), name="diesel-nearby-sites"),
    path("diesel/site-by-id", TowerDieselSiteByIdView.as_view(), name="diesel-site-by-id"),
    path("diesel/<int:record_id>", TowerDieselDeleteView.as_view(), name="diesel-delete"),
    path(
        "diesel/<int:record_id>/logbook-photo",
        TowerDieselLogbookPhotoView.as_view(),
        name="diesel-logbook-photo",
    ),
    path("diesel/tripsheet", TowerDieselTripSheetView.as_view(), name="diesel-tripsheet"),
    path(
        "diesel/tripsheet/pdf",
        TowerDieselTripSheetPdfView.as_view(),
        name="diesel-tripsheet-pdf",
    ),
]
