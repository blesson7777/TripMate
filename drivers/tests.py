from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from drivers.models import Driver
from users.models import EmailOTP, Transporter, User
from vehicles.models import Vehicle


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class DriverAllocationTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="transporter_one",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="transporter.one@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Blue Fleet",
            address="City Center",
        )
        self.transporter_vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="NEW-TRK-01",
            model="New Truck",
            status=Vehicle.Status.ACTIVE,
        )

        self.driver_user = User.objects.create_user(
            username="driver_new",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="driver.new@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=None,
            license_number="LIC-NEW-1001",
        )

    def test_transporter_can_allocate_driver_with_otp(self):
        self.client.force_authenticate(user=self.transporter_user)

        request_response = self.client.post(
            reverse("driver-allocation-request-otp"),
            {"email": self.driver_user.email},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

        otp = EmailOTP.objects.filter(
            email=self.driver_user.email,
            purpose=EmailOTP.Purpose.DRIVER_ALLOCATION,
        ).latest("created_at")

        verify_response = self.client.post(
            reverse("driver-allocation-verify"),
            {"email": self.driver_user.email, "otp": otp.code},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.transporter_id, self.transporter.id)
        self.assertEqual(
            verify_response.data["driver"]["transporter"],
            self.transporter.id,
        )

    def test_can_reallocate_driver_from_old_transporter(self):
        transporter_user_two = User.objects.create_user(
            username="transporter_two",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="transporter.two@example.com",
        )
        transporter_two = Transporter.objects.create(
            user=transporter_user_two,
            company_name="Red Fleet",
            address="Dock",
        )
        old_vehicle = Vehicle.objects.create(
            transporter=transporter_two,
            vehicle_number="OLD-TRK-01",
            model="Old Truck",
            status=Vehicle.Status.ACTIVE,
        )
        self.driver.transporter = transporter_two
        self.driver.assigned_vehicle = old_vehicle
        self.driver.save(update_fields=["transporter", "assigned_vehicle"])

        self.client.force_authenticate(user=self.transporter_user)
        request_response = self.client.post(
            reverse("driver-allocation-request-otp"),
            {"email": self.driver_user.email},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)

        otp = EmailOTP.objects.filter(
            email=self.driver_user.email,
            purpose=EmailOTP.Purpose.DRIVER_ALLOCATION,
        ).latest("created_at")

        verify_response = self.client.post(
            reverse("driver-allocation-verify"),
            {"email": self.driver_user.email, "otp": otp.code},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

        self.driver.refresh_from_db()
        self.assertEqual(self.driver.transporter_id, self.transporter.id)
        self.assertIsNone(self.driver.assigned_vehicle_id)

    def test_transporter_can_assign_and_unassign_vehicle_to_driver(self):
        self.driver.transporter = self.transporter
        self.driver.save(update_fields=["transporter"])

        self.client.force_authenticate(user=self.transporter_user)
        assign_response = self.client.patch(
            reverse("driver-assign-vehicle", kwargs={"driver_id": self.driver.id}),
            {"vehicle_id": self.transporter_vehicle.id},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.assigned_vehicle_id, self.transporter_vehicle.id)

        unassign_response = self.client.patch(
            reverse("driver-assign-vehicle", kwargs={"driver_id": self.driver.id}),
            {"vehicle_id": None},
            format="json",
        )
        self.assertEqual(unassign_response.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertIsNone(self.driver.assigned_vehicle_id)

    def test_transporter_cannot_assign_other_transporter_vehicle(self):
        transporter_user_two = User.objects.create_user(
            username="transporter_three",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="transporter.three@example.com",
        )
        transporter_three = Transporter.objects.create(
            user=transporter_user_two,
            company_name="Green Fleet",
            address="Harbor",
        )
        foreign_vehicle = Vehicle.objects.create(
            transporter=transporter_three,
            vehicle_number="FOREIGN-01",
            model="Foreign Truck",
            status=Vehicle.Status.ACTIVE,
        )
        self.driver.transporter = self.transporter
        self.driver.save(update_fields=["transporter"])

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.patch(
            reverse("driver-assign-vehicle", kwargs={"driver_id": self.driver.id}),
            {"vehicle_id": foreign_vehicle.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
