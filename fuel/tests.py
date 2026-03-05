from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance
from drivers.models import Driver
from users.models import Transporter, User
from vehicles.models import Vehicle


class FuelRecordTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="fuel_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="fuel.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Fuel Fleet",
            address="Yard",
        )

        self.driver_user = User.objects.create_user(
            username="fuel_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="fuel.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="FUEL-LIC-01",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="FUEL-VEH-01",
            model="Fuel Van",
            status=Vehicle.Status.ACTIVE,
        )
        Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1200,
            odo_start_image=self._image("start.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def _image(self, name):
        return SimpleUploadedFile(
            name,
            (
                b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                b"\x4c\x01\x00\x3b"
            ),
            content_type="image/gif",
        )

    def test_fuel_add_saves_odometer_km(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "15.50",
                "amount": "1850.00",
                "odometer_km": 1234,
                "meter_image": self._image("meter.gif"),
                "bill_image": self._image("bill.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["odometer_km"], 1234)

    def test_fuel_add_requires_odometer_km(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "10.00",
                "amount": "1000.00",
                "meter_image": self._image("meter.gif"),
                "bill_image": self._image("bill.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("odometer_km", response.data)

    def test_fuel_add_allowed_when_attendance_already_ended_for_today(self):
        attendance = Attendance.objects.get(driver=self.driver, date=timezone.localdate())
        attendance.ended_at = timezone.now()
        attendance.end_km = 1215
        attendance.save(update_fields=["ended_at", "end_km"])

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "8.00",
                "amount": "900.00",
                "odometer_km": 1216,
                "meter_image": self._image("meter2.gif"),
                "bill_image": self._image("bill2.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["odometer_km"], 1216)
