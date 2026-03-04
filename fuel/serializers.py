from rest_framework import serializers

from fuel.models import FuelRecord


class FuelRecordSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)

    class Meta:
        model = FuelRecord
        fields = (
            "id",
            "attendance",
            "driver",
            "driver_name",
            "vehicle",
            "vehicle_number",
            "liters",
            "amount",
            "meter_image",
            "bill_image",
            "date",
            "created_at",
        )
        read_only_fields = ("attendance", "driver", "vehicle")


class FuelRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelRecord
        fields = ("liters", "amount", "meter_image", "bill_image", "date")

    def create(self, validated_data):
        attendance = self.context["attendance"]
        driver = self.context["driver"]
        vehicle = attendance.vehicle
        return FuelRecord.objects.create(
            attendance=attendance,
            driver=driver,
            vehicle=vehicle,
            **validated_data,
        )
