from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance, DriverDailyAttendanceMark
from drivers.models import Driver
from trips.models import Trip
from users.models import Transporter, User
from vehicles.models import Vehicle


class DailyAttendanceWorkflowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="attendance_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="attendance.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Attendance Fleet",
            address="Central Yard",
        )

        self.driver_user = User.objects.create_user(
            username="attendance_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="attendance.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="ATT-LIC-01",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="ATT-VEH-01",
            model="Attendance Van",
            status=Vehicle.Status.ACTIVE,
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save(update_fields=["assigned_vehicle"])

    def _odo_image(self):
        return SimpleUploadedFile(
            "odo.gif",
            (
                b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                b"\x4c\x01\x00\x3b"
            ),
            content_type="image/gif",
        )

    def test_daily_overview_defaults_absent_when_not_marked(self):
        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(reverse("attendance-daily"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], timezone.localdate())
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["status"], "ABSENT")
        self.assertTrue(response.data["items"][0]["can_start_day"])

    def test_driver_start_auto_marks_present(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 100,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "ON_DUTY")
        self.assertEqual(response.data["trips_count"], 1)

        mark = DriverDailyAttendanceMark.objects.get(
            driver=self.driver,
            date=timezone.localdate(),
        )
        self.assertEqual(mark.status, DriverDailyAttendanceMark.Status.PRESENT)

    def test_transporter_mark_present_allows_driver_start(self):
        self.client.force_authenticate(user=self.transporter_user)
        mark_response = self.client.post(
            reverse("attendance-daily-mark"),
            {
                "driver_id": self.driver.id,
                "status": "PRESENT",
            },
            format="json",
        )
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.driver_user)
        start_response = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 120,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(start_response.data["status"], "ON_DUTY")
        self.assertEqual(start_response.data["trips_count"], 1)

    def test_mark_absent_blocks_driver_start(self):
        self.client.force_authenticate(user=self.transporter_user)
        mark_response = self.client.post(
            reverse("attendance-daily-mark"),
            {
                "driver_id": self.driver.id,
                "status": "ABSENT",
            },
            format="json",
        )
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.driver_user)
        start_response = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 130,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )
        self.assertEqual(start_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marked you absent", str(start_response.data))

    def test_cannot_mark_absent_after_start_day(self):
        self.client.force_authenticate(user=self.transporter_user)
        self.client.post(
            reverse("attendance-daily-mark"),
            {
                "driver_id": self.driver.id,
                "status": "PRESENT",
            },
            format="json",
        )

        self.client.force_authenticate(user=self.driver_user)
        self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 140,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )

        self.client.force_authenticate(user=self.transporter_user)
        absent_response = self.client.post(
            reverse("attendance-daily-mark"),
            {
                "driver_id": self.driver.id,
                "status": "ABSENT",
            },
            format="json",
        )
        self.assertEqual(absent_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_end_day_creates_auto_trip_from_opening_closing_km(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 200,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 245,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(end_response.status_code, status.HTTP_200_OK)
        self.assertEqual(end_response.data["status"], "ON_DUTY")
        self.assertEqual(end_response.data["trips_count"], 1)

        attendance = Attendance.objects.get(driver=self.driver, date=timezone.localdate())
        trip = Trip.objects.get(attendance=attendance)
        self.assertEqual(trip.start_km, 200)
        self.assertEqual(trip.end_km, 245)
        self.assertEqual(trip.total_km, 45)
        self.assertEqual(trip.start_location, "Day Start")
        self.assertEqual(trip.destination, "Day End")

    def test_end_day_with_same_opening_closing_km_keeps_no_trip(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 320,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
            },
            format="multipart",
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(start_response.data["trips_count"], 1)

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 320,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(end_response.status_code, status.HTTP_200_OK)
        self.assertEqual(end_response.data["status"], "ON_DUTY")
        self.assertEqual(end_response.data["trips_count"], 1)
