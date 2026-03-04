from django.contrib import admin

from vehicles.models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("vehicle_number", "transporter", "model", "status")
    list_filter = ("status", "transporter")
    search_fields = ("vehicle_number", "model", "transporter__company_name")
