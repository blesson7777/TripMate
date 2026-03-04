from django.contrib import admin

from fuel.models import FuelRecord


@admin.register(FuelRecord)
class FuelRecordAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "driver", "liters", "amount", "date")
    list_filter = ("date", "vehicle")
    search_fields = ("driver__user__username", "vehicle__vehicle_number")
