from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from services.route_optimizer import MAX_TOWERS_PER_REQUEST, RouteOptimizerError, optimize_route


class OptimizeRouteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        depot = payload.get("depot")
        towers = payload.get("towers")

        if depot is None:
            return Response(
                {"detail": "depot is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if towers is None:
            return Response(
                {"detail": "towers is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(towers, list):
            return Response(
                {"detail": "towers must be a list of [latitude, longitude] pairs."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not towers:
            return Response(
                {"detail": "towers must contain at least one coordinate pair."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(towers) > MAX_TOWERS_PER_REQUEST:
            return Response(
                {
                    "detail": (
                        f"towers cannot contain more than {MAX_TOWERS_PER_REQUEST} items."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = optimize_route(depot=depot, towers=towers)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RouteOptimizerError:
            return Response(
                {"detail": "Unable to optimize the route right now."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            return Response(
                {"detail": "Unexpected error while optimizing the route."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "route": result["route"],
                "distance": result["distance"],
                "ordered_coordinates": [
                    [latitude, longitude]
                    for latitude, longitude in result["ordered_coordinates"]
                ],
            },
            status=status.HTTP_200_OK,
        )
