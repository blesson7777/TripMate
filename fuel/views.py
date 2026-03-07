from datetime import date, timedelta

from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from fuel.models import FuelRecord
from fuel.serializers import FuelRecordCreateSerializer, FuelRecordSerializer
from users.notification_utils import detect_and_notify_fuel_anomaly
from users.permissions import IsDriverRole

User = get_user_model()


def _vehicle_fuel_queryset_for_user(user):
    queryset = FuelRecord.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "attendance",
    ).filter(entry_type=FuelRecord.EntryType.VEHICLE_FILLING)

    if user.role == User.Role.ADMIN:
        return queryset

    if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
        return queryset.filter(vehicle__transporter=user.transporter_profile)

    if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
        if user.driver_profile.transporter_id is None:
            return FuelRecord.objects.none()
        return queryset.filter(
            driver=user.driver_profile,
            vehicle__transporter_id=user.driver_profile.transporter_id,
        )

    return FuelRecord.objects.none()


def _get_active_attendance_for_vehicle_fuel(driver):
    if driver.transporter_id is None:
        return None

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    return (
        Attendance.objects.select_related("vehicle")
        .filter(
            driver=driver,
            ended_at__isnull=True,
            date__in=[today, yesterday],
            vehicle__transporter_id=driver.transporter_id,
        )
        .order_by("-started_at")
        .first()
    )


class FuelAddView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        if not hasattr(request.user, "driver_profile"):
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent old mixed payload usage and force tower workflow into diesel module.
        requested_entry_type = (
            str(request.data.get("entry_type", "")).strip().upper() or "VEHICLE_FILLING"
        )
        if requested_entry_type == FuelRecord.EntryType.TOWER_DIESEL:
            return Response(
                {
                    "detail": (
                        "Tower diesel filling is a separate module. "
                        "Use /api/diesel/add."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.data.copy()
        payload.pop("entry_type", None)

        attendance = _get_active_attendance_for_vehicle_fuel(
            request.user.driver_profile
        )

        serializer = FuelRecordCreateSerializer(
            data=payload,
            context={"attendance": attendance, "driver": request.user.driver_profile},
        )
        serializer.is_valid(raise_exception=True)
        fuel_record = serializer.save()
        detect_and_notify_fuel_anomaly(fuel_record)
        return Response(
            FuelRecordSerializer(fuel_record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class FuelRecordListView(generics.ListAPIView):
    serializer_class = FuelRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = _vehicle_fuel_queryset_for_user(user)

        vehicle_id = self.request.query_params.get("vehicle_id")
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        fill_date = self.request.query_params.get("fill_date")
        if fill_date:
            try:
                parsed_fill_date = date.fromisoformat(fill_date)
            except ValueError:
                return FuelRecord.objects.none()
            queryset = queryset.filter(date=parsed_fill_date)

        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")
        if month and year:
            try:
                queryset = queryset.filter(date__month=int(month), date__year=int(year))
            except ValueError:
                return FuelRecord.objects.none()

        return queryset.order_by("-date", "-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class FuelRecordDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, record_id):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER}:
            return Response(
                {"detail": "Only admin or transporter can delete fuel entries."},
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = _vehicle_fuel_queryset_for_user(request.user)
        record = queryset.filter(id=record_id).first()
        if record is None:
            return Response({"detail": "Fuel record not found."}, status=status.HTTP_404_NOT_FOUND)

        record.delete()
        return Response({"detail": "Fuel record deleted successfully."}, status=status.HTTP_200_OK)
