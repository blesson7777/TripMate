from django.urls import path

from tripmate import admin_dashboard_views as views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.admin_login, name="admin_login"),
    path("logout/", views.admin_logout, name="logout"),
    path("forgot-password/", views.admin_forgot_password, name="admin_forgot_password"),
    path("reset-password/", views.admin_reset_password, name="admin_reset_password"),
    path("register/", views.admin_register, name="admin_register"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.admin_settings, name="settings"),
    path("lock-screen/", views.lock_screen, name="lock_screen"),
    path("toggle-theme/", views.toggle_theme, name="toggle_theme"),
    path("users/", views.admin_users, name="admin_users"),
    path("users/<int:user_id>/", views.admin_user_details, name="admin_user_details"),
    path("users/<int:user_id>/toggle-active/", views.admin_toggle_user_active, name="admin_toggle_user_active"),
    path("users/<int:user_id>/force-password-reset/", views.admin_force_password_reset, name="admin_force_password_reset"),
    path("users/<int:user_id>/delete/", views.admin_delete_user, name="admin_delete_user"),
    path("transporters/", views.admin_transporters, name="admin_transporters"),
    path("vehicles/", views.admin_vehicles, name="admin_vehicles"),
    path("drivers/", views.admin_drivers, name="admin_drivers"),
    path("attendance/", views.admin_attendance, name="admin_attendance"),
    path("trips/", views.admin_trips, name="admin_trips"),
    path("fuel-records/", views.admin_fuel_records, name="admin_fuel_records"),
    path("reports/monthly/", views.admin_monthly_reports, name="admin_monthly_reports"),
    path("audit-logs/", views.admin_audit_logs, name="admin_audit_logs"),
    path("export/<str:report_type>/", views.admin_export_report, name="admin_export_report"),
]
