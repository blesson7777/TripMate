from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from drivers.models import Driver
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
