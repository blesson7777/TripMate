from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from drivers.models import Driver
from fuel.models import FuelRecord
from users.models import Transporter, User
from vehicles.models import Vehicle


class VehicleCreateTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="vehicle_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="vehicle.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Fleet Builders",
            address="Main Yard",
        )

        self.driver_user = User.objects.create_user(
            username="vehicle_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="vehicle.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="VEH-LIC-001",
        )

    def _image(self, name="test.gif"):
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

    def test_transporter_can_create_vehicle(self):
        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.post(
            reverse("vehicle-list"),
            {
                "vehicle_number": "WB01AA1234",
                "model": "Tata Ace",
                "status": "ACTIVE",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Vehicle.objects.filter(
                transporter=self.transporter,
                vehicle_number="WB01AA1234",
            ).exists()
        )

    def test_driver_cannot_create_vehicle(self):
        self.client.force_authenticate(user=self.driver_user)
        response = self.client.post(
            reverse("vehicle-list"),
            {
                "vehicle_number": "WB01AA9999",
                "model": "Mini Truck",
                "status": "ACTIVE",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_transporter_cannot_create_vehicle_with_existing_number_from_another_transporter(self):
        other_user = User.objects.create_user(
            username="vehicle_transporter_two",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="vehicle.transporter.two@example.com",
        )
        other_transporter = Transporter.objects.create(
            user=other_user,
            company_name="Other Fleet",
            address="Branch",
        )
        Vehicle.objects.create(
            transporter=other_transporter,
            vehicle_number="WB01AA1234",
            model="Existing Truck",
            status=Vehicle.Status.ACTIVE,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.post(
            reverse("vehicle-list"),
            {
                "vehicle_number": "wb01aa1234",
                "model": "Tata Ace",
                "status": "ACTIVE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", str(response.data))

    def test_driver_can_list_transporter_vehicles_for_selection(self):
        vehicle_one = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="WB01AA1234",
            model="Tata Ace",
            status=Vehicle.Status.ACTIVE,
        )
        vehicle_two = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="WB01AA5678",
            model="Mahindra Jeeto",
            status=Vehicle.Status.ACTIVE,
        )
        self.driver.assigned_vehicle = vehicle_one
        self.driver.save(update_fields=["assigned_vehicle"])

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(reverse("vehicle-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        numbers = {item["vehicle_number"] for item in response.data}
        self.assertEqual(numbers, {"WB01AA1234", "WB01AA5678"})

    def test_vehicle_list_includes_tank_capacity_and_odometer_source(self):
        vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="WB01AA9000",
            model="Ashok Leyland",
            status=Vehicle.Status.ACTIVE,
            tank_capacity_liters="55.00",
        )
        FuelRecord.objects.create(
            attendance=None,
            driver=self.driver,
            vehicle=vehicle,
            partner=self.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            liters="20.00",
            fuel_filled="20.00",
            amount="2200.00",
            odometer_km=1234,
            meter_image=self._image("meter.gif"),
            bill_image=self._image("bill.gif"),
        )

        self.client.force_authenticate(user=self.driver_user)
        response = self.client.get(reverse("vehicle-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target = next(
            item for item in response.data if item["vehicle_number"] == "WB01AA9000"
        )
        self.assertEqual(target["tank_capacity_liters"], "55.00")
        self.assertEqual(target["latest_odometer_km"], 1234)
        self.assertEqual(target["latest_odometer_source"], "fuel")
