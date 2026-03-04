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
