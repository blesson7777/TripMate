from django.urls import path

from users.views import (
    AdminPartnerDieselToggleView,
    AppUpdateView,
    ChangePasswordView,
    DriverNotificationListView,
    DriverNotificationMarkReadView,
    DriverOtpRequestView,
    DriverRegisterView,
    LoginView,
    PasswordResetConfirmView,
    PasswordResetOtpRequestView,
    ProfileView,
    PushTokenRegisterView,
    PushTokenUnregisterView,
    TransporterNotificationListView,
    TransporterNotificationMarkReadView,
    TransporterOtpRequestView,
    TransporterPublicListView,
    TransporterRegisterView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("profile", ProfileView.as_view(), name="profile"),
    path("profile/change-password", ChangePasswordView.as_view(), name="profile-change-password"),
    path(
        "notifications",
        TransporterNotificationListView.as_view(),
        name="transporter-notifications",
    ),
    path(
        "notifications/mark-read",
        TransporterNotificationMarkReadView.as_view(),
        name="transporter-notifications-mark-read",
    ),
    path(
        "driver/notifications",
        DriverNotificationListView.as_view(),
        name="driver-notifications",
    ),
    path(
        "driver/notifications/mark-read",
        DriverNotificationMarkReadView.as_view(),
        name="driver-notifications-mark-read",
    ),
    path(
        "admin/partner/enable_diesel_module",
        AdminPartnerDieselToggleView.as_view(),
        name="admin-partner-enable-diesel-module-underscore",
    ),
    path(
        "admin/partner/enable-diesel-module",
        AdminPartnerDieselToggleView.as_view(),
        name="admin-partner-enable-diesel-module",
    ),
    path("transporters/public", TransporterPublicListView.as_view(), name="transporter-public-list"),
    path("transporter/request-otp", TransporterOtpRequestView.as_view(), name="transporter-request-otp"),
    path("transporter/register", TransporterRegisterView.as_view(), name="transporter-register"),
    path("driver/request-otp", DriverOtpRequestView.as_view(), name="driver-request-otp"),
    path("driver/register", DriverRegisterView.as_view(), name="driver-register"),
    path("push/register-token", PushTokenRegisterView.as_view(), name="push-register-token"),
    path("push/unregister-token", PushTokenUnregisterView.as_view(), name="push-unregister-token"),
    path("app-update/<str:app_variant>", AppUpdateView.as_view(), name="app-update"),
    path(
        "password/request-otp",
        PasswordResetOtpRequestView.as_view(),
        name="password-reset-request-otp",
    ),
    path(
        "password/request-otp/",
        PasswordResetOtpRequestView.as_view(),
        name="password-reset-request-otp-slash",
    ),
    path(
        "password/reset",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "password/reset/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm-slash",
    ),
    path(
        "forgot-password/request-otp",
        PasswordResetOtpRequestView.as_view(),
        name="forgot-password-request-otp",
    ),
    path(
        "forgot-password/request-otp/",
        PasswordResetOtpRequestView.as_view(),
        name="forgot-password-request-otp-slash",
    ),
    path(
        "forgot-password/reset",
        PasswordResetConfirmView.as_view(),
        name="forgot-password-reset",
    ),
    path(
        "forgot-password/reset/",
        PasswordResetConfirmView.as_view(),
        name="forgot-password-reset-slash",
    ),
]
