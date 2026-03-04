from rest_framework import serializers

from drivers.models import Driver


class DriverSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    transporter_company = serializers.CharField(
        source="transporter.company_name", read_only=True
    )
    vehicle_number = serializers.CharField(
        source="assigned_vehicle.vehicle_number", read_only=True
    )

    class Meta:
        model = Driver
        fields = (
            "id",
            "username",
            "phone",
            "license_number",
            "transporter",
            "transporter_company",
            "assigned_vehicle",
            "vehicle_number",
            "is_active",
        )
