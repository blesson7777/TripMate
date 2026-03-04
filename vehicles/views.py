from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from vehicles.models import Vehicle
from vehicles.serializers import VehicleSerializer

User = get_user_model()


class VehicleListView(generics.ListAPIView):
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == User.Role.ADMIN:
            return Vehicle.objects.select_related("transporter", "transporter__user")

        if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
            return Vehicle.objects.filter(
                transporter=user.transporter_profile
            ).select_related("transporter", "transporter__user")

        if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
            assigned_vehicle_id = user.driver_profile.assigned_vehicle_id
            if not assigned_vehicle_id:
                return Vehicle.objects.none()
            return Vehicle.objects.filter(id=assigned_vehicle_id).select_related(
                "transporter", "transporter__user"
            )

        return Vehicle.objects.none()
