from rest_framework import serializers

from vehicles.models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    transporter_id = serializers.IntegerField(source="transporter.id", read_only=True)
    transporter_company = serializers.CharField(
        source="transporter.company_name", read_only=True
    )

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "transporter_id",
            "transporter_company",
            "vehicle_number",
            "model",
            "status",
            "created_at",
        )


class VehicleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ("vehicle_number", "model", "status")

    def validate_vehicle_number(self, value):
        normalized = value.strip().upper()
        transporter = self.context["request"].user.transporter_profile
        if Vehicle.objects.filter(
            transporter=transporter,
            vehicle_number__iexact=normalized,
        ).exists():
            raise serializers.ValidationError(
                "A vehicle with this number already exists for your transporter."
            )
        return normalized
