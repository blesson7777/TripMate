from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance, AttendanceLocationPoint, TransportService
from diesel.models import DieselDailyRoutePlan, IndusTowerSite
from drivers.models import Driver
from fuel.models import FuelRecord
from users.models import AccountDeletionRequest, Transporter, User
from vehicles.models import Vehicle


class AdminDriverLocationsPageTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_driver_locations",
            email="admin.driver.locations@example.com",
            password="AdminPass@123",
        )

        transporter_user = User.objects.create_user(
            username="driver_locations_transporter",
            password="DriverLocPass@123",
            role=User.Role.TRANSPORTER,
            email="driver.locations.transporter@example.com",
        )
        transporter = Transporter.objects.create(
            user=transporter_user,
            company_name="Driver Locations Fleet",
            address="HQ",
        )

        driver_user = User.objects.create_user(
            username="driver_locations_driver",
            password="DriverLocPass@123",
            role=User.Role.DRIVER,
            email="driver.locations.driver@example.com",
        )
        driver = Driver.objects.create(
            user=driver_user,
            transporter=transporter,
            license_number="DL-LOC-001",
        )
        vehicle = Vehicle.objects.create(
            transporter=transporter,
            vehicle_number="DL-VEH-001",
            model="Route Van",
            status=Vehicle.Status.ACTIVE,
        )
        service = TransportService.objects.create(
            transporter=transporter,
            name="Route Service",
            is_active=True,
        )
        self.attendance = Attendance.objects.create(
            driver=driver,
            vehicle=vehicle,
            service=service,
            service_name=service.name,
            service_purpose="Location test",
            date=timezone.localdate(),
            start_km=1000,
            odo_start_image=self._odo_image(),
            latitude="9.981635",
            longitude="76.299889",
            started_at=timezone.now(),
        )
        AttendanceLocationPoint.objects.create(
            attendance=self.attendance,
            transporter=transporter,
            driver=driver,
            vehicle=vehicle,
            point_type=AttendanceLocationPoint.PointType.START,
            latitude="9.981635",
            longitude="76.299889",
            recorded_at=timezone.now(),
        )

    @staticmethod
    def _odo_image():
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

    def test_admin_driver_locations_page_renders_with_session_rows(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_driver_locations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Driver Locations")
        self.assertContains(response, self.attendance.driver.user.username)

    def test_admin_driver_locations_data_endpoint_returns_json(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_driver_locations_data"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("map_points", payload)
        self.assertIn("session_rows", payload)
        self.assertIsInstance(payload["map_points"], list)
        self.assertIsInstance(payload["session_rows"], list)


class AdminDieselTripSheetPageTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_diesel_tripsheet",
            email="admin.diesel.tripsheet@example.com",
            password="AdminPass@123",
        )

        transporter_user = User.objects.create_user(
            username="diesel_tripsheet_transporter",
            password="DieselTripSheetPass@123",
            role=User.Role.TRANSPORTER,
            email="diesel.tripsheet.transporter@example.com",
        )
        transporter = Transporter.objects.create(
            user=transporter_user,
            company_name="Diesel TripSheet Fleet",
            address="HQ",
        )
        self.transporter = transporter

        driver_user = User.objects.create_user(
            username="diesel_tripsheet_driver",
            password="DieselTripSheetPass@123",
            role=User.Role.DRIVER,
            email="diesel.tripsheet.driver@example.com",
        )
        driver = Driver.objects.create(
            user=driver_user,
            transporter=transporter,
            license_number="DL-DIESEL-001",
        )
        self.driver = driver

        self.vehicle = Vehicle.objects.create(
            transporter=transporter,
            vehicle_number="DT-VEH-001",
            model="Route Van",
            status=Vehicle.Status.ACTIVE,
            vehicle_type=Vehicle.Type.GENERAL,
        )

        FuelRecord.objects.create(
            driver=driver,
            vehicle=self.vehicle,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="50.00",
            amount="0.00",
            start_km=1000,
            end_km=1050,
            fuel_filled="50.00",
            indus_site_id="SITE-001",
            site_name="Tower A",
            purpose="Diesel Filling",
            fill_date=timezone.localdate(),
        )

        other_transporter_user = User.objects.create_user(
            username="diesel_tripsheet_transporter_two",
            password="DieselTripSheetPass@123",
            role=User.Role.TRANSPORTER,
            email="diesel.tripsheet.transporter.two@example.com",
        )
        other_transporter = Transporter.objects.create(
            user=other_transporter_user,
            company_name="Diesel TripSheet Fleet Two",
            address="HQ",
        )
        other_driver_user = User.objects.create_user(
            username="diesel_tripsheet_driver_two",
            password="DieselTripSheetPass@123",
            role=User.Role.DRIVER,
            email="diesel.tripsheet.driver.two@example.com",
        )
        other_driver = Driver.objects.create(
            user=other_driver_user,
            transporter=other_transporter,
            license_number="DL-DIESEL-002",
        )
        self.other_vehicle = Vehicle.objects.create(
            transporter=other_transporter,
            vehicle_number="DT-VEH-002",
            model="Route Van",
            status=Vehicle.Status.ACTIVE,
            vehicle_type=Vehicle.Type.GENERAL,
        )
        FuelRecord.objects.create(
            driver=other_driver,
            vehicle=self.other_vehicle,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="40.00",
            amount="0.00",
            start_km=2000,
            end_km=2060,
            fuel_filled="40.00",
            indus_site_id="SITE-002",
            site_name="Tower B",
            purpose="Diesel Filling",
            fill_date=timezone.localdate(),
        )

    @staticmethod
    def _odo_image():
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

    def test_admin_diesel_tripsheet_page_renders_rows(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_diesel_tripsheet"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tower Diesel Trip Sheet")
        self.assertContains(response, self.vehicle.vehicle_number)
        self.assertContains(response, "SITE-001")

    def test_admin_diesel_tripsheet_filters_by_transporter(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse("admin_diesel_tripsheet") + f"?transporter_id={self.transporter.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.vehicle.vehicle_number)
        self.assertNotContains(response, self.other_vehicle.vehicle_number)


class AdminDieselDailyPlanPageTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_diesel_daily_plan",
            email="admin.diesel.daily.plan@example.com",
            password="AdminPass@123",
        )
        transporter_user = User.objects.create_user(
            username="diesel_daily_plan_transporter",
            password="DieselDailyPlanPass@123",
            role=User.Role.TRANSPORTER,
            email="diesel.daily.plan.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=transporter_user,
            company_name="Diesel Daily Plan Fleet",
            address="HQ",
        )
        driver_user = User.objects.create_user(
            username="diesel_daily_plan_driver",
            password="DieselDailyPlanPass@123",
            role=User.Role.DRIVER,
            email="diesel.daily.plan.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=driver_user,
            transporter=self.transporter,
            license_number="DDP-DRIVER-001",
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="DDP-VEH-001",
            model="Route Van",
            status=Vehicle.Status.ACTIVE,
            vehicle_type=Vehicle.Type.GENERAL,
        )
        self.driver.assigned_vehicle = self.vehicle
        self.driver.save(update_fields=["assigned_vehicle"])
        self.site = IndusTowerSite.objects.create(
            partner=self.transporter,
            indus_site_id="3224809",
            site_name="Mulakaramedu",
            latitude="9.981635",
            longitude="76.299889",
        )
        self.target_date = timezone.localdate()
        self.client.force_login(self.admin_user)

    @staticmethod
    def _odo_image():
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

    def _plan_url(self) -> str:
        return (
            f"{reverse('admin_diesel_daily_route_plan')}"
            f"?transporter_id={self.transporter.id}&vehicle_id={self.vehicle.id}&date={self.target_date.isoformat()}"
        )

    def test_admin_daily_plan_allows_text_import_with_only_site_ids(self):
        response = self.client.post(
            self._plan_url(),
            {
                "form_action": "add_bulk_text",
                "replace_existing": "1",
                "bulk_sites": "3224809\n1125570\n1095413",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        plan = DieselDailyRoutePlan.objects.get(vehicle=self.vehicle, plan_date=self.target_date)
        stops = list(plan.stops.order_by("sequence"))
        self.assertEqual(len(stops), 3)
        self.assertEqual(stops[0].indus_site_id, "3224809")
        self.assertEqual(str(stops[0].planned_qty), "0.00")
        self.assertContains(response, "Imported 3 site(s).")

    def test_admin_daily_plan_allows_single_column_csv_import(self):
        uploaded = SimpleUploadedFile(
            "route-sites.csv",
            b"3224809\n1125570\n1095413\n",
            content_type="text/csv",
        )

        response = self.client.post(
            self._plan_url(),
            {
                "form_action": "import_plan_file",
                "replace_existing": "1",
                "plan_file": uploaded,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        plan = DieselDailyRoutePlan.objects.get(vehicle=self.vehicle, plan_date=self.target_date)
        stops = list(plan.stops.order_by("sequence"))
        self.assertEqual(len(stops), 3)
        self.assertEqual(stops[1].indus_site_id, "1125570")
        self.assertEqual(str(stops[1].planned_qty), "0.00")
        self.assertContains(response, "Imported 3 site(s).")

    def test_admin_daily_plan_driver_options_endpoint_returns_assigned_vehicle(self):
        response = self.client.get(
            reverse("admin_diesel_daily_plan_driver_options"),
            {
                "transporter_id": self.transporter.id,
                "selected_driver_id": self.driver.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], self.driver.id)
        self.assertEqual(item["assigned_vehicle_id"], self.vehicle.id)
        self.assertEqual(item["assigned_vehicle_number"], self.vehicle.vehicle_number)
        self.assertTrue(item["selected"])

    def test_admin_daily_plan_site_search_endpoint_supports_name_lookup(self):
        response = self.client.get(
            reverse("admin_diesel_daily_plan_site_search"),
            {
                "transporter_id": self.transporter.id,
                "q": "mulakar",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["indus_site_id"], self.site.indus_site_id)
        self.assertEqual(payload["items"][0]["site_name"], self.site.site_name)

    def test_admin_daily_plan_add_manual_stop_from_searched_site(self):
        response = self.client.post(
            self._plan_url() + f"&driver_id={self.driver.id}",
            {
                "form_action": "add_manual_stop",
                "manual_site_id": self.site.indus_site_id,
                "manual_planned_qty": "40.00",
                "manual_notes": "Priority tower",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        plan = DieselDailyRoutePlan.objects.get(vehicle=self.vehicle, plan_date=self.target_date)
        stop = plan.stops.get()
        self.assertEqual(stop.tower_site_id, self.site.id)
        self.assertEqual(stop.indus_site_id, self.site.indus_site_id)
        self.assertEqual(stop.site_name, self.site.site_name)
        self.assertEqual(str(stop.planned_qty), "40.00")
        self.assertContains(response, "Tower site added to the plan.")

    def test_admin_diesel_tripsheet_prefers_attendance_closing_km(self):
        self.client.force_login(self.admin_user)

        vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="DT-VEH-003",
            model="Route Van",
            status=Vehicle.Status.ACTIVE,
            vehicle_type=Vehicle.Type.GENERAL,
        )
        attendance = Attendance.objects.create(
            driver=self.driver,
            vehicle=vehicle,
            date=timezone.localdate(),
            start_km=102900,
            end_km=103124,
            odo_start_image=self._odo_image(),
            latitude="9.981635",
            longitude="76.299889",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        FuelRecord.objects.create(
            attendance=attendance,
            driver=self.driver,
            vehicle=vehicle,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters="40.00",
            amount="0.00",
            start_km=102900,
            end_km=102900,
            fuel_filled="40.00",
            indus_site_id="SITE-003",
            site_name="Tower C",
            purpose="Diesel Filling",
            fill_date=timezone.localdate(),
        )

        response = self.client.get(
            reverse("admin_diesel_tripsheet") + f"?vehicle_id={vehicle.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "102900")
        self.assertContains(response, "103124")

    def test_admin_diesel_tripsheet_pdf_downloads(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_diesel_tripsheet") + "?download=pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))


class AdminAccountDeletionMonitorTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_deletion_monitor",
            email="admin.deletion.monitor@example.com",
            password="AdminPass@123",
        )
        self.target_user = User.objects.create_user(
            username="delete_me_driver",
            password="DeletePass@123",
            role=User.Role.DRIVER,
            email="delete.me@example.com",
            phone="9000000021",
        )
        self.transporter_user = User.objects.create_user(
            username="delete_monitor_transporter",
            password="DeletePass@123",
            role=User.Role.TRANSPORTER,
            email="delete.monitor.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Deletion Monitor Fleet",
            address="HQ",
        )
        Driver.objects.create(
            user=self.target_user,
            transporter=self.transporter,
            license_number="DEL-MON-001",
        )
        self.deletion_request = AccountDeletionRequest.objects.create(
            email=self.target_user.email,
            role=self.target_user.role,
            user=self.target_user,
            source=AccountDeletionRequest.Source.WEB,
            note="Please delete this account.",
            status=AccountDeletionRequest.Status.REQUESTED,
        )

    def test_admin_account_deletion_monitor_page_renders(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_account_deletion_requests"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account Deletion Monitor")
        self.assertContains(response, self.deletion_request.email)

    def test_admin_can_process_account_deletion_request(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse(
                "admin_process_account_deletion_request",
                args=[self.deletion_request.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.deletion_request.refresh_from_db()
        self.target_user.refresh_from_db()
        self.assertEqual(
            self.deletion_request.status,
            AccountDeletionRequest.Status.COMPLETED,
        )
        self.assertFalse(self.target_user.is_active)
        self.assertEqual(self.deletion_request.processed_by, self.admin_user)


class AdminServerHealthUnlockTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin_server_health",
            email="admin.server.health@example.com",
            password="AdminPass@123",
        )

    @override_settings(SERVER_HEALTH_PASSWORD="health-pass", SERVER_HEALTH_PASSWORD_HASH="")
    def test_server_health_requires_unlock_and_allows_unlock(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_server_health"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Server Health Locked")

        response = self.client.post(
            reverse("admin_server_health"),
            {
                "form_action": "unlock_server_health",
                "server_health_password": "health-pass",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Server Health And Backup Control")

    @override_settings(SERVER_HEALTH_PASSWORD="health-pass", SERVER_HEALTH_PASSWORD_HASH="")
    def test_backup_metadata_download_requires_unlock(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin_backup_metadata_download"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin_server_health"), response["Location"])

        self.client.post(
            reverse("admin_server_health"),
            {
                "form_action": "unlock_server_health",
                "server_health_password": "health-pass",
            },
        )

        response = self.client.get(reverse("admin_backup_metadata_download"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
