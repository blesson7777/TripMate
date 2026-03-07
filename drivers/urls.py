from django.urls import path

from drivers.views import (
    DriverAllocationOtpRequestView,
    DriverAllocationVerifyView,
    DriverTransporterRemoveView,
    DriverVehicleAssignmentView,
    DriverListView,
)

urlpatterns = [
    path("drivers", DriverListView.as_view(), name="driver-list"),
    path(
        "drivers/allocation/request-otp",
        DriverAllocationOtpRequestView.as_view(),
        name="driver-allocation-request-otp",
    ),
    path(
        "drivers/allocation/verify",
        DriverAllocationVerifyView.as_view(),
        name="driver-allocation-verify",
    ),
    path(
        "drivers/<int:driver_id>/assign-vehicle",
        DriverVehicleAssignmentView.as_view(),
        name="driver-assign-vehicle",
    ),
    path(
        "drivers/<int:driver_id>/remove",
        DriverTransporterRemoveView.as_view(),
        name="driver-remove-from-transporter",
    ),
]
