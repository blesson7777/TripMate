from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from fuel.models import FuelRecord
from fuel.serializers import FuelRecordCreateSerializer, FuelRecordSerializer
from users.permissions import IsDriverRole

User = get_user_model()


class FuelAddView(APIView):
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
            )
            .order_by("-started_at")
            .first()
        )

        if not attendance:
            return Response(
                {"detail": "Attendance must be started before adding fuel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FuelRecordCreateSerializer(
            data=request.data,
            context={"attendance": attendance, "driver": request.user.driver_profile},
        )
        serializer.is_valid(raise_exception=True)
        fuel_record = serializer.save()
        return Response(FuelRecordSerializer(fuel_record).data, status=status.HTTP_201_CREATED)


class FuelRecordListView(generics.ListAPIView):
    serializer_class = FuelRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = FuelRecord.objects.select_related("driver", "driver__user", "vehicle", "attendance")

        if user.role == User.Role.ADMIN:
            return queryset

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return queryset.filter(driver__transporter=user.transporter_profile)

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            return queryset.filter(driver=user.driver_profile)

        return FuelRecord.objects.none()
