from datetime import datetime

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance, DriverDailyAttendanceMark
from attendance.serializers import (
    AttendanceEndSerializer,
    DriverAttendanceMarkRequestSerializer,
    AttendanceSerializer,
    AttendanceStartSerializer,
)
from drivers.models import Driver
from users.permissions import IsDriverRole, IsTransporterRole


class AttendanceStartView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        serializer = AttendanceStartSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()
        response_serializer = AttendanceSerializer(attendance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class AttendanceEndView(APIView):
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
                {"detail": "No attendance found for today."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AttendanceEndSerializer(instance=attendance, data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()

        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_200_OK)


class DailyAttendanceOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        target_date = request.query_params.get("date")
        if target_date:
            try:
                target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        transporter = request.user.transporter_profile
        drivers = list(
            Driver.objects.filter(transporter=transporter)
            .select_related("user", "assigned_vehicle")
            .order_by("user__username")
        )
        attendances = {
            attendance.driver_id: attendance
            for attendance in Attendance.objects.filter(
                driver__in=drivers,
                date=target_date,
            ).select_related("vehicle")
        }
        marks = {
            mark.driver_id: mark
            for mark in DriverDailyAttendanceMark.objects.filter(
                driver__in=drivers,
                date=target_date,
            )
        }

        items = []
        for driver in drivers:
            attendance = attendances.get(driver.id)
            mark = marks.get(driver.id)

            if attendance is not None:
                status_value = attendance.status
            elif mark is not None:
                status_value = mark.status
            else:
                status_value = "ABSENT"

            items.append(
                {
                    "driver_id": driver.id,
                    "driver_name": driver.user.username,
                    "license_number": driver.license_number,
                    "assigned_vehicle_number": (
                        driver.assigned_vehicle.vehicle_number
                        if driver.assigned_vehicle is not None
                        else None
                    ),
                    "date": target_date,
                    "status": status_value,
                    "mark_status": mark.status if mark is not None else None,
                    "has_mark": mark is not None,
                    "has_attendance": attendance is not None,
                    "attendance_vehicle_number": (
                        attendance.vehicle.vehicle_number if attendance is not None else None
                    ),
                    "started_at": attendance.started_at if attendance is not None else None,
                    "ended_at": attendance.ended_at if attendance is not None else None,
                    "start_km": attendance.start_km if attendance is not None else None,
                    "end_km": attendance.end_km if attendance is not None else None,
                    "can_start_day": (
                        attendance is None
                        and (mark is None or mark.status != "ABSENT")
                    ),
                }
            )

        return Response(
            {
                "date": target_date,
                "items": items,
            },
            status=status.HTTP_200_OK,
        )


class DailyAttendanceMarkView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        serializer = DriverAttendanceMarkRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        mark = serializer.save()

        return Response(
            {
                "detail": "Attendance mark updated successfully.",
                "driver_id": mark.driver_id,
                "date": mark.date,
                "status": mark.status,
            },
            status=status.HTTP_200_OK,
        )
