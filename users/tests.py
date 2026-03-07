from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance
from drivers.models import Driver
from fuel.models import FuelRecord
from trips.models import Trip
from users.models import (
    DriverNotification,
    EmailOTP,
    AppRelease,
    Transporter,
    TransporterNotification,
    User,
    UserDeviceToken,
)
from users.notification_utils import (
    ensure_fuel_level_alerts_for_driver,
    ensure_day_close_reminders_for_driver,
    ensure_open_trip_alerts_for_transporter,
    ensure_start_day_reminder_for_transporter,
    ensure_trip_overdue_for_driver,
    ensure_trip_overdue_for_transporter,
)
from vehicles.models import Vehicle


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

    def test_driver_profile_contains_diesel_tracking_flag(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("transporter", response.data["driver"])
        self.assertIn(
            "diesel_tracking_enabled",
            response.data["driver"]["transporter"],
        )


class AdminDieselModuleToggleTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(
            username="admin_toggle",
            password="SafePass@123",
            role=User.Role.ADMIN,
            email="admin.toggle@example.com",
        )
        self.transporter_user = User.objects.create_user(
            username="feature_partner",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="partner.toggle@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Feature Fleet",
            address="Toggle Road",
        )

    def test_admin_can_enable_diesel_module(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            reverse("admin-partner-enable-diesel-module"),
            {
                "partner_id": self.transporter.id,
                "enabled": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.transporter.refresh_from_db()
        self.assertTrue(self.transporter.diesel_tracking_enabled)

    def test_non_admin_cannot_toggle_diesel_module(self):
        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.post(
            reverse("admin-partner-enable-diesel-module"),
            {
                "partner_id": self.transporter.id,
                "enabled": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LoginWithPhoneOrEmailTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="driver_login_seed",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="driver.login@company.com",
            phone="9876543210",
        )
        Driver.objects.create(
            user=self.user,
            license_number="LIC-LOGIN-1",
        )

    def test_login_with_email(self):
        response = self.client.post(
            reverse("login"),
            {"username": "driver.login@company.com", "password": "SafePass@123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["id"], self.user.id)

    def test_login_with_phone(self):
        response = self.client.post(
            reverse("login"),
            {"username": "9876543210", "password": "SafePass@123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["id"], self.user.id)

    def test_login_with_disabled_account_returns_clear_error(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("login"),
            {"username": "driver.login@company.com", "password": "SafePass@123"},
            format="json",
        )

        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))
        self.assertIn("disabled by admin", str(response.data).lower())

    def test_login_with_forced_password_reset_returns_clear_error(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])

        response = self.client.post(
            reverse("login"),
            {"username": "9876543210", "password": "SafePass@123"},
            format="json",
        )

        self.assertIn(response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))
        self.assertIn("password reset required", str(response.data).lower())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetOtpFlowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="resettable_user",
            password="OldPass@123",
            role=User.Role.TRANSPORTER,
            email="reset@tripmate.com",
        )
        Transporter.objects.create(
            user=self.user,
            company_name="Reset Fleet",
            address="HQ",
        )

    def test_request_otp_and_reset_password(self):
        request_response = self.client.post(
            reverse("password-reset-request-otp"),
            {"email": "reset@tripmate.com"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        otp = EmailOTP.objects.filter(
            email="reset@tripmate.com",
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
        ).latest("created_at")

        reset_response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "email": "reset@tripmate.com",
                "otp": otp.code,
                "new_password": "NewPass@456",
                "confirm_password": "NewPass@456",
            },
            format="json",
        )
        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            reset_response.data["detail"],
            "Password reset successful. Please login.",
        )

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

        login_response = self.client.post(
            reverse("login"),
            {"username": "reset@tripmate.com", "password": "NewPass@456"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_forgot_password_alias_routes_work(self):
        request_response = self.client.post(
            reverse("forgot-password-request-otp"),
            {"email": "reset@tripmate.com"},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        otp = EmailOTP.objects.filter(
            email="reset@tripmate.com",
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
        ).latest("created_at")

        reset_response = self.client.post(
            reverse("forgot-password-reset"),
            {
                "email": "reset@tripmate.com",
                "otp": otp.code,
                "new_password": "AliasPass@456",
                "confirm_password": "AliasPass@456",
            },
            format="json",
        )
        self.assertEqual(reset_response.status_code, status.HTTP_200_OK)


class TransporterNotificationApiTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="notify_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="notify.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Notify Fleet",
        )
        self.driver_user = User.objects.create_user(
            username="notify_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="notify.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="NOTIFY-LIC-1",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="NOTIFY-VEH-1",
            model="Mini Truck",
            status=Vehicle.Status.ACTIVE,
        )

    def test_transporter_can_list_and_mark_notifications_read(self):
        TransporterNotification.objects.create(
            transporter=self.transporter,
            driver=self.driver,
            notification_type=TransporterNotification.Type.SYSTEM,
            title="Test",
            message="Check",
        )
        self.client.force_authenticate(user=self.transporter_user)

        list_response = self.client.get(reverse("transporter-notifications"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_response.data["unread_count"], 1)
        self.assertGreaterEqual(len(list_response.data["items"]), 1)

        mark_response = self.client.post(
            reverse("transporter-notifications-mark-read"),
            {},
            format="json",
        )
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)
        self.assertEqual(mark_response.data["unread_count"], 0)

    def test_time_based_helpers_create_reminders(self):
        morning_time = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(),
                timezone.datetime.strptime("10:15", "%H:%M").time(),
            )
        )
        ensure_start_day_reminder_for_transporter(
            self.transporter,
            current_time=morning_time,
        )
        self.assertTrue(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.START_DAY_REMINDER,
            ).exists()
        )

        attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1000,
            odo_start_image=SimpleUploadedFile(
                "start.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            latitude="10.000000",
            longitude="76.000000",
        )
        master_trip = Trip.objects.create(
            attendance=attendance,
            start_location="Day Start",
            destination="Day End",
            start_km=1000,
            start_odo_image=SimpleUploadedFile(
                "master.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            status=Trip.Status.OPEN,
            is_day_trip=True,
        )
        Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="Point A",
            destination="Point B",
            start_km=1002,
            start_odo_image=SimpleUploadedFile(
                "child.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            status=Trip.Status.OPEN,
            is_day_trip=False,
        )

        final_time = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(),
                timezone.datetime.strptime("23:50", "%H:%M").time(),
            )
        )
        ensure_open_trip_alerts_for_transporter(
            self.transporter,
            current_time=final_time,
        )
        self.assertTrue(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.OPEN_TRIP_ALERT,
            ).exists()
        )

    def test_open_run_reminders_use_5h_8h_and_final_day_end_windows(self):
        current_date = timezone.localdate()
        attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=current_date,
            status=Attendance.Status.ON_DUTY,
            start_km=1000,
            odo_start_image=SimpleUploadedFile(
                "start-reminder.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            latitude="10.000000",
            longitude="76.000000",
        )
        trip = Trip.objects.create(
            attendance=attendance,
            start_location="Day Start",
            destination="Day End",
            start_km=1000,
            start_odo_image=SimpleUploadedFile(
                "master-reminder.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            status=Trip.Status.OPEN,
            is_day_trip=True,
        )

        started_at = timezone.make_aware(
            timezone.datetime.combine(
                current_date,
                timezone.datetime.strptime("10:00", "%H:%M").time(),
            )
        )
        Trip.objects.filter(pk=trip.pk).update(started_at=started_at)
        trip.refresh_from_db()

        five_hour_time = timezone.make_aware(
            timezone.datetime.combine(
                current_date,
                timezone.datetime.strptime("15:05", "%H:%M").time(),
            )
        )
        self.assertEqual(
            ensure_trip_overdue_for_transporter(self.transporter, current_time=five_hour_time),
            1,
        )
        self.assertEqual(
            ensure_trip_overdue_for_driver(self.driver, current_time=five_hour_time),
            1,
        )
        self.assertEqual(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.TRIP_OVERDUE,
            ).count(),
            1,
        )
        self.assertEqual(
            DriverNotification.objects.filter(
                driver=self.driver,
                notification_type=DriverNotification.Type.TRIP_OVERDUE,
            ).count(),
            1,
        )

        self.assertEqual(
            ensure_trip_overdue_for_transporter(self.transporter, current_time=five_hour_time),
            0,
        )
        self.assertEqual(
            ensure_trip_overdue_for_driver(self.driver, current_time=five_hour_time),
            0,
        )

        eight_hour_time = timezone.make_aware(
            timezone.datetime.combine(
                current_date,
                timezone.datetime.strptime("18:10", "%H:%M").time(),
            )
        )
        self.assertEqual(
            ensure_trip_overdue_for_transporter(self.transporter, current_time=eight_hour_time),
            1,
        )
        self.assertEqual(
            ensure_trip_overdue_for_driver(self.driver, current_time=eight_hour_time),
            1,
        )

        self.assertFalse(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.OPEN_TRIP_ALERT,
            ).exists()
        )

        final_time = timezone.make_aware(
            timezone.datetime.combine(
                current_date,
                timezone.datetime.strptime("23:50", "%H:%M").time(),
            )
        )
        self.assertEqual(
            ensure_open_trip_alerts_for_transporter(
                self.transporter,
                current_time=final_time,
            ),
            1,
        )
        self.assertEqual(
            ensure_day_close_reminders_for_driver(
                self.driver,
                current_time=final_time,
            ),
            1,
        )
        self.assertTrue(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.OPEN_TRIP_ALERT,
                title="Final Close Reminder",
            ).exists()
        )
        self.assertTrue(
            DriverNotification.objects.filter(
                driver=self.driver,
                notification_type=DriverNotification.Type.TRIP_OVERDUE,
                title="Final Close Reminder",
            ).exists()
        )

    def test_fuel_level_alert_created_for_driver_at_evening_threshold(self):
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save(update_fields=["assigned_vehicle"])

        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1000,
            date=timezone.localdate() - timedelta(days=2),
            fill_date=timezone.localdate() - timedelta(days=2),
            meter_image=SimpleUploadedFile(
                "fuel-meter-1.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            bill_image=SimpleUploadedFile(
                "fuel-bill-1.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1500,
            date=timezone.localdate() - timedelta(days=1),
            fill_date=timezone.localdate() - timedelta(days=1),
            meter_image=SimpleUploadedFile(
                "fuel-meter-2.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            bill_image=SimpleUploadedFile(
                "fuel-bill-2.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
        )
        Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1500,
            end_km=1800,
            odo_start_image=SimpleUploadedFile(
                "fuel-attendance-start.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            odo_end_image=SimpleUploadedFile(
                "fuel-attendance-end.gif",
                (
                    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                    b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                    b"\x4c\x01\x00\x3b"
                ),
                content_type="image/gif",
            ),
            latitude="10.000000",
            longitude="76.000000",
            end_latitude="10.000000",
            end_longitude="76.000000",
            ended_at=timezone.now(),
        )

        evening_time = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(),
                timezone.datetime.strptime("18:10", "%H:%M").time(),
            )
        )
        ensure_fuel_level_alerts_for_driver(self.driver, current_time=evening_time)

        notification = DriverNotification.objects.filter(driver=self.driver).latest("created_at")
        self.assertEqual(notification.title, "Fuel Refill Reminder")
        self.assertIn("20.00 L left", notification.message)
        self.assertIn("40.00%", notification.message)


class PushTokenRegistrationTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="push_token_user",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="push.tokens@example.com",
        )
        self.client.force_authenticate(user=self.user)

    def test_registering_new_token_deactivates_older_token_for_same_variant(self):
        first_response = self.client.post(
            reverse("push-register-token"),
            {
                "token": "first-token",
                "app_variant": UserDeviceToken.AppVariant.TRANSPORTER,
                "platform": UserDeviceToken.Platform.ANDROID,
            },
            format="json",
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        second_response = self.client.post(
            reverse("push-register-token"),
            {
                "token": "second-token",
                "app_variant": UserDeviceToken.AppVariant.TRANSPORTER,
                "platform": UserDeviceToken.Platform.ANDROID,
            },
            format="json",
        )
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        active_tokens = list(
            UserDeviceToken.objects.filter(
                user=self.user,
                app_variant=UserDeviceToken.AppVariant.TRANSPORTER,
                is_active=True,
            ).values_list("token", flat=True)
        )
        self.assertEqual(active_tokens, ["second-token"])

    def test_registering_token_for_different_variant_keeps_both_active(self):
        self.client.post(
            reverse("push-register-token"),
            {
                "token": "driver-token",
                "app_variant": UserDeviceToken.AppVariant.DRIVER,
                "platform": UserDeviceToken.Platform.ANDROID,
            },
            format="json",
        )
        self.client.post(
            reverse("push-register-token"),
            {
                "token": "transporter-token",
                "app_variant": UserDeviceToken.AppVariant.TRANSPORTER,
                "platform": UserDeviceToken.Platform.ANDROID,
            },
            format="json",
        )

        self.assertEqual(
            UserDeviceToken.objects.filter(user=self.user, is_active=True).count(),
            2,
        )


class AppUpdateApiTests(APITestCase):
    def test_driver_update_endpoint_returns_active_release(self):
        AppRelease.objects.create(
            app_variant=AppRelease.AppVariant.DRIVER,
            version_name="1.2.0",
            build_number=3030,
            apk_file=SimpleUploadedFile(
                "driver_v1_2_0.apk",
                b"fake-apk-content",
                content_type="application/vnd.android.package-archive",
            ),
            force_update=False,
            message="New improvements available",
            is_active=True,
            published_at=timezone.now(),
        )

        response = self.client.get(reverse("app-update", args=["driver"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["latest_version"], "1.2.0")
        self.assertEqual(response.data["latest_build_number"], 3030)
        self.assertIn("driver_v1_2_0.apk", response.data["apk_url"])

    def test_update_endpoint_returns_not_available_when_no_release(self):
        response = self.client.get(reverse("app-update", args=["transporter"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["apk_url"], "")
