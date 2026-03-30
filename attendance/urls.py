from django.urls import path

from attendance.views import (
    AttendanceEndView,
    AttendanceLocationTrackView,
    AttendanceStartView,
    DailyAttendanceMarkView,
    DriverAttendanceCalendarView,
    DailyAttendanceOverviewView,
    TransportServiceDetailView,
    TransportServiceListCreateView,
    TransporterDriverLocationsView,
)

urlpatterns = [
    path("services", TransportServiceListCreateView.as_view(), name="service-list-create"),
    path("services/<int:service_id>", TransportServiceDetailView.as_view(), name="service-detail"),
    path("attendance/start", AttendanceStartView.as_view(), name="attendance-start"),
    path("attendance/end", AttendanceEndView.as_view(), name="attendance-end"),
    path("attendance/track-location", AttendanceLocationTrackView.as_view(), name="attendance-track-location"),
    path(
        "attendance/driver-locations",
        TransporterDriverLocationsView.as_view(),
        name="attendance-driver-locations",
    ),
    path("attendance/daily", DailyAttendanceOverviewView.as_view(), name="attendance-daily"),
    path(
        "attendance/driver/<int:driver_id>/calendar",
        DriverAttendanceCalendarView.as_view(),
        name="attendance-driver-calendar",
    ),
    path("attendance/daily/mark", DailyAttendanceMarkView.as_view(), name="attendance-daily-mark"),
]
