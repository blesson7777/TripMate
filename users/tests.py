from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from drivers.models import Driver
from users.models import EmailOTP, Transporter, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TransporterRegisterOtpFlowTests(APITestCase):
    def test_request_otp_sends_email_and_stores_record(self):
        response = self.client.post(
            reverse("transporter-request-otp"),
            {"email": "transporter@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "transporter@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("OTP is", mail.outbox[0].body)
        self.assertTrue(
            EmailOTP.objects.filter(
                email="transporter@example.com",
                purpose=EmailOTP.Purpose.TRANSPORTER_SIGNUP,
                is_used=False,
            ).exists()
        )

    def test_register_transporter_with_valid_otp(self):
        self.client.post(
            reverse("transporter-request-otp"),
            {"email": "verified@example.com"},
            format="json",
        )
        otp = EmailOTP.objects.filter(email="verified@example.com").latest("created_at")

        response = self.client.post(
            reverse("transporter-register"),
            {
                "username": "newtransporter",
                "password": "SafePass@123",
                "confirm_password": "SafePass@123",
                "email": "verified@example.com",
                "otp": otp.code,
                "phone": "9999999999",
                "company_name": "Swift Logistics",
                "address": "Kolkata",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], User.Role.TRANSPORTER)

        user = User.objects.get(username="newtransporter")
        self.assertEqual(user.role, User.Role.TRANSPORTER)
        self.assertTrue(Transporter.objects.filter(user=user).exists())
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DriverRegisterOtpFlowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="transporterseed",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="seed@company.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Fleet Seed Co",
            address="HQ",
        )

    def test_public_transporter_list(self):
        response = self.client.get(reverse("transporter-public-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["company_name"], "Fleet Seed Co")

    def test_register_driver_with_valid_otp(self):
        self.client.post(
            reverse("driver-request-otp"),
            {"email": "driver@example.com"},
            format="json",
        )
        otp = EmailOTP.objects.filter(email="driver@example.com").latest("created_at")

        response = self.client.post(
            reverse("driver-register"),
            {
                "username": "driverone",
                "password": "SafePass@123",
                "confirm_password": "SafePass@123",
                "email": "driver@example.com",
                "otp": otp.code,
                "phone": "9999999999",
                "license_number": "LIC-12345",
                "transporter_id": self.transporter.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], User.Role.DRIVER)

        user = User.objects.get(username="driverone")
        self.assertTrue(Driver.objects.filter(user=user).exists())
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_register_driver_without_transporter(self):
        self.client.post(
            reverse("driver-request-otp"),
            {"email": "unassigned.driver@example.com"},
            format="json",
        )
        otp = EmailOTP.objects.filter(email="unassigned.driver@example.com").latest(
            "created_at"
        )

        response = self.client.post(
            reverse("driver-register"),
            {
                "username": "unassigned_driver",
                "password": "SafePass@123",
                "confirm_password": "SafePass@123",
                "email": "unassigned.driver@example.com",
                "otp": otp.code,
                "license_number": "LIC-UNASSIGNED-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        driver = Driver.objects.get(user__username="unassigned_driver")
        self.assertIsNone(driver.transporter_id)


class ProfileAndPasswordTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="transporter_admin",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="transporter@company.com",
            phone="9000000001",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="North Fleet",
            address="Main Road",
        )
        self.driver_user = User.objects.create_user(
            username="driver_profile",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="driver@company.com",
            phone="9000000002",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="LIC-9999",
        )

    def test_driver_profile_read_and_update(self):
        self.client.force_authenticate(user=self.driver_user)

        get_response = self.client.get(reverse("profile"))
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["user"]["username"], "driver_profile")
        self.assertEqual(get_response.data["driver"]["license_number"], "LIC-9999")

        patch_response = self.client.patch(
            reverse("profile"),
            {
                "username": "driver_profile_new",
                "phone": "9888888888",
                "license_number": "LIC-8888",
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["user"]["username"], "driver_profile_new")
        self.assertEqual(patch_response.data["driver"]["license_number"], "LIC-8888")

    def test_transporter_profile_update(self):
        self.client.force_authenticate(user=self.transporter_user)

        response = self.client.patch(
            reverse("profile"),
            {
                "company_name": "North Fleet Updated",
                "address": "Updated Address",
                "phone": "9777777777",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transporter"]["company_name"], "North Fleet Updated")
        self.assertEqual(response.data["user"]["phone"], "9777777777")

    def test_change_password_requires_current_password(self):
        self.client.force_authenticate(user=self.driver_user)

        bad_response = self.client.post(
            reverse("profile-change-password"),
            {
                "current_password": "wrong-password",
                "new_password": "NewStrong@123",
                "confirm_password": "NewStrong@123",
            },
            format="json",
        )
        self.assertEqual(bad_response.status_code, status.HTTP_400_BAD_REQUEST)

        good_response = self.client.post(
            reverse("profile-change-password"),
            {
                "current_password": "SafePass@123",
                "new_password": "NewStrong@123",
                "confirm_password": "NewStrong@123",
            },
            format="json",
        )
        self.assertEqual(good_response.status_code, status.HTTP_200_OK)
        self.assertEqual(good_response.data["detail"], "Password updated successfully.")
