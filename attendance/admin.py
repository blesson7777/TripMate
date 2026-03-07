from django.contrib import admin

from attendance.models import Attendance, TransportService


@admin.register(TransportService)
class TransportServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "transporter", "is_active", "updated_at")
    list_filter = ("is_active", "transporter")
    search_fields = ("name", "transporter__company_name")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "driver",
        "vehicle",
        "service_name",
        "date",
        "status",
        "start_km",
        "end_km",
    )
    list_filter = ("status", "date", "vehicle", "service_name")
    search_fields = ("driver__user__username", "vehicle__vehicle_number", "service_name")
