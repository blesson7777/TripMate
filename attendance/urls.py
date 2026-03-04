from django.urls import path

from attendance.views import AttendanceEndView, AttendanceStartView

urlpatterns = [
    path("attendance/start", AttendanceStartView.as_view(), name="attendance-start"),
    path("attendance/end", AttendanceEndView.as_view(), name="attendance-end"),
]
