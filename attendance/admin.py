from django.contrib import admin

from attendance.models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("driver", "vehicle", "date", "status", "start_km", "end_km")
    list_filter = ("status", "date", "vehicle")
    search_fields = ("driver__user__username", "vehicle__vehicle_number")
