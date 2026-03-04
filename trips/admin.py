from django.contrib import admin

from trips.models import Trip


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("attendance", "start_location", "destination", "total_km", "created_at")
    list_filter = ("attendance__date",)
    search_fields = (
        "attendance__driver__user__username",
        "attendance__vehicle__vehicle_number",
        "start_location",
        "destination",
    )
