from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drivers.models import Driver
from drivers.serializers import (
    DriverAllocationOtpRequestSerializer,
    DriverAllocationVerifySerializer,
    DriverVehicleAssignmentSerializer,
    DriverSerializer,
)
from users.permissions import IsTransporterRole

User = get_user_model()


class DriverListView(generics.ListAPIView):
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == User.Role.ADMIN:
            return Driver.objects.select_related(
                "user", "transporter", "assigned_vehicle"
            )

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return Driver.objects.filter(transporter=user.transporter_profile).select_related(
                "user", "transporter", "assigned_vehicle"
            )

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            return Driver.objects.filter(id=user.driver_profile.id).select_related(
                "user", "transporter", "assigned_vehicle"
            )

        return Driver.objects.none()


class DriverAllocationOtpRequestView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        serializer = DriverAllocationOtpRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "Driver allocation OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class DriverAllocationVerifyView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        serializer = DriverAllocationVerifySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        payload = {
            "detail": "Driver allocated successfully.",
            "driver": DriverSerializer(driver).data,
        }
        return Response(payload, status=status.HTTP_200_OK)


class DriverVehicleAssignmentView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def patch(self, request, driver_id: int):
        try:
            driver = Driver.objects.select_related(
                "user",
                "transporter",
                "assigned_vehicle",
            ).get(pk=driver_id)
        except Driver.DoesNotExist:
            return Response(
                {"detail": "Driver not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DriverVehicleAssignmentSerializer(
            data=request.data,
            context={
                "request": request,
                "driver": driver,
            },
        )
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        payload = {
            "detail": "Driver vehicle updated successfully.",
            "driver": DriverSerializer(driver).data,
        }
        return Response(payload, status=status.HTTP_200_OK)
