from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient, APISimpleTestCase

from services.route_optimizer import (
    MAX_TOWERS_PER_REQUEST,
    optimize_route,
    optimize_route_path,
)

User = get_user_model()


def _build_osrm_payload(matrix: list[list[float]]) -> dict:
    return {
        "code": "Ok",
        "distances": matrix,
        "durations": matrix,
    }


class RouteOptimizerServiceTests(APISimpleTestCase):
    @mock.patch("services.route_optimizer.requests.get")
    def test_basic_case_with_three_towers(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = _build_osrm_payload(
            [
                [0, 1000, 4000, 5000],
                [1000, 0, 1000, 4000],
                [4000, 1000, 0, 1000],
                [5000, 4000, 1000, 0],
            ]
        )

        result = optimize_route(
            depot=(8.6, 76.9),
            towers=[
                (8.61, 76.91),
                (8.62, 76.92),
                (8.63, 76.93),
            ],
        )

        self.assertEqual(result["route"][0], 0)
        self.assertEqual(result["route"][-1], 0)
        self.assertEqual(set(result["route"][1:-1]), {1, 2, 3})
        self.assertEqual(len(result["ordered_coordinates"]), 5)

    @mock.patch("services.route_optimizer.requests.get")
    def test_single_tower(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = _build_osrm_payload(
            [
                [0, 2200],
                [2200, 0],
            ]
        )

        result = optimize_route(
            depot=(8.6, 76.9),
            towers=[(8.61, 76.91)],
        )

        self.assertEqual(result["route"], [0, 1, 0])
        self.assertEqual(result["ordered_coordinates"][0], (8.6, 76.9))
        self.assertEqual(result["ordered_coordinates"][-1], (8.6, 76.9))

    @mock.patch("services.route_optimizer.requests.get")
    def test_open_path_route_does_not_force_return_to_start(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = _build_osrm_payload(
            [
                [0, 1000, 3000, 4500],
                [1000, 0, 1200, 2800],
                [3000, 1200, 0, 900],
                [4500, 2800, 900, 0],
            ]
        )

        result = optimize_route_path(
            start=(8.6, 76.9),
            towers=[
                (8.61, 76.91),
                (8.62, 76.92),
                (8.63, 76.93),
            ],
            return_to_start=False,
        )

        self.assertEqual(result["route"][0], 0)
        self.assertNotEqual(result["route"][-1], 0)
        self.assertEqual(set(result["route"][1:]), {1, 2, 3})
        self.assertEqual(result["mode"], "road")

    def test_no_towers_raises_validation_error(self):
        with self.assertRaisesMessage(ValueError, "towers must contain at least one"):
            optimize_route(depot=(8.6, 76.9), towers=[])

    def test_invalid_input_raises_validation_error(self):
        with self.assertRaisesMessage(ValueError, "tower #1 latitude must be between -90 and 90."):
            optimize_route(
                depot=(8.6, 76.9),
                towers=[(120.0, 76.9)],
            )

    @mock.patch("services.route_optimizer.requests.get")
    def test_large_input_twenty_towers(self, mock_get):
        size = 21
        matrix = []
        for row in range(size):
            matrix_row = []
            for col in range(size):
                matrix_row.append(abs(col - row) * 1000)
            matrix.append(matrix_row)

        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = _build_osrm_payload(matrix)

        towers = [(8.6 + index * 0.001, 76.9 + index * 0.001) for index in range(1, 21)]
        result = optimize_route(depot=(8.6, 76.9), towers=towers)

        self.assertEqual(result["route"][0], 0)
        self.assertEqual(result["route"][-1], 0)
        self.assertEqual(len(result["route"]), 22)
        self.assertEqual(set(result["route"][1:-1]), set(range(1, 21)))


class RouteOptimizerApiTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="route-api-user",
            password="SafePass@123",
            role=User.Role.ADMIN,
            email="route.api@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @mock.patch("api.views.optimize_route")
    def test_optimize_route_endpoint_returns_success(self, optimize_route_mock):
        optimize_route_mock.return_value = {
            "route": [0, 2, 1, 0],
            "distance": 42.5,
            "ordered_coordinates": [
                (8.6, 76.9),
                (8.5, 76.8),
                (8.7, 77.0),
                (8.6, 76.9),
            ],
        }

        response = self.client.post(
            reverse("optimize-route"),
            {
                "depot": [8.6, 76.9],
                "towers": [
                    [8.7, 77.0],
                    [8.5, 76.8],
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["route"], [0, 2, 1, 0])
        self.assertEqual(response.data["distance"], 42.5)

    def test_optimize_route_endpoint_rejects_empty_towers(self):
        response = self.client.post(
            reverse("optimize-route"),
            {
                "depot": [8.6, 76.9],
                "towers": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("towers", response.data["detail"])

    def test_optimize_route_endpoint_rejects_large_request(self):
        towers = [[8.6 + index * 0.001, 76.9 + index * 0.001] for index in range(MAX_TOWERS_PER_REQUEST + 1)]
        response = self.client.post(
            reverse("optimize-route"),
            {
                "depot": [8.6, 76.9],
                "towers": towers,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
