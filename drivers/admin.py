from django.contrib import admin

from drivers.models import Driver


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("user", "transporter", "license_number", "assigned_vehicle", "is_active")
    list_filter = ("is_active", "transporter")
    search_fields = ("user__username", "license_number", "assigned_vehicle__vehicle_number")
    autocomplete_fields = ("user", "transporter", "assigned_vehicle")
