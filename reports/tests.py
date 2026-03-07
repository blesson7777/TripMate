from decimal import Decimal
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance, TransportService
from drivers.models import Driver
from fuel.models import FuelRecord
from trips.models import Trip
from users.models import Transporter, User
from vehicles.models import Vehicle


class MonthlyReportServiceWorkflowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="report_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="report.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Report Fleet",
            address="Central Yard",
            diesel_tracking_enabled=True,
        )

        self.driver_user = User.objects.create_user(
            username="report_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="report.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="REP-LIC-01",
        )
        self.driver_two_user = User.objects.create_user(
            username="report_driver_two",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="report.driver.two@example.com",
        )
        self.driver_two = Driver.objects.create(
            user=self.driver_two_user,
            transporter=self.transporter,
            license_number="REP-LIC-02",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="REP-VEH-01",
            model="Trip Carrier",
            status=Vehicle.Status.ACTIVE,
        )
        self.vehicle_two = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="REP-VEH-02",
            model="Trip Carrier 2",
            status=Vehicle.Status.ACTIVE,
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save(update_fields=["assigned_vehicle"])

        self.service_dtm = TransportService.objects.create(
            transporter=self.transporter,
            name="DTM Vehicle",
            description="Plant movement duty",
            is_active=True,
        )
        self.service_generator = TransportService.objects.create(
            transporter=self.transporter,
            name="Generator Vehicle",
            description="Generator support duty",
            is_active=True,
        )

    def _odo_image(self, filename="odo.gif"):
        return SimpleUploadedFile(
            filename,
            (
                b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                b"\x4c\x01\x00\x3b"
            ),
            content_type="image/gif",
        )

    def _create_attendance(
        self,
        *,
        date,
        service,
        start_km,
        end_km,
        purpose="",
        driver=None,
        vehicle=None,
    ):
        return Attendance.objects.create(
            driver=driver or self.driver,
            vehicle=vehicle or self.vehicle,
            date=date,
            status=Attendance.Status.ON_DUTY,
            service=service,
            service_name=service.name,
            service_purpose=purpose,
            start_km=start_km,
            end_km=end_km,
            odo_start_image=self._odo_image(filename=f"start-{date}.gif"),
            odo_end_image=self._odo_image(filename=f"end-{date}.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def test_monthly_report_returns_service_wise_trip_sheet_fields(self):
        report_date = timezone.localdate().replace(day=1)
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=1000,
            end_km=1080,
            purpose="Plant material movement",
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {
                "month": report_date.month,
                "year": report_date.year,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_days"], 1)
        self.assertEqual(response.data["total_km"], 80)
        row = response.data["rows"][0]
        self.assertEqual(row["sl_no"], 1)
        self.assertEqual(row["service_id"], self.service_dtm.id)
        self.assertEqual(row["service_name"], "DTM Vehicle")
        self.assertEqual(row["opening_km"], 1000)
        self.assertEqual(row["closing_km"], 1080)
        self.assertEqual(row["total_run_km"], 80)
        self.assertEqual(row["purpose"], "Plant material movement")

    def test_monthly_report_filters_by_service_id(self):
        day_one = timezone.localdate().replace(day=1)
        day_two = day_one + timedelta(days=1)
        self._create_attendance(
            date=day_one,
            service=self.service_dtm,
            start_km=2000,
            end_km=2060,
            purpose="DTM run",
        )
        self._create_attendance(
            date=day_two,
            service=self.service_generator,
            start_km=5000,
            end_km=5040,
            purpose="Generator support",
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {
                "month": day_one.month,
                "year": day_one.year,
                "service_id": self.service_dtm.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_days"], 1)
        self.assertEqual(response.data["rows"][0]["service_name"], "DTM Vehicle")
        self.assertEqual(response.data["rows"][0]["purpose"], "DTM run")

    def test_monthly_report_filters_by_service_name_case_insensitive(self):
        report_date = timezone.localdate().replace(day=2)
        self._create_attendance(
            date=report_date,
            service=self.service_generator,
            start_km=3000,
            end_km=3075,
            purpose="Generator emergency duty",
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {
                "month": report_date.month,
                "year": report_date.year,
                "service_name": "generator vehicle",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_days"], 1)
        self.assertEqual(response.data["rows"][0]["service_name"], "Generator Vehicle")

    def test_monthly_report_uses_last_child_trip_end_km_for_closing(self):
        report_date = timezone.localdate().replace(day=3)
        attendance = self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=5000,
            end_km=5040,
            purpose="DTM route",
        )
        master_trip = Trip.objects.create(
            attendance=attendance,
            parent_trip=None,
            start_location="Day Start",
            destination="Day End",
            start_km=5000,
            end_km=5040,
            purpose="Master",
            start_odo_image=self._odo_image(filename="master-start.gif"),
            end_odo_image=self._odo_image(filename="master-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=True,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="A",
            destination="B",
            start_km=5000,
            end_km=5090,
            purpose="Child 1",
            start_odo_image=self._odo_image(filename="child1-start.gif"),
            end_odo_image=self._odo_image(filename="child1-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=False,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {"month": report_date.month, "year": report_date.year},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        self.assertEqual(row["opening_km"], 5000)
        self.assertEqual(row["closing_km"], 5090)
        self.assertEqual(row["total_run_km"], 90)

    def test_monthly_report_uses_larger_of_day_end_and_trip_end(self):
        report_date = timezone.localdate().replace(day=6)
        attendance = self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=8000,
            end_km=8160,
            purpose="Dual service day",
        )
        master_trip = Trip.objects.create(
            attendance=attendance,
            parent_trip=None,
            start_location="Day Start",
            destination="Day End",
            start_km=8000,
            end_km=8160,
            purpose="Master",
            start_odo_image=self._odo_image(filename="max-master-start.gif"),
            end_odo_image=self._odo_image(filename="max-master-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=True,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location="A",
            destination="B",
            start_km=8000,
            end_km=8120,
            purpose="Child lower than day close",
            start_odo_image=self._odo_image(filename="max-child-start.gif"),
            end_odo_image=self._odo_image(filename="max-child-end.gif"),
            status=Trip.Status.CLOSED,
            is_day_trip=False,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {"month": report_date.month, "year": report_date.year},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        self.assertEqual(row["opening_km"], 8000)
        self.assertEqual(row["closing_km"], 8160)
        self.assertEqual(row["total_run_km"], 160)

    def test_monthly_report_groups_same_vehicle_same_service_across_multiple_runs(self):
        report_date = timezone.localdate().replace(day=7)
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=9000,
            end_km=9050,
            purpose="Morning run",
            driver=self.driver,
            vehicle=self.vehicle,
        )
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=9050,
            end_km=9125,
            purpose="Evening run",
            driver=self.driver_two,
            vehicle=self.vehicle,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {"month": report_date.month, "year": report_date.year},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(
            item
            for item in response.data["rows"]
            if item["date"] == report_date.isoformat()
            and item["vehicle_number"] == self.vehicle.vehicle_number
            and item["service_name"] == self.service_dtm.name
        )
        self.assertEqual(row["opening_km"], 9000)
        self.assertEqual(row["closing_km"], 9125)
        self.assertEqual(row["total_run_km"], 125)

    def test_monthly_report_keeps_separate_rows_for_same_service_different_vehicles(self):
        report_date = timezone.localdate().replace(day=8)
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=10000,
            end_km=10060,
            purpose="Vehicle one",
            driver=self.driver,
            vehicle=self.vehicle,
        )
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=20000,
            end_km=20045,
            purpose="Vehicle two",
            driver=self.driver_two,
            vehicle=self.vehicle_two,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("monthly-report"),
            {"month": report_date.month, "year": report_date.year},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        matching_rows = [
            item
            for item in response.data["rows"]
            if item["date"] == report_date.isoformat()
            and item["service_name"] == self.service_dtm.name
        ]
        self.assertEqual(len(matching_rows), 2)
        self.assertEqual(
            {item["vehicle_number"] for item in matching_rows},
            {self.vehicle.vehicle_number, self.vehicle_two.vehicle_number},
        )

    def test_monthly_report_total_km_is_calculated_for_all_vehicle_and_service_filters(self):
        report_date = timezone.localdate().replace(day=9)
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=11000,
            end_km=11060,
            purpose="DTM vehicle one",
            driver=self.driver,
            vehicle=self.vehicle,
        )
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=21000,
            end_km=21045,
            purpose="DTM vehicle two",
            driver=self.driver_two,
            vehicle=self.vehicle_two,
        )
        self._create_attendance(
            date=report_date + timedelta(days=1),
            service=self.service_generator,
            start_km=30000,
            end_km=30025,
            purpose="Generator vehicle one",
            driver=self.driver,
            vehicle=self.vehicle,
        )

        self.client.force_authenticate(user=self.transporter_user)

        all_response = self.client.get(
            reverse("monthly-report"),
            {"month": report_date.month, "year": report_date.year},
        )
        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        self.assertEqual(all_response.data["total_km"], 130)

        vehicle_response = self.client.get(
            reverse("monthly-report"),
            {
                "month": report_date.month,
                "year": report_date.year,
                "vehicle_id": self.vehicle.id,
            },
        )
        self.assertEqual(vehicle_response.status_code, status.HTTP_200_OK)
        self.assertEqual(vehicle_response.data["total_km"], 85)

        service_response = self.client.get(
            reverse("monthly-report"),
            {
                "month": report_date.month,
                "year": report_date.year,
                "service_id": self.service_dtm.id,
            },
        )
        self.assertEqual(service_response.status_code, status.HTTP_200_OK)
        self.assertEqual(service_response.data["total_km"], 105)

    def test_monthly_trip_sheet_pdf_download_full_and_compact(self):
        report_date = timezone.localdate().replace(day=4)
        self._create_attendance(
            date=report_date,
            service=self.service_dtm,
            start_km=7000,
            end_km=7080,
            purpose="Plant run",
        )
        self.client.force_authenticate(user=self.transporter_user)

        full_response = self.client.get(
            reverse("monthly-report-pdf"),
            {
                "month": report_date.month,
                "year": report_date.year,
                "layout": "full",
            },
        )
        self.assertEqual(full_response.status_code, status.HTTP_200_OK)
        self.assertEqual(full_response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", full_response["Content-Disposition"])

        compact_response = self.client.get(
            reverse("monthly-report-pdf"),
            {
                "month": report_date.month,
                "year": report_date.year,
                "layout": "compact",
            },
        )
        self.assertEqual(compact_response.status_code, status.HTTP_200_OK)
        self.assertEqual(compact_response["Content-Type"], "application/pdf")


class FuelMonthlyMileageWorkflowTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="fuel_report_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="fuel.report.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Fuel Report Fleet",
            address="Central Yard",
            diesel_tracking_enabled=True,
        )

        self.driver_user = User.objects.create_user(
            username="fuel_report_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="fuel.report.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="FUEL-REP-LIC-01",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="FUEL-REP-VEH-01",
            model="Mileage Carrier",
            status=Vehicle.Status.ACTIVE,
        )
        self.service = TransportService.objects.create(
            transporter=self.transporter,
            name="DTM Vehicle",
            description="Mileage duty",
            is_active=True,
        )

    def _image(self, filename="img.gif"):
        return SimpleUploadedFile(
            filename,
            (
                b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                b"\x4c\x01\x00\x3b"
            ),
            content_type="image/gif",
        )

    def _attendance(self, *, run_date, start_km, end_km):
        return Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=run_date,
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=start_km,
            end_km=end_km,
            odo_start_image=self._image(filename=f"start-{run_date}.gif"),
            odo_end_image=self._image(filename=f"end-{run_date}.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def _fuel(self, *, attendance, run_date, liters, amount, odometer_km):
        return FuelRecord.objects.create(
            attendance=attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters=Decimal(liters),
            fuel_filled=Decimal(liters),
            amount=Decimal(amount),
            odometer_km=odometer_km,
            start_km=max(odometer_km - 10, 0),
            end_km=odometer_km,
            fill_date=run_date,
            date=run_date,
            indus_site_id="1013567",
            site_name="Chottakuzhy Voda",
            purpose="Diesel Filling",
            logbook_photo=self._image(filename=f"log-{run_date}-{odometer_km}.gif"),
            meter_image=self._image(filename=f"meter-{run_date}-{odometer_km}.gif"),
            bill_image=self._image(filename=f"bill-{run_date}-{odometer_km}.gif"),
        )

    def test_full_tank_interval_mileage_uses_two_odometer_readings(self):
        report_date = timezone.localdate().replace(day=5)
        attendance_one = self._attendance(
            run_date=report_date,
            start_km=100,
            end_km=150,
        )
        attendance_two = self._attendance(
            run_date=report_date + timedelta(days=1),
            start_km=150,
            end_km=200,
        )
        self._fuel(
            attendance=attendance_one,
            run_date=report_date,
            liters="20.00",
            amount="2200.00",
            odometer_km=100,
        )
        self._fuel(
            attendance=attendance_two,
            run_date=report_date + timedelta(days=1),
            liters="10.00",
            amount="1200.00",
            odometer_km=200,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("fuel-monthly-summary"),
            {"month": report_date.month, "year": report_date.year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_vehicles_filled"], 1)
        row = response.data["rows"][0]
        self.assertEqual(row["total_km"], 100)
        self.assertEqual(Decimal(str(row["average_mileage"])), Decimal("10.00"))
        self.assertEqual(
            Decimal(str(response.data["overall_average_mileage"])),
            Decimal("10.00"),
        )

    def test_mileage_uses_previous_month_odometer_for_first_interval(self):
        report_date = timezone.localdate().replace(day=10)
        previous_date = report_date - timedelta(days=15)

        attendance_prev = self._attendance(
            run_date=previous_date,
            start_km=80,
            end_km=100,
        )
        attendance_one = self._attendance(
            run_date=report_date,
            start_km=100,
            end_km=150,
        )
        attendance_two = self._attendance(
            run_date=report_date + timedelta(days=3),
            start_km=150,
            end_km=200,
        )

        self._fuel(
            attendance=attendance_prev,
            run_date=previous_date,
            liters="5.00",
            amount="600.00",
            odometer_km=100,
        )
        self._fuel(
            attendance=attendance_one,
            run_date=report_date,
            liters="10.00",
            amount="1200.00",
            odometer_km=150,
        )
        self._fuel(
            attendance=attendance_two,
            run_date=report_date + timedelta(days=3),
            liters="8.00",
            amount="1000.00",
            odometer_km=200,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("fuel-monthly-summary"),
            {"month": report_date.month, "year": report_date.year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        self.assertEqual(row["fuel_fill_count"], 2)
        self.assertEqual(row["total_km"], 100)
        self.assertEqual(Decimal(str(row["average_mileage"])), Decimal("5.56"))
