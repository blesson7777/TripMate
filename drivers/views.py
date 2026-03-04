from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from drivers.models import Driver
from drivers.serializers import DriverSerializer

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
