from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import (
    Attendance,
    AttendanceLocationPoint,
    DriverDailyAttendanceMark,
    TransportService,
)
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
        self.driver_two_user = User.objects.create_user(
            username="attendance_driver_two",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="attendance.driver.two@example.com",
        )
        self.driver_two = Driver.objects.create(
            user=self.driver_two_user,
            transporter=self.transporter,
            license_number="ATT-LIC-02",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="ATT-VEH-01",
            model="Attendance Van",
            status=Vehicle.Status.ACTIVE,
        )
        self.vehicle_two = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="ATT-VEH-02",
            model="Attendance Van 2",
            status=Vehicle.Status.ACTIVE,
        )
        self.service = TransportService.objects.create(
            transporter=self.transporter,
            name="DTM Vehicle",
            description="Daily transport duty",
            is_active=True,
        )
        self.service_two = TransportService.objects.create(
            transporter=self.transporter,
            name="Generator Vehicle",
            description="Secondary duty",
            is_active=True,
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

    def _start_day(self, start_km: int, vehicle_id: int | None = None, service_id: int | None = None):
        return self.client.post(
            reverse("attendance-start"),
            {
                "start_km": start_km,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": vehicle_id or self.vehicle.id,
                "service_id": service_id or self.service.id,
            },
            format="multipart",
        )

    def test_daily_overview_defaults_no_duty_when_not_marked(self):
        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(reverse("attendance-daily"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], timezone.localdate())
        self.assertEqual(len(response.data["items"]), 2)
        first_item = next(
            item for item in response.data["items"] if item["driver_id"] == self.driver.id
        )
        self.assertEqual(first_item["status"], "NO_DUTY")
        self.assertTrue(first_item["can_start_day"])

    def test_driver_start_auto_marks_present(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self._start_day(start_km=100)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "ON_DUTY")
        self.assertEqual(response.data["trips_count"], 1)
        self.assertTrue(
            AttendanceLocationPoint.objects.filter(
                attendance_id=response.data["id"],
                point_type=AttendanceLocationPoint.PointType.START,
            ).exists()
        )

        mark = DriverDailyAttendanceMark.objects.get(
            driver=self.driver,
            transporter=self.transporter,
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
        start_response = self._start_day(start_km=120)
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
        start_response = self._start_day(start_km=130)
        self.assertEqual(start_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marked you absent", str(start_response.data))

    def test_mark_leave_blocks_driver_start(self):
        self.client.force_authenticate(user=self.transporter_user)
        mark_response = self.client.post(
            reverse("attendance-daily-mark"),
            {
                "driver_id": self.driver.id,
                "status": "LEAVE",
            },
            format="json",
        )
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=131)
        self.assertEqual(start_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("absent/leave", str(start_response.data))

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
        self._start_day(start_km=140)

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

    def test_end_day_creates_auto_trip_from_opening_closing_km_and_keeps_present(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=200)
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 245,
                "odo_end_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
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
        self.assertTrue(
            AttendanceLocationPoint.objects.filter(
                attendance=attendance,
                point_type=AttendanceLocationPoint.PointType.END,
            ).exists()
        )

    def test_driver_can_record_live_tracking_point_for_active_run(self):
        self.client.force_authenticate(user=self.driver_user)
        self._start_day(start_km=210)

        response = self.client.post(
            reverse("attendance-track-location"),
            {
                "latitude": "22.573001",
                "longitude": "88.364401",
                "accuracy_m": "8.50",
                "speed_kph": "18.75",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        point = AttendanceLocationPoint.objects.filter(
            driver=self.driver,
            point_type=AttendanceLocationPoint.PointType.TRACK,
        ).latest("recorded_at")
        self.assertEqual(str(point.latitude), "22.573001")
        self.assertEqual(str(point.longitude), "88.364401")

    def test_tracking_point_rejected_when_transporter_location_monitoring_disabled(self):
        self.transporter.location_tracking_enabled = False
        self.transporter.save(update_fields=["location_tracking_enabled"])
        self.client.force_authenticate(user=self.driver_user)
        self._start_day(start_km=211)

        response = self.client.post(
            reverse("attendance-track-location"),
            {
                "latitude": "22.573001",
                "longitude": "88.364401",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("disabled", str(response.data).lower())

    def test_tracking_point_rejected_without_active_run(self):
        self.client.force_authenticate(user=self.driver_user)

        response = self.client.post(
            reverse("attendance-track-location"),
            {
                "latitude": "22.573001",
                "longitude": "88.364401",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transporter_driver_locations_endpoint_returns_only_own_fleet_points(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=500)
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        track_response = self.client.post(
            reverse("attendance-track-location"),
            {
                "latitude": "22.573500",
                "longitude": "88.364900",
                "accuracy_m": "6.50",
                "speed_kph": "12.00",
            },
            format="json",
        )
        self.assertEqual(track_response.status_code, status.HTTP_201_CREATED)

        other_transporter_user = User.objects.create_user(
            username="attendance_other_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="attendance.other.transporter@example.com",
        )
        other_transporter = Transporter.objects.create(
            user=other_transporter_user,
            company_name="Other Fleet",
        )
        other_driver_user = User.objects.create_user(
            username="attendance_other_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="attendance.other.driver@example.com",
        )
        other_driver = Driver.objects.create(
            user=other_driver_user,
            transporter=other_transporter,
            license_number="ATT-OTHER-LIC",
        )
        other_vehicle = Vehicle.objects.create(
            transporter=other_transporter,
            vehicle_number="ATT-OTHER-VEH",
            model="Other Truck",
            status=Vehicle.Status.ACTIVE,
        )
        other_attendance = Attendance.objects.create(
            driver=other_driver,
            vehicle=other_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=None,
            service_name="Unspecified Service",
            start_km=10,
            odo_start_image=self._odo_image(),
            latitude="23.100001",
            longitude="87.100001",
        )
        AttendanceLocationPoint.objects.create(
            attendance=other_attendance,
            transporter=other_transporter,
            driver=other_driver,
            vehicle=other_vehicle,
            point_type=AttendanceLocationPoint.PointType.START,
            latitude="23.100001",
            longitude="87.100001",
            recorded_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("attendance-driver-locations"),
            {"date": timezone.localdate().isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        map_points = response.data.get("map_points") or []
        self.assertTrue(any(point.get("driver_id") == self.driver.id for point in map_points))
        self.assertFalse(any(point.get("driver_id") == other_driver.id for point in map_points))

    def test_driver_cannot_access_transporter_driver_locations_endpoint(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(reverse("attendance-driver-locations"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_end_day_with_same_opening_closing_km_keeps_present(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=320)
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

    def test_end_day_run_km_above_300_requires_confirmation(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=1000)
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 1351,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )

        self.assertEqual(end_response.status_code, status.HTTP_400_BAD_REQUEST)
        detail = end_response.data.get("detail") or ""
        if isinstance(detail, list) and detail:
            detail = str(detail[0])
        self.assertIn("confirm_large_run", str(detail).lower())

        confirmed_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 1351,
                "confirm_large_run": "true",
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )

        self.assertEqual(confirmed_response.status_code, status.HTTP_200_OK)
        attendance = Attendance.objects.get(pk=confirmed_response.data["id"])
        self.assertEqual(attendance.end_km, 1351)

    def test_end_day_run_km_above_400_is_blocked(self):
        self.client.force_authenticate(user=self.driver_user)
        start_response = self._start_day(start_km=2000)
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 2451,
                "confirm_large_run": "true",
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )

        self.assertEqual(end_response.status_code, status.HTTP_400_BAD_REQUEST)
        detail = end_response.data.get("detail") or ""
        if isinstance(detail, list) and detail:
            detail = str(detail[0])
        self.assertIn("400", str(detail))

    def test_end_day_can_close_open_yesterday_attendance(self):
        attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate() - timedelta(days=1),
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=410,
            odo_start_image=self._odo_image(),
            latitude="22.572646",
            longitude="88.363895",
        )

        self.client.force_authenticate(user=self.driver_user)
        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 455,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )

        self.assertEqual(end_response.status_code, status.HTTP_200_OK)
        attendance.refresh_from_db()
        self.assertEqual(attendance.end_km, 455)
        self.assertIsNotNone(attendance.ended_at)

    def test_driver_can_start_second_service_same_day_with_another_vehicle(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=500)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        first_end = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 540,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(first_end.status_code, status.HTTP_200_OK)

        second_start = self._start_day(
            start_km=541,
            vehicle_id=self.vehicle_two.id,
            service_id=self.service_two.id,
        )
        self.assertEqual(second_start.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Attendance.objects.filter(
                driver=self.driver,
                date=timezone.localdate(),
            ).count(),
            2,
        )

    def test_driver_can_start_second_service_same_day_with_same_vehicle(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=700)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        first_end = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 720,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(first_end.status_code, status.HTTP_200_OK)

        second_start = self._start_day(
            start_km=721,
            vehicle_id=self.vehicle.id,
            service_id=self.service_two.id,
        )
        self.assertEqual(second_start.status_code, status.HTTP_201_CREATED)

    def test_driver_cannot_restart_same_vehicle_with_lower_odometer(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=730)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        first_end = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 760,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(first_end.status_code, status.HTTP_200_OK)

        second_start = self._start_day(
            start_km=750,
            vehicle_id=self.vehicle.id,
            service_id=self.service_two.id,
        )
        self.assertEqual(second_start.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latest recorded odometer", str(second_start.data).lower())

    def test_driver_cannot_restart_same_vehicle_more_than_300_km_above_latest_odometer(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=730)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        first_end = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 760,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(first_end.status_code, status.HTTP_200_OK)

        second_start = self._start_day(
            start_km=1061,
            vehicle_id=self.vehicle.id,
            service_id=self.service_two.id,
        )
        self.assertEqual(second_start.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("more than 300 km", str(second_start.data).lower())

    def test_driver_cannot_start_second_service_same_day_when_open_trip_exists(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=600)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        second_start = self._start_day(start_km=601)
        self.assertEqual(second_start.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already active", str(second_start.data))

    def test_end_day_blocked_when_pending_open_trip_exists(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=800)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        attendance = Attendance.objects.filter(
            driver=self.driver,
            date=timezone.localdate(),
        ).order_by("-started_at").first()
        self.assertIsNotNone(attendance)
        master_trip = attendance.trips.filter(
            is_day_trip=True,
            parent_trip__isnull=True,
        ).first()
        self.assertIsNotNone(master_trip)
        Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="Site A",
            destination="Site B",
            start_km=805,
            start_odo_image=self._odo_image(),
            status=Trip.Status.OPEN,
            is_day_trip=False,
        )

        end_response = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 840,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(end_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pending trips", str(end_response.data).lower())

    def test_second_driver_cannot_start_same_vehicle_while_first_driver_run_is_open(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=900, vehicle_id=self.vehicle.id)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.driver_two_user)
        second_start = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 901,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
                "service_id": self.service.id,
            },
            format="multipart",
        )
        self.assertEqual(second_start.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already in an active run", str(second_start.data))

    def test_second_driver_can_start_same_vehicle_after_first_driver_closes(self):
        self.client.force_authenticate(user=self.driver_user)
        first_start = self._start_day(start_km=950, vehicle_id=self.vehicle.id)
        self.assertEqual(first_start.status_code, status.HTTP_201_CREATED)
        first_end = self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 980,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )
        self.assertEqual(first_end.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.driver_two_user)
        second_start = self.client.post(
            reverse("attendance-start"),
            {
                "start_km": 980,
                "odo_start_image": self._odo_image(),
                "latitude": "22.572646",
                "longitude": "88.363895",
                "vehicle_id": self.vehicle.id,
                "service_id": self.service.id,
            },
            format="multipart",
        )
        self.assertEqual(second_start.status_code, status.HTTP_201_CREATED)

    def test_daily_overview_can_start_again_after_closed_run_same_day(self):
        self.client.force_authenticate(user=self.driver_user)
        self._start_day(start_km=1000)
        self.client.post(
            reverse("attendance-end"),
            {
                "end_km": 1040,
                "odo_end_image": self._odo_image(),
            },
            format="multipart",
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(reverse("attendance-daily"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["items"][0]
        self.assertEqual(item["status"], "PRESENT")
        self.assertTrue(item["has_attendance"])
        self.assertTrue(item["can_start_day"])

    def test_old_transporter_mark_does_not_leak_after_driver_reassignment(self):
        old_transporter_user = User.objects.create_user(
            username="old_attendance_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="old.attendance.transporter@example.com",
        )
        old_transporter = Transporter.objects.create(
            user=old_transporter_user,
            company_name="Old Attendance Fleet",
            address="Old Yard",
        )
        moving_driver_user = User.objects.create_user(
            username="moving_attendance_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="moving.attendance.driver@example.com",
        )
        moving_driver = Driver.objects.create(
            user=moving_driver_user,
            transporter=old_transporter,
            license_number="MOVE-ATT-01",
        )
        DriverDailyAttendanceMark.objects.create(
            driver=moving_driver,
            transporter=old_transporter,
            date=timezone.localdate(),
            status=DriverDailyAttendanceMark.Status.ABSENT,
            marked_by=old_transporter_user,
        )

        moving_driver.transporter = self.transporter
        moving_driver.save(update_fields=["transporter"])

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(reverse("attendance-daily"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(
            item
            for item in response.data["items"]
            if item["driver_id"] == moving_driver.id
        )
        self.assertEqual(item["status"], "NO_DUTY")
        self.assertFalse(item["has_mark"])
