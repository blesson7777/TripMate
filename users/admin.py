from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from drivers.models import Driver
from users.models import EmailOTP, Transporter, User
from vehicles.models import Vehicle


class VehicleInline(admin.TabularInline):
    model = Vehicle
    extra = 0
    fields = ("vehicle_number", "model", "status")


class DriverInline(admin.TabularInline):
    model = Driver
    extra = 0
    fields = ("user", "license_number", "assigned_vehicle", "is_active")
    autocomplete_fields = ("user", "assigned_vehicle")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Fleet Profile", {"fields": ("role", "phone")}),
    )
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "phone")


@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "created_at")
    search_fields = ("company_name", "user__username", "user__phone")
    inlines = (VehicleInline, DriverInline)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "purpose", "code", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("email", "code")
    readonly_fields = ("created_at",)
