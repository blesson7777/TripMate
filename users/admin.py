from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import Transporter, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Fleet Profile", {"fields": ("role", "phone")}),
    )
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")


@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "created_at")
    search_fields = ("company_name", "user__username", "user__phone")
