from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from vehicles.models import Vehicle
from vehicles.serializers import VehicleCreateSerializer, VehicleSerializer

User = get_user_model()


class VehicleListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return VehicleCreateSerializer
        return VehicleSerializer

    def get_queryset(self):
        user = self.request.user

        if user.role == User.Role.ADMIN:
            return Vehicle.objects.select_related("transporter", "transporter__user")

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return Vehicle.objects.filter(
                transporter=user.transporter_profile
            ).select_related("transporter", "transporter__user")

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            driver = user.driver_profile
            if driver.transporter_id is None:
                return Vehicle.objects.none()
            return Vehicle.objects.filter(transporter_id=driver.transporter_id).select_related(
                "transporter", "transporter__user"
            )

        return Vehicle.objects.none()

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role != User.Role.TRANSPORTER or not hasattr(user, "transporter_profile"):
            return Response(
                {"detail": "Only transporter accounts can add vehicles."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(transporter=self.request.user.transporter_profile)
