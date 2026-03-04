from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from attendance.serializers import (
    AttendanceEndSerializer,
    AttendanceSerializer,
    AttendanceStartSerializer,
)
from users.permissions import IsDriverRole


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
