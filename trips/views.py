from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from trips.models import Trip
from trips.serializers import TripCreateSerializer, TripSerializer
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

        attendance = (
            Attendance.objects.filter(
                driver=request.user.driver_profile,
                date=timezone.localdate(),
                ended_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        if not attendance:
            return Response(
                {"detail": "Attendance not started."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TripCreateSerializer(data=request.data, context={"attendance": attendance})
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()

        if attendance.status == Attendance.Status.NO_TRIP:
            attendance.status = Attendance.Status.ON_DUTY
            attendance.save(update_fields=["status"])

        return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


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
        )

        if user.role == User.Role.ADMIN:
            return queryset

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return queryset.filter(
                attendance__driver__transporter=user.transporter_profile
            )

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            return queryset.filter(attendance__driver=user.driver_profile)

        return Trip.objects.none()
