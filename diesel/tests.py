from io import BytesIO
from datetime import date, timedelta

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance, TransportService
from diesel.models import IndusTowerSite
from diesel.views import _build_diesel_pdf_table_data, _build_tripsheet_rows
from drivers.models import Driver
from fuel.models import FuelRecord
from trips.models import Trip
from users.models import Transporter, User
from vehicles.models import Vehicle


class TowerDieselModuleTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="diesel_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="diesel.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Diesel Fleet",
            address="Yard",
            diesel_tracking_enabled=True,
        )
        self.driver_user = User.objects.create_user(
            username="diesel_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="diesel.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="DSL-LIC-01",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="DSL-VEH-01",
            model="Diesel Vehicle",
            vehicle_type=Vehicle.Type.DIESEL_SERVICE,
            status=Vehicle.Status.ACTIVE,
        )
        self.service = TransportService.objects.create(
            transporter=self.transporter,
            name="Generator Vehicle",
            is_active=True,
        )
        self.attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=100,
            end_km=140,
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

    def test_tower_diesel_add_uses_additional_trip_end_km(self):
        master_trip = Trip.objects.create(
            attendance=self.attendance,
            parent_trip=None,
            is_day_trip=True,
            start_location="Day Start",
            destination="Day End",
            start_km=100,
            end_km=140,
            purpose="Master",
            start_odo_image=self._image("master-start.png"),
            end_odo_image=self._image("master-end.png"),
            status=Trip.Status.CLOSED,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        Trip.objects.create(
            attendance=self.attendance,
            parent_trip=master_trip,
            is_day_trip=False,
            start_location="A",
            destination="B",
            start_km=120,
            end_km=160,
            purpose="Additional Duty",
            start_odo_image=self._image("trip-start.png"),
            end_odo_image=self._image("trip-end.png"),
            status=Trip.Status.CLOSED,
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "40.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("logbook.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["start_km"], 100)
        self.assertEqual(response.data["end_km"], 160)
        self.assertEqual(response.data["run_km"], 60)

    def test_tower_diesel_add_blocked_when_feature_disabled(self):
        self.transporter.diesel_tracking_enabled = False
        self.transporter.save(update_fields=["diesel_tracking_enabled"])

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook.png"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["status"], "error")

    def test_tower_tripsheet_groups_km_once_per_day(self):
        self.client.force_authenticate(user=self.driver_user)
        for site_id, site_name, fuel in [
            ("1000101", "Site One", "20.00"),
            ("1000102", "Site Two", "40.00"),
        ]:
            response = self.client.post(
                reverse("diesel-add"),
                {
                    "indus_site_id": site_id,
                    "site_name": site_name,
                    "fuel_filled": fuel,
                    "purpose": "Tower Filling",
                    "tower_latitude": "9.501200",
                    "tower_longitude": "76.980100",
                    "fill_date": timezone.localdate().isoformat(),
                    "logbook_photo": self._image(f"logbook-{site_id}.png"),
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("diesel-tripsheet"),
            {
                "month": timezone.localdate().month,
                "year": timezone.localdate().year,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_days"], 1)
        self.assertEqual(response.data["total_fillings"], 2)
        self.assertEqual(response.data["total_entries"], 2)

        first = response.data["rows"][0]
        second = response.data["rows"][1]

        self.assertEqual(first["start_km"], 100)
        self.assertEqual(first["end_km"], 140)
        self.assertEqual(first["run_km"], 40)
        self.assertNotEqual(first["indus_site_id"], "")
        self.assertTrue(first["is_day_summary"])

        self.assertEqual(second["start_km"], "")
        self.assertEqual(second["end_km"], "")
        self.assertEqual(second["run_km"], "")
        self.assertNotEqual(second["indus_site_id"], "")
        self.assertFalse(second["is_day_summary"])

    def test_tower_tripsheet_pdf_downloads_for_transporter(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1000101",
                "site_name": "Site One",
                "fuel_filled": "20.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("logbook-pdf.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.transporter_user)
        pdf_response = self.client.get(
            reverse("diesel-tripsheet-pdf"),
            {
                "month": timezone.localdate().month,
                "year": timezone.localdate().year,
            },
        )
        self.assertEqual(pdf_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn("diesel-fill-trip-sheet", pdf_response["Content-Disposition"])

    def test_diesel_pdf_marks_only_vehicle_changes_with_plain_row(self):
        rows = [
            {
                "sl_no": 1,
                "date": date(2026, 3, 6),
                "vehicle_number": "KL35L4523",
                "start_km": 102882,
                "end_km": 102973,
                "run_km": 91,
                "indus_site_id": "1000101",
                "site_name": "Site One",
                "fuel_filled": "20.00",
                "purpose": "Diesel Filling",
                "is_day_summary": True,
            },
            {
                "sl_no": 2,
                "date": date(2026, 3, 6),
                "vehicle_number": "KL35L4523",
                "start_km": "",
                "end_km": "",
                "run_km": "",
                "indus_site_id": "1000102",
                "site_name": "Site Two",
                "fuel_filled": "40.00",
                "purpose": "Diesel Filling",
                "is_day_summary": False,
            },
            {
                "sl_no": 3,
                "date": date(2026, 3, 6),
                "vehicle_number": "KL06K5828",
                "start_km": 86146,
                "end_km": 86210,
                "run_km": 64,
                "indus_site_id": "1000103",
                "site_name": "Site Three",
                "fuel_filled": "60.00",
                "purpose": "Diesel Filling",
                "is_day_summary": True,
            },
        ]

        table_data, marker_rows = _build_diesel_pdf_table_data(rows)

        self.assertEqual(marker_rows, [3])
        self.assertFalse(any("Service:" in str(cell) for row in table_data for cell in row))
        self.assertEqual(table_data[3][0], "Vehicle changed to KL06K5828")
        self.assertEqual(table_data[3][1:], ["", "", "", "", "", "", "", ""])

    def test_diesel_pdf_can_include_filled_quantity_column(self):
        rows = [
            {
                "sl_no": 1,
                "date": date(2026, 3, 6),
                "vehicle_number": "KL35L4523",
                "start_km": 102882,
                "end_km": 102973,
                "run_km": 91,
                "indus_site_id": "1000101",
                "site_name": "Site One",
                "fuel_filled": "20.00",
                "purpose": "Diesel Filling",
                "is_day_summary": True,
            }
        ]

        table_data, marker_rows = _build_diesel_pdf_table_data(
            rows,
            include_filled_quantity=True,
        )

        self.assertEqual(marker_rows, [])
        self.assertEqual(table_data[0], [
            "Sl No",
            "Date",
            "Vehicle",
            "Start KM",
            "End KM",
            "Run KM",
            "Site ID",
            "Site Name",
            "Filled Qty",
            "Purpose",
        ])
        self.assertEqual(table_data[1][8], "20.00")
        self.assertEqual(table_data[1][9], "Diesel Filling")

    def test_tower_site_list_returns_distance_sorted_with_last_quantity(self):
        near_site = IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1000201",
            site_name="Near Site",
            latitude="9.501250",
            longitude="76.980100",
        )
        far_site = IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1000202",
            site_name="Far Site",
            latitude="9.511250",
            longitude="76.980100",
        )
        FuelRecord.objects.create(
            attendance=self.attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            tower_site=near_site,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="20.00",
            amount="0.00",
            indus_site_id=near_site.indus_site_id,
            site_name=near_site.site_name,
            purpose="Diesel Filling",
            fuel_filled="20.00",
            start_km=100,
            end_km=140,
            fill_date=timezone.localdate(),
        )
        FuelRecord.objects.create(
            attendance=self.attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            tower_site=far_site,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="40.00",
            amount="0.00",
            indus_site_id=far_site.indus_site_id,
            site_name=far_site.site_name,
            purpose="Diesel Filling",
            fuel_filled="40.00",
            start_km=100,
            end_km=140,
            fill_date=timezone.localdate(),
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(
            reverse("diesel-sites"),
            {
                "latitude": "9.501220",
                "longitude": "76.980100",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["items"][0]["indus_site_id"], "1000201")
        self.assertEqual(response.data["items"][0]["last_filled_quantity"], 20.0)
        self.assertEqual(response.data["items"][1]["indus_site_id"], "1000202")
        self.assertEqual(response.data["items"][1]["last_filled_quantity"], 40.0)

    def test_tower_tripsheet_merges_same_vehicle_multiple_drivers_into_one_km_block(self):
        second_driver_user = User.objects.create_user(
            username="diesel_driver_two",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="diesel.driver.two@example.com",
        )
        second_driver = Driver.objects.create(
            user=second_driver_user,
            transporter=self.transporter,
            license_number="DSL-LIC-02",
        )
        second_attendance = Attendance.objects.create(
            driver=second_driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=140,
            end_km=180,
            odo_start_image=self._image("second-start.png"),
            latitude="22.572646",
            longitude="88.363895",
        )
        FuelRecord.objects.create(
            attendance=self.attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="20.00",
            fuel_filled="20.00",
            amount="0.00",
            start_km=100,
            end_km=140,
            fill_date=timezone.localdate(),
            date=timezone.localdate(),
            indus_site_id="2011001",
            site_name="First Driver Site",
            purpose="Tower Filling",
            logbook_photo=self._image("driver-one-logbook.png"),
        )
        FuelRecord.objects.create(
            attendance=second_attendance,
            driver=second_driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="20.00",
            fuel_filled="20.00",
            amount="0.00",
            start_km=140,
            end_km=180,
            fill_date=timezone.localdate(),
            date=timezone.localdate(),
            indus_site_id="2011002",
            site_name="Second Driver Site",
            purpose="Tower Filling",
            logbook_photo=self._image("driver-two-logbook.png"),
        )

        rows = _build_tripsheet_rows(
            FuelRecord.objects.filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                fill_date=timezone.localdate(),
                vehicle=self.vehicle,
            ).select_related("attendance", "vehicle", "driver", "driver__user", "tower_site")
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["start_km"], 100)
        self.assertEqual(rows[0]["end_km"], 180)
        self.assertEqual(rows[0]["run_km"], 80)
        self.assertEqual(rows[1]["start_km"], "")
        self.assertEqual(rows[1]["end_km"], "")
        self.assertEqual(rows[1]["run_km"], "")

    def test_tower_tripsheet_includes_legacy_general_vehicle_records(self):
        legacy_vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="LEGACY-DSL-01",
            model="Legacy Tower Diesel Vehicle",
            vehicle_type=Vehicle.Type.GENERAL,
            status=Vehicle.Status.ACTIVE,
        )
        legacy_attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=legacy_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=300,
            end_km=360,
            odo_start_image=self._image("legacy-start.png"),
            latitude="22.572646",
            longitude="88.363895",
        )
        FuelRecord.objects.create(
            attendance=legacy_attendance,
            driver=self.driver,
            vehicle=legacy_vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="20.00",
            fuel_filled="20.00",
            amount="0.00",
            start_km=300,
            end_km=360,
            fill_date=timezone.localdate(),
            date=timezone.localdate(),
            indus_site_id="2011001",
            site_name="Legacy Site",
            purpose="Tower Filling",
            logbook_photo=self._image("legacy-logbook.png"),
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("diesel-tripsheet"),
            {
                "month": timezone.localdate().month,
                "year": timezone.localdate().year,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_entries"], 1)
        self.assertTrue(
            any(row["site_name"] == "Legacy Site" for row in response.data["rows"])
        )

    def test_tower_tripsheet_prefers_attendance_closing_km_over_stale_fill_rows(self):
        stale_attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=102882,
            end_km=102973,
            odo_start_image=self._image("stale-start.png"),
            latitude="22.572646",
            longitude="88.363895",
        )
        FuelRecord.objects.create(
            attendance=stale_attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="20.00",
            fuel_filled="20.00",
            amount="0.00",
            start_km=102882,
            end_km=102882,
            fill_date=timezone.localdate(),
            date=timezone.localdate(),
            indus_site_id="1067993",
            site_name="Test Site",
            purpose="Diesel Filling",
            logbook_photo=self._image("stale-logbook.png"),
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("diesel-tripsheet"),
            {
                "month": timezone.localdate().month,
                "year": timezone.localdate().year,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target_row = next(
            row for row in response.data["rows"] if row["indus_site_id"] == "1067993"
        )
        self.assertEqual(target_row["start_km"], 102882)
        self.assertEqual(target_row["end_km"], 102973)
        self.assertEqual(target_row["run_km"], 91)

    def test_tower_diesel_add_rejects_duplicate_within_ten_minutes(self):
        self.client.force_authenticate(user=self.driver_user)
        payload = {
            "indus_site_id": "1013567",
            "site_name": "Chottakuzhy Voda",
            "fuel_filled": "40.00",
            "purpose": "Tower Filling",
            "tower_latitude": "9.501200",
            "tower_longitude": "76.980100",
            "fill_date": timezone.localdate().isoformat(),
        }
        first = self.client.post(
            reverse("diesel-add"),
            {
                **payload,
                "logbook_photo": self._image("logbook-first.png"),
            },
            format="multipart",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            reverse("diesel-add"),
            {
                **payload,
                "logbook_photo": self._image("logbook-second.png"),
            },
            format="multipart",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("within 10 minutes", str(second.data))

    def test_tower_diesel_add_links_to_tower_master_site(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "40.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("logbook-master.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(IndusTowerSite.objects.count(), 1)
        site = IndusTowerSite.objects.first()
        self.assertEqual(site.indus_site_id, "1013567")
        self.assertEqual(site.site_name, "Chottakuzhy Voda")
        self.assertEqual(str(site.latitude), "9.501200")
        self.assertEqual(str(site.longitude), "76.980100")

    def test_existing_tower_location_is_not_overwritten_by_later_driver_fill(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1013567",
            site_name="Chottakuzhy Voda",
            latitude="9.501200",
            longitude="76.980100",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "40.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501350",
                "tower_longitude": "76.980150",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("logbook-preserve-location.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        site = IndusTowerSite.objects.get(
            partner=self.transporter,
            indus_site_id="1013567",
        )
        self.assertEqual(str(site.latitude), "9.501200")
        self.assertEqual(str(site.longitude), "76.980100")

    def test_driver_fill_rejected_when_outside_saved_tower_radius(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1013555",
            site_name="Boundary Tower",
            latitude="9.501200",
            longitude="76.980100",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013555",
                "site_name": "Boundary Tower",
                "fuel_filled": "20.00",
                "tower_latitude": "9.503500",
                "tower_longitude": "76.983500",
                "logbook_photo": self._image("logbook-outside-radius.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("within 100 meters", str(response.data))

    def test_existing_tower_without_coordinates_gets_location_from_first_driver_fill(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1013666",
            site_name="Needs First Fix",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013666",
                "site_name": "Needs First Fix",
                "fuel_filled": "20.00",
                "tower_latitude": "9.511200",
                "tower_longitude": "76.981100",
                "logbook_photo": self._image("logbook-first-fix.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        site = IndusTowerSite.objects.get(
            partner=self.transporter,
            indus_site_id="1013666",
        )
        self.assertEqual(str(site.latitude), "9.511200")
        self.assertEqual(str(site.longitude), "76.981100")

    def test_tower_site_lookup_by_site_id(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1018888",
            site_name="Lookup Site",
            latitude="9.400000",
            longitude="76.900000",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(
            reverse("diesel-site-by-id"),
            {"indus_site_id": "1018888"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["site_name"], "Lookup Site")
        self.assertEqual(response.data["indus_site_id"], "1018888")

    def test_tower_site_lookup_by_site_id_without_coordinates(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1018899",
            site_name="Lookup Without Coordinates",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(
            reverse("diesel-site-by-id"),
            {"indus_site_id": "1018899"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["site_name"], "Lookup Without Coordinates")

    def test_tower_site_list_supports_search(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1017001",
            site_name="Alpha Site",
            latitude="9.400000",
            longitude="76.900000",
        )
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1017002",
            site_name="Beta Site",
            latitude="9.500000",
            longitude="76.950000",
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(
            reverse("diesel-sites"),
            {"q": "Beta"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["items"][0]["indus_site_id"], "1017002")

    def test_manual_tower_record_allows_blank_site_name_and_missing_photo(self):
        tower_site = IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1019999",
            site_name="",
        )
        record = FuelRecord.objects.create(
            attendance=self.attendance,
            driver=self.driver,
            vehicle=self.vehicle,
            partner=self.transporter,
            tower_site=tower_site,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="25.00",
            fuel_filled="25.00",
            amount="0.00",
            start_km=100,
            end_km=140,
            fill_date=timezone.localdate(),
            date=timezone.localdate(),
            purpose="Diesel Filling",
        )
        self.assertFalse(record.logbook_photo)
        self.assertEqual(record.resolved_indus_site_id, "1019999")
        self.assertEqual(record.resolved_site_name, "")

    def test_tower_diesel_add_allows_general_vehicle_when_service_is_diesel(self):
        non_diesel_vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="DSL-VEH-02",
            model="General Duty Vehicle",
            vehicle_type=Vehicle.Type.GENERAL,
            status=Vehicle.Status.ACTIVE,
        )
        diesel_service = TransportService.objects.create(
            transporter=self.transporter,
            name="Diesel Filling Vehicle",
            is_active=True,
        )
        Attendance.objects.create(
            driver=self.driver,
            vehicle=non_diesel_vehicle,
            date=timezone.localdate(),
            status=Attendance.Status.ON_DUTY,
            service=diesel_service,
            service_name=diesel_service.name,
            start_km=200,
            odo_start_image=self._image("general-start.png"),
            latitude="22.572646",
            longitude="88.363895",
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "Chottakuzhy Voda",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook-general.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["vehicle_number"], "DSL-VEH-02")

    def test_tower_diesel_list_filters_by_fill_date_and_site_search(self):
        self.client.force_authenticate(user=self.driver_user)
        first_response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1011001",
                "site_name": "Alpha Tower",
                "fuel_filled": "20.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "fill_date": timezone.localdate().isoformat(),
                "logbook_photo": self._image("alpha-logbook.png"),
            },
            format="multipart",
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1011002",
                "site_name": "Beta Tower",
                "fuel_filled": "40.00",
                "purpose": "Tower Filling",
                "tower_latitude": "9.501210",
                "tower_longitude": "76.980110",
                "fill_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "logbook_photo": self._image("beta-logbook.png"),
            },
            format="multipart",
        )
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.transporter_user)
        date_filtered = self.client.get(
            reverse("diesel-list"),
            {
                "fill_date": timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(date_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(len(date_filtered.data), 1)
        self.assertEqual(date_filtered.data[0]["indus_site_id"], "1011001")

        query_filtered = self.client.get(
            reverse("diesel-list"),
            {
                "month": timezone.localdate().month,
                "year": timezone.localdate().year,
                "q": "Beta",
            },
        )
        self.assertEqual(query_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(len(query_filtered.data), 1)
        self.assertEqual(query_filtered.data[0]["site_name"], "Beta Tower")

    def test_tower_diesel_add_rejects_non_digit_site_id(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "10A3567",
                "site_name": "Alpha Tower",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook-invalid-id.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exactly 7 digits", str(response.data))

    def test_tower_diesel_add_rejects_numeric_only_site_name(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1013567",
                "site_name": "1246527",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook-invalid-name.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("only numbers", str(response.data))

    def test_tower_diesel_add_requires_confirmation_for_site_name_update(self):
        IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="1017777",
            site_name="Old Name",
        )
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1017777",
                "site_name": "New Name",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook-confirm.png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Confirm site name update", str(response.data))

        confirmed = self.client.post(
            reverse("diesel-add"),
            {
                "indus_site_id": "1017777",
                "site_name": "New Name",
                "confirm_site_name_update": "true",
                "fuel_filled": "20.00",
                "tower_latitude": "9.501200",
                "tower_longitude": "76.980100",
                "logbook_photo": self._image("logbook-confirmed.png"),
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            IndusTowerSite.objects.get(
                partner=self.transporter,
                indus_site_id="1017777",
            ).site_name,
            "New Name",
        )
