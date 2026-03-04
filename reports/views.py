from django.contrib.auth import get_user_model
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from reports.serializers import MonthlyReportSerializer

User = get_user_model()


class MonthlyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
        except ValueError:
            return Response(
                {"detail": "Month and year must be numeric values."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vehicle_id = request.query_params.get("vehicle_id")

        if month < 1 or month > 12:
            return Response(
                {"detail": "Month must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendances = Attendance.objects.filter(date__year=year, date__month=month)
        user = request.user

        if user.role == User.Role.TRANSPORTER:
            if not hasattr(user, "transporter_profile"):
                return Response(
                    {"detail": "Transporter profile does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            attendances = attendances.filter(vehicle__transporter=user.transporter_profile)
        elif user.role == User.Role.DRIVER:
            if not hasattr(user, "driver_profile"):
                return Response(
                    {"detail": "Driver profile does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            attendances = attendances.filter(driver=user.driver_profile)

        if vehicle_id:
            attendances = attendances.filter(vehicle_id=vehicle_id)

        attendances = attendances.annotate(
            normalized_end_km=Coalesce(F("end_km"), F("start_km")),
            computed_total_km=Coalesce(F("end_km"), F("start_km")) - F("start_km"),
        ).order_by("date")

        rows = [
            {
                "date": attendance.date,
                "start_km": attendance.start_km,
                "end_km": attendance.normalized_end_km,
                "total_km": max(attendance.computed_total_km, 0),
            }
            for attendance in attendances
        ]

        payload = {
            "month": month,
            "year": year,
            "vehicle_id": int(vehicle_id) if vehicle_id else None,
            "total_days": len(rows),
            "total_km": sum(row["total_km"] for row in rows),
            "rows": rows,
        }

        serializer = MonthlyReportSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
