from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from drivers.models import Driver
from users.models import (
    AdminBroadcastNotification,
    AppRelease,
    DriverNotification,
    EmailOTP,
    FeatureToggleLog,
    Transporter,
    TransporterNotification,
    UserDeviceToken,
    User,
)
from vehicles.models import Vehicle


class VehicleInline(admin.TabularInline):
    model = Vehicle
    extra = 0
    fields = ("vehicle_number", "model", "status", "vehicle_type")


class DriverInline(admin.TabularInline):
    model = Driver
    extra = 0
    fields = ("user", "license_number", "assigned_vehicle", "default_service", "is_active")
    autocomplete_fields = ("user", "assigned_vehicle", "default_service")


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
    list_display = ("company_name", "user", "diesel_tracking_enabled", "created_at")
    search_fields = ("company_name", "user__username", "user__phone")
    inlines = (VehicleInline, DriverInline)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "purpose", "code", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("email", "code")
    readonly_fields = ("created_at",)


@admin.register(FeatureToggleLog)
class FeatureToggleLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "admin", "partner", "feature_name", "action")
    list_filter = ("feature_name", "action")
    search_fields = ("admin__username", "partner__company_name")
    readonly_fields = ("created_at",)


@admin.register(TransporterNotification)
class TransporterNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "transporter",
        "notification_type",
        "driver",
        "trip",
        "is_read",
    )
    list_filter = ("notification_type", "is_read")
    search_fields = (
        "transporter__company_name",
        "driver__user__username",
        "title",
        "message",
    )
    readonly_fields = ("created_at",)


@admin.register(AdminBroadcastNotification)
class AdminBroadcastNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "title",
        "audience",
        "is_active",
        "created_by",
    )
    list_filter = ("audience", "is_active")
    search_fields = ("title", "message", "created_by__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DriverNotification)
class DriverNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "driver",
        "notification_type",
        "trip",
        "is_read",
    )
    list_filter = ("notification_type", "is_read")
    search_fields = ("driver__user__username", "title", "message")
    readonly_fields = ("created_at",)


@admin.register(UserDeviceToken)
class UserDeviceTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "app_variant",
        "platform",
        "is_active",
        "updated_at",
    )
    list_filter = ("app_variant", "platform", "is_active")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = ("created_at", "updated_at", "last_seen_at")


@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = (
        "app_variant",
        "version_name",
        "build_number",
        "is_active",
        "force_update",
        "published_at",
        "push_sent_at",
        "uploaded_by",
    )
    list_filter = ("app_variant", "is_active", "force_update")
    search_fields = ("version_name", "message", "build_number")
    readonly_fields = ("created_at", "updated_at", "published_at", "push_sent_at")
