from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.models import Trip
from trips.serializers import (
    TripCloseSerializer,
    TripCreateSerializer,
    TripSerializer,
    get_or_create_master_trip,
    get_today_attendance_for_driver,
)
from users.permissions import IsDriverRole

User = get_user_model()


class TripCreateView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        if not hasattr(request.user, "driver_profile"):
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendance = get_today_attendance_for_driver(request.user.driver_profile)
        if not attendance:
            return Response(
                {"detail": "Start day before starting a trip."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        master_trip = get_or_create_master_trip(attendance)
        if (
            attendance.trips.filter(
                status=Trip.Status.OPEN,
                parent_trip=master_trip,
            ).exists()
        ):
            return Response(
                {"detail": "Close the current open trip before starting another one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TripCreateSerializer(data=request.data, context={"attendance": attendance})
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        return Response(
            TripSerializer(trip, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TripCloseView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request, trip_id):
        if not hasattr(request.user, "driver_profile"):
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        trip = (
            Trip.objects.select_related("attendance", "attendance__driver")
            .filter(pk=trip_id, attendance__driver=request.user.driver_profile)
            .first()
        )
        if trip is None:
            return Response(
                {"detail": "Trip not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if trip.status == Trip.Status.CLOSED:
            return Response(
                {"detail": "Trip is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if trip.is_day_trip:
            return Response(
                {"detail": "Master day trip closes only with End Day."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TripCloseSerializer(instance=trip, data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()
        return Response(
            TripSerializer(trip, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class TripListView(generics.ListAPIView):
    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Trip.objects.select_related(
            "attendance",
            "attendance__driver",
            "attendance__driver__user",
            "attendance__vehicle",
            "attendance__vehicle__transporter",
            "parent_trip",
        ).prefetch_related("child_trips")

        if user.role == User.Role.ADMIN:
            return queryset

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return queryset.filter(
                attendance__driver__transporter=user.transporter_profile
            )

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            return queryset.filter(attendance__driver=user.driver_profile)

        return Trip.objects.none()


class TripDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, trip_id):
        trip = self._get_scoped_queryset(request.user).filter(pk=trip_id).first()
        if trip is None:
            return Response(
                {"detail": "Trip not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        parent_trip = trip if (trip.is_day_trip and trip.parent_trip_id is None) else trip.parent_trip
        if parent_trip is None:
            parent_trip = trip

        children = (
            self._get_scoped_queryset(request.user)
            .filter(parent_trip=parent_trip)
            .order_by("started_at", "created_at")
        )

        return Response(
            {
                "master_trip": TripSerializer(parent_trip, context={"request": request}).data,
                "child_trips": TripSerializer(
                    children,
                    many=True,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )

    def _get_scoped_queryset(self, user):
        queryset = Trip.objects.select_related(
            "attendance",
            "attendance__driver",
            "attendance__driver__user",
            "attendance__vehicle",
            "attendance__vehicle__transporter",
            "parent_trip",
        ).prefetch_related("child_trips")

        if user.role == User.Role.ADMIN:
            return queryset

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return queryset.filter(
                attendance__driver__transporter=user.transporter_profile
            )

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            return queryset.filter(attendance__driver=user.driver_profile)

        return Trip.objects.none()
