from django.urls import path

from users.views import (
    ChangePasswordView,
    DriverOtpRequestView,
    DriverRegisterView,
    LoginView,
    ProfileView,
    TransporterOtpRequestView,
    TransporterPublicListView,
    TransporterRegisterView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("profile", ProfileView.as_view(), name="profile"),
    path("profile/change-password", ChangePasswordView.as_view(), name="profile-change-password"),
    path("transporters/public", TransporterPublicListView.as_view(), name="transporter-public-list"),
    path("transporter/request-otp", TransporterOtpRequestView.as_view(), name="transporter-request-otp"),
    path("transporter/register", TransporterRegisterView.as_view(), name="transporter-register"),
    path("driver/request-otp", DriverOtpRequestView.as_view(), name="driver-request-otp"),
    path("driver/register", DriverRegisterView.as_view(), name="driver-register"),
]
