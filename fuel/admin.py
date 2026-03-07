from django.contrib import admin

from fuel.models import FuelRecord


@admin.register(FuelRecord)
class FuelRecordAdmin(admin.ModelAdmin):
    list_display = (
        "entry_type",
        "fill_date",
        "vehicle",
        "driver",
        "indus_site_id",
        "site_name",
        "fuel_filled",
        "run_km",
    )
    list_filter = ("entry_type", "fill_date", "vehicle", "partner")
    search_fields = (
        "driver__user__username",
        "vehicle__vehicle_number",
        "indus_site_id",
        "site_name",
    )
