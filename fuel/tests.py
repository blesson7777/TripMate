from datetime import timedelta
from datetime import timedelta
from io import BytesIO

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance
from drivers.models import Driver
from fuel.analytics import get_vehicle_fuel_status
from fuel.models import FuelRecord
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
            odo_start_image=self._image("start.png"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def _image(self, name):
        image_buffer = BytesIO()
        Image.new("RGB", (3, 3), color=(240, 240, 240)).save(
            image_buffer,
            format="PNG",
        )
        return SimpleUploadedFile(
            name,
            image_buffer.getvalue(),
            content_type="image/png",
        )

    def test_vehicle_fuel_add_saves_odometer_km(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "15.50",
                "amount": "1850.00",
                "odometer_km": 1234,
                "meter_image": self._image("meter.png"),
                "bill_image": self._image("bill.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["odometer_km"], 1234)
        self.assertEqual(response.data["liters"], "15.50")

    def test_vehicle_fuel_add_requires_odometer_km(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "10.00",
                "amount": "1000.00",
                "meter_image": self._image("meter.png"),
                "bill_image": self._image("bill.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("odometer_km", response.data)

    def test_fuel_add_rejects_tower_diesel_payload(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "entry_type": "TOWER_DIESEL",
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "40.00",
                "start_km": 1200,
                "end_km": 1234,
                "purpose": "Diesel Filling",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("logbook.png"),
                "ocr_raw_text": "sample text",
                "ocr_confidence": "0.85",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("separate module", response.data["detail"].lower())

    def test_fuel_list_returns_vehicle_rows(self):
        self.client.force_authenticate(user=self.driver_user)

        self.client.post(
            reverse("fuel-add"),
            {
                "entry_type": "VEHICLE_FILLING",
                "liters": "12.00",
                "amount": "1440.00",
                "odometer_km": 1250,
                "meter_image": self._image("meter.png"),
                "bill_image": self._image("bill.png"),
            },
            format="multipart",
        )

        list_response = self.client.get(reverse("fuel-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["liters"], "12.00")

    def test_vehicle_fuel_add_without_active_day_trip_requires_vehicle_selection(self):
        manual_driver_user = User.objects.create_user(
            username="manual_fuel_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="manual.fuel.driver@example.com",
        )
        manual_driver = Driver.objects.create(
            user=manual_driver_user,
            transporter=self.transporter,
            license_number="FUEL-LIC-02",
        )

        self.client.force_authenticate(user=manual_driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "8.00",
                "amount": "960.00",
                "odometer_km": 1500,
                "meter_image": self._image("manual-meter.png"),
                "bill_image": self._image("manual-bill.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle_id", response.data)

    def test_vehicle_fuel_add_without_active_day_trip_accepts_selected_vehicle(self):
        manual_driver_user = User.objects.create_user(
            username="manual_select_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="manual.select.driver@example.com",
        )
        manual_driver = Driver.objects.create(
            user=manual_driver_user,
            transporter=self.transporter,
            license_number="FUEL-LIC-03",
        )

        self.client.force_authenticate(user=manual_driver_user)
        response = self.client.post(
            reverse("fuel-add"),
            {
                "vehicle_id": self.vehicle.id,
                "liters": "9.50",
                "amount": "1140.00",
                "odometer_km": 1450,
                "meter_image": self._image("manual-selected-meter.png"),
                "bill_image": self._image("manual-selected-bill.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = FuelRecord.objects.get(id=response.data["id"])
        self.assertIsNone(record.attendance)
        self.assertEqual(record.driver_id, manual_driver.id)
        self.assertEqual(record.vehicle_id, self.vehicle.id)

    def test_vehicle_fuel_add_rejects_lower_odometer_than_latest_vehicle_reading(self):
        self.client.force_authenticate(user=self.driver_user)

        first = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "20.00",
                "amount": "2400.00",
                "odometer_km": 1300,
                "meter_image": self._image("meter-first.png"),
                "bill_image": self._image("bill-first.png"),
            },
            format="multipart",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "10.00",
                "amount": "1200.00",
                "odometer_km": 1290,
                "meter_image": self._image("meter-second.png"),
                "bill_image": self._image("bill-second.png"),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latest recorded odometer", str(second.data["odometer_km"][0]).lower())

    def test_vehicle_fuel_add_rejects_odometer_more_than_300_km_above_latest_vehicle_reading(self):
        self.client.force_authenticate(user=self.driver_user)

        first = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "20.00",
                "amount": "2400.00",
                "odometer_km": 1300,
                "meter_image": self._image("meter-first-300.png"),
                "bill_image": self._image("bill-first-300.png"),
            },
            format="multipart",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            reverse("fuel-add"),
            {
                "liters": "10.00",
                "amount": "1200.00",
                "odometer_km": 1601,
                "meter_image": self._image("meter-second-300.png"),
                "bill_image": self._image("bill-second-300.png"),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("more than 300 km", str(second.data["odometer_km"][0]).lower())

    def test_vehicle_fuel_status_estimates_remaining_fuel(self):
        analytics_vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="FUEL-VEH-ANALYTICS",
            model="Fuel Analytics Van",
            status=Vehicle.Status.ACTIVE,
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=analytics_vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1000,
            date=timezone.localdate() - timedelta(days=2),
            fill_date=timezone.localdate() - timedelta(days=2),
            meter_image=self._image("analytics-meter-1.png"),
            bill_image=self._image("analytics-bill-1.png"),
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=analytics_vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1500,
            date=timezone.localdate() - timedelta(days=1),
            fill_date=timezone.localdate() - timedelta(days=1),
            meter_image=self._image("analytics-meter-2.png"),
            bill_image=self._image("analytics-bill-2.png"),
        )
        Attendance.objects.create(
            driver=self.driver,
            vehicle=analytics_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1500,
            end_km=1800,
            odo_start_image=self._image("analytics-start.png"),
            odo_end_image=self._image("analytics-end.png"),
            latitude="22.572646",
            longitude="88.363895",
            end_latitude="22.572646",
            end_longitude="88.363895",
            ended_at=timezone.now(),
        )

        snapshot = get_vehicle_fuel_status(analytics_vehicle)
        self.assertIsNotNone(snapshot)
        self.assertEqual(str(snapshot.average_mileage_km_per_liter), "10.00")
        self.assertEqual(str(snapshot.estimated_tank_capacity_liters), "50.00")
        self.assertEqual(str(snapshot.estimated_fuel_left_liters), "20.00")
        self.assertEqual(str(snapshot.estimated_fuel_left_percent), "40.00")
        self.assertEqual(snapshot.estimated_km_left, 200)

    def test_vehicle_fuel_status_prefers_manual_tank_capacity(self):
        analytics_vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="FUEL-VEH-MANUAL",
            model="Fuel Manual Tank Van",
            status=Vehicle.Status.ACTIVE,
            tank_capacity_liters="60.00",
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=analytics_vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1000,
            date=timezone.localdate() - timedelta(days=2),
            fill_date=timezone.localdate() - timedelta(days=2),
            meter_image=self._image("manual-meter-1.png"),
            bill_image=self._image("manual-bill-1.png"),
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=analytics_vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="50.00",
            fuel_filled="50.00",
            amount="5000.00",
            odometer_km=1500,
            date=timezone.localdate() - timedelta(days=1),
            fill_date=timezone.localdate() - timedelta(days=1),
            meter_image=self._image("manual-meter-2.png"),
            bill_image=self._image("manual-bill-2.png"),
        )
        Attendance.objects.create(
            driver=self.driver,
            vehicle=analytics_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=1500,
            end_km=1800,
            odo_start_image=self._image("manual-start.png"),
            odo_end_image=self._image("manual-end.png"),
            latitude="22.572646",
            longitude="88.363895",
            end_latitude="22.572646",
            end_longitude="88.363895",
            ended_at=timezone.now(),
        )

        snapshot = get_vehicle_fuel_status(analytics_vehicle)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.tank_capacity_source, "manual")
        self.assertEqual(str(snapshot.estimated_tank_capacity_liters), "60.00")
        self.assertEqual(str(snapshot.estimated_fuel_left_liters), "20.00")
        self.assertEqual(str(snapshot.estimated_fuel_left_percent), "33.33")

    def test_fuel_list_scopes_records_by_current_vehicle_transporter(self):
        old_transporter_user = User.objects.create_user(
            username="old_fuel_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="old.fuel.transporter@example.com",
        )
        old_transporter = Transporter.objects.create(
            user=old_transporter_user,
            company_name="Old Fuel Fleet",
            address="Old Fuel Yard",
        )
        new_transporter_user = User.objects.create_user(
            username="new_fuel_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="new.fuel.transporter@example.com",
        )
        new_transporter = Transporter.objects.create(
            user=new_transporter_user,
            company_name="New Fuel Fleet",
            address="New Fuel Yard",
        )
        moving_driver_user = User.objects.create_user(
            username="moving_fuel_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="moving.fuel.driver@example.com",
        )
        moving_driver = Driver.objects.create(
            user=moving_driver_user,
            transporter=old_transporter,
            license_number="MOVE-FUEL-01",
        )
        old_vehicle = Vehicle.objects.create(
            transporter=old_transporter,
            vehicle_number="OLD-FUEL-01",
            model="Old Fuel Van",
            status=Vehicle.Status.ACTIVE,
        )
        new_vehicle = Vehicle.objects.create(
            transporter=new_transporter,
            vehicle_number="NEW-FUEL-01",
            model="New Fuel Van",
            status=Vehicle.Status.ACTIVE,
        )
        old_attendance = Attendance.objects.create(
            driver=moving_driver,
            vehicle=old_vehicle,
            date=timezone.localdate() - timedelta(days=1),
            status=Attendance.Status.ON_DUTY,
            start_km=1000,
            end_km=1010,
            odo_start_image=self._image("old-start.png"),
            odo_end_image=self._image("old-end.png"),
            latitude="22.572646",
            longitude="88.363895",
        )
        old_record = FuelRecord.objects.create(
            attendance=old_attendance,
            driver=moving_driver,
            vehicle=old_vehicle,
            partner=old_transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="10.00",
            fuel_filled="10.00",
            amount="1000.00",
            odometer_km=1010,
            meter_image=self._image("old-meter.png"),
            bill_image=self._image("old-bill.png"),
            date=old_attendance.date,
            fill_date=old_attendance.date,
        )

        moving_driver.transporter = new_transporter
        moving_driver.assigned_vehicle = None
        moving_driver.save(update_fields=["transporter", "assigned_vehicle"])
        new_attendance = Attendance.objects.create(
            driver=moving_driver,
            vehicle=new_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            start_km=2000,
            end_km=2010,
            odo_start_image=self._image("new-start.png"),
            odo_end_image=self._image("new-end.png"),
            latitude="22.572646",
            longitude="88.363895",
        )
        new_record = FuelRecord.objects.create(
            attendance=new_attendance,
            driver=moving_driver,
            vehicle=new_vehicle,
            partner=new_transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="12.00",
            fuel_filled="12.00",
            amount="1320.00",
            odometer_km=2010,
            meter_image=self._image("new-meter.png"),
            bill_image=self._image("new-bill.png"),
            date=new_attendance.date,
            fill_date=new_attendance.date,
        )

        self.client.force_authenticate(user=old_transporter_user)
        old_response = self.client.get(reverse("fuel-list"))
        self.assertEqual(old_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in old_response.data], [old_record.id])

        self.client.force_authenticate(user=new_transporter_user)
        new_response = self.client.get(reverse("fuel-list"))
        self.assertEqual(new_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in new_response.data], [new_record.id])

        self.client.force_authenticate(user=moving_driver_user)
        driver_response = self.client.get(reverse("fuel-list"))
        self.assertEqual(driver_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in driver_response.data], [new_record.id])
