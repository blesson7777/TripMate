from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance
from drivers.models import Driver
from trips.models import Trip
from trips.serializers import get_or_create_master_trip
from users.models import Transporter, TransporterNotification, User
from vehicles.models import Vehicle


class TripLifecycleTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="trip_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="trip.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Trip Fleet",
            address="Main Hub",
        )

        self.driver_user = User.objects.create_user(
            username="trip_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="trip.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="TRIP-LIC-01",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="TRIP-VEH-01",
            model="Trip Carrier",
            status=Vehicle.Status.ACTIVE,
        )

    def _image(self, name="odo.gif"):
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

    def _active_attendance(self):
        return Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1000,
            odo_start_image=self._image("start.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def _master_trip(self, attendance):
        return get_or_create_master_trip(attendance)

    def test_trip_list_returns_trip_images_and_live_status(self):
        attendance = self._active_attendance()
        Trip.objects.create(
            attendance=attendance,
            start_location="Day Start",
            destination="Day End",
            start_km=1000,
            start_odo_image=self._image("trip_start.gif"),
            status=Trip.Status.OPEN,
            is_day_trip=True,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(reverse("trip-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        item = response.data[0]
        self.assertTrue(item["is_live"])
        self.assertEqual(item["trip_status"], "OPEN")
        self.assertEqual(item["driver_name"], "trip_driver")
        self.assertEqual(item["vehicle_number"], "TRIP-VEH-01")
        self.assertIn("/media/trips/odo_start/", item["opening_odo_image"])

    def test_driver_cannot_start_trip_when_another_trip_is_open(self):
        attendance = self._active_attendance()
        master_trip = self._master_trip(attendance)
        Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="A",
            destination="B",
            start_km=1000,
            start_odo_image=self._image("open.gif"),
            status=Trip.Status.OPEN,
            is_day_trip=False,
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-create"),
            {
                "start_location": "C",
                "destination": "D",
                "start_km": 1010,
                "purpose": "New run",
                "start_odo_image": self._image("new_start.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("child trips are retired", str(response.data))

    def test_driver_cannot_start_retired_child_trip_workflow(self):
        self._active_attendance()

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-create"),
            {
                "start_location": "Hub A",
                "destination": "Hub B",
                "start_km": 1005,
                "purpose": "Delivery",
                "start_odo_image": self._image("trip_create.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("child trips are retired", str(response.data))

    def test_driver_cannot_start_retired_child_trip_with_open_yesterday_attendance(self):
        Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate() - timedelta(days=1),
            status=Attendance.Status.ON_DUTY,
            start_km=980,
            odo_start_image=self._image("start_yesterday.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-create"),
            {
                "start_location": "Night Start",
                "destination": "Night End",
                "start_km": 990,
                "purpose": "Post-midnight run",
                "start_odo_image": self._image("trip_yesterday.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("child trips are retired", str(response.data))

    def test_driver_cannot_start_retired_child_trip_when_attendance_ended_for_today(self):
        attendance = self._active_attendance()
        attendance.ended_at = timezone.now()
        attendance.end_km = 1020
        attendance.save(update_fields=["ended_at", "end_km"])

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-create"),
            {
                "start_location": "Emergency Start",
                "destination": "Emergency End",
                "start_km": 1021,
                "purpose": "Emergency run",
                "start_odo_image": self._image("emergency.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("child trips are retired", str(response.data))

    def test_driver_can_close_open_trip_with_end_odo(self):
        attendance = self._active_attendance()
        master_trip = self._master_trip(attendance)
        trip = Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="City A",
            destination="City B",
            start_km=1000,
            start_odo_image=self._image("open_trip.gif"),
            status=Trip.Status.OPEN,
            is_day_trip=False,
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-close", kwargs={"trip_id": trip.id}),
            {
                "end_km": 1062,
                "end_odo_image": self._image("close_trip.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.CLOSED)
        self.assertEqual(trip.end_km, 1062)
        self.assertEqual(trip.total_km, 62)
        self.assertIsNotNone(trip.end_odo_image)

    def test_only_one_master_trip_per_attendance(self):
        attendance = self._active_attendance()
        first_master = self._master_trip(attendance)
        second_master = self._master_trip(attendance)

        self.assertEqual(first_master.id, second_master.id)
        self.assertEqual(
            attendance.trips.filter(is_day_trip=True, parent_trip__isnull=True).count(),
            1,
        )

    def test_retired_child_trip_start_does_not_create_transporter_notification(self):
        self._active_attendance()
        self.client.force_authenticate(user=self.driver_user)

        response = self.client.post(
            reverse("trip-create"),
            {
                "start_location": "Warehouse",
                "destination": "Site-42",
                "start_km": 1010,
                "purpose": "Dispatch",
                "start_odo_image": self._image("start_notify.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            TransporterNotification.objects.filter(
                transporter=self.transporter,
                notification_type=TransporterNotification.Type.TRIP_STARTED,
            ).exists()
        )

    def test_trip_close_creates_transporter_notification(self):
        attendance = self._active_attendance()
        master_trip = self._master_trip(attendance)
        trip = Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="City A",
            destination="City B",
            start_km=1000,
            start_odo_image=self._image("notify_open.gif"),
            status=Trip.Status.OPEN,
            is_day_trip=False,
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("trip-close", kwargs={"trip_id": trip.id}),
            {
                "end_km": 1030,
                "end_odo_image": self._image("notify_close.gif"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = TransporterNotification.objects.filter(
            transporter=self.transporter,
            notification_type=TransporterNotification.Type.TRIP_CLOSED,
            trip=trip,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn("closed trip", notification.message.lower())

    def test_trip_lists_scope_history_by_trip_vehicle_transporter(self):
        old_transporter_user = User.objects.create_user(
            username="old_trip_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="old.trip.transporter@example.com",
        )
        old_transporter = Transporter.objects.create(
            user=old_transporter_user,
            company_name="Old Trip Fleet",
            address="Old Yard",
        )
        new_transporter_user = User.objects.create_user(
            username="new_trip_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="new.trip.transporter@example.com",
        )
        new_transporter = Transporter.objects.create(
            user=new_transporter_user,
            company_name="New Trip Fleet",
            address="New Yard",
        )
        moving_driver_user = User.objects.create_user(
            username="moving_trip_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="moving.trip.driver@example.com",
        )
        moving_driver = Driver.objects.create(
            user=moving_driver_user,
            transporter=old_transporter,
            license_number="MOVE-TRIP-01",
        )
        old_vehicle = Vehicle.objects.create(
            transporter=old_transporter,
            vehicle_number="OLD-TRIP-01",
            model="Old Carrier",
            status=Vehicle.Status.ACTIVE,
        )
        new_vehicle = Vehicle.objects.create(
            transporter=new_transporter,
            vehicle_number="NEW-TRIP-01",
            model="New Carrier",
            status=Vehicle.Status.ACTIVE,
        )
        old_attendance = Attendance.objects.create(
            driver=moving_driver,
            vehicle=old_vehicle,
            date=timezone.localdate() - timedelta(days=1),
            status=Attendance.Status.ON_DUTY,
            start_km=100,
            end_km=150,
            odo_start_image=self._image("old-attendance.gif"),
            odo_end_image=self._image("old-attendance-end.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )
        old_trip = Trip.objects.create(
            attendance=old_attendance,
            parent_trip=None,
            start_location="Old Start",
            destination="Old End",
            start_km=100,
            end_km=150,
            purpose="Old company trip",
            start_odo_image=self._image("old-trip.gif"),
            end_odo_image=self._image("old-trip-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=True,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )

        moving_driver.transporter = new_transporter
        moving_driver.assigned_vehicle = None
        moving_driver.save(update_fields=["transporter", "assigned_vehicle"])

        new_attendance = Attendance.objects.create(
            driver=moving_driver,
            vehicle=new_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=200,
            end_km=260,
            odo_start_image=self._image("new-attendance.gif"),
            odo_end_image=self._image("new-attendance-end.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )
        new_trip = Trip.objects.create(
            attendance=new_attendance,
            parent_trip=None,
            start_location="New Start",
            destination="New End",
            start_km=200,
            end_km=260,
            purpose="New company trip",
            start_odo_image=self._image("new-trip.gif"),
            end_odo_image=self._image("new-trip-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=True,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )

        self.client.force_authenticate(user=old_transporter_user)
        old_response = self.client.get(reverse("trip-list"))
        self.assertEqual(old_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in old_response.data], [old_trip.id])

        self.client.force_authenticate(user=new_transporter_user)
        new_response = self.client.get(reverse("trip-list"))
        self.assertEqual(new_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in new_response.data], [new_trip.id])

        self.client.force_authenticate(user=moving_driver_user)
        driver_response = self.client.get(reverse("trip-list"))
        self.assertEqual(driver_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in driver_response.data], [new_trip.id])
