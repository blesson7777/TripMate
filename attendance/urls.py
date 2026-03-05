from django.urls import path

from attendance.views import (
    AttendanceEndView,
    AttendanceStartView,
    DailyAttendanceMarkView,
    DailyAttendanceOverviewView,
)

urlpatterns = [
    path("attendance/start", AttendanceStartView.as_view(), name="attendance-start"),
    path("attendance/end", AttendanceEndView.as_view(), name="attendance-end"),
    path("attendance/daily", DailyAttendanceOverviewView.as_view(), name="attendance-daily"),
    path("attendance/daily/mark", DailyAttendanceMarkView.as_view(), name="attendance-daily-mark"),
]
