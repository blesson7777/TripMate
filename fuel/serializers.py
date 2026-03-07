from rest_framework import serializers

from fuel.models import FuelRecord
from tripmate.odometer_utils import get_latest_vehicle_odometer
from vehicles.models import Vehicle

MAX_ODOMETER_SUBMISSION_DELTA_KM = 300


class FuelRecordSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)
    meter_image_url = serializers.SerializerMethodField()
    bill_image_url = serializers.SerializerMethodField()

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
            "odometer_km",
            "meter_image",
            "meter_image_url",
            "bill_image",
            "bill_image_url",
            "date",
            "created_at",
        )
        read_only_fields = ("attendance", "driver", "vehicle")

    def _absolute_media_url(self, field_file):
        if not field_file:
            return ""
        request = self.context.get("request")
        if request is None:
            return field_file.url
        return request.build_absolute_uri(field_file.url)

    def get_meter_image_url(self, obj):
        return self._absolute_media_url(obj.meter_image)

    def get_bill_image_url(self, obj):
        return self._absolute_media_url(obj.bill_image)


class FuelRecordCreateSerializer(serializers.ModelSerializer):
    odometer_km = serializers.IntegerField(min_value=0)
    vehicle_id = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = FuelRecord
        fields = (
            "vehicle_id",
            "liters",
            "amount",
            "odometer_km",
            "meter_image",
            "bill_image",
            "date",
        )

    def validate(self, attrs):
        driver = self.context["driver"]
        attendance = self.context.get("attendance")
        vehicle_id = attrs.get("vehicle_id")

        if attendance is not None:
            vehicle = attendance.vehicle
            if vehicle_id is not None and vehicle_id != attendance.vehicle_id:
                raise serializers.ValidationError(
                    {
                        "vehicle_id": (
                            "Vehicle is auto-selected from the active day trip."
                        )
                    }
                )
        else:
            if vehicle_id is None:
                raise serializers.ValidationError(
                    {"vehicle_id": "Select a vehicle when no active day trip exists."}
                )

            vehicle = Vehicle.objects.filter(
                id=vehicle_id,
                transporter_id=driver.transporter_id,
            ).first()
            if vehicle is None:
                raise serializers.ValidationError(
                    {"vehicle_id": "Selected vehicle is not available for your transporter."}
                )

        latest_odometer = get_latest_vehicle_odometer(vehicle)
        input_odometer = attrs.get("odometer_km")
        if (
            latest_odometer is not None
            and input_odometer is not None
            and input_odometer < latest_odometer
        ):
            raise serializers.ValidationError(
                {
                    "odometer_km": (
                        "Odometer KM cannot be less than the latest recorded "
                        f"odometer for this vehicle ({latest_odometer})."
                    )
                }
            )
        if (
            latest_odometer is not None
            and input_odometer is not None
            and input_odometer > latest_odometer + MAX_ODOMETER_SUBMISSION_DELTA_KM
        ):
            raise serializers.ValidationError(
                {
                    "odometer_km": (
                        "Odometer KM cannot be greater than the latest recorded "
                        f"odometer by more than {MAX_ODOMETER_SUBMISSION_DELTA_KM} km "
                        f"for this vehicle ({latest_odometer})."
                    )
                }
            )

        attrs["_resolved_vehicle"] = vehicle
        return attrs

    def create(self, validated_data):
        attendance = self.context["attendance"]
        driver = self.context["driver"]
        validated_data.pop("vehicle_id", None)
        vehicle = validated_data.pop("_resolved_vehicle")
        return FuelRecord.objects.create(
            attendance=attendance,
            driver=driver,
            vehicle=vehicle,
            partner=driver.transporter,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            **validated_data,
        )
