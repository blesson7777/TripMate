from django.utils import timezone
from rest_framework import serializers

from attendance.models import Attendance
from vehicles.models import Vehicle


class AttendanceSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)
    trips_count = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = (
            "id",
            "driver",
            "driver_name",
            "vehicle",
            "vehicle_number",
            "date",
            "status",
            "start_km",
            "end_km",
            "odo_start_image",
            "odo_end_image",
            "latitude",
            "longitude",
            "started_at",
            "ended_at",
            "trips_count",
        )

    def get_trips_count(self, obj):
        return obj.trips.count()


class AttendanceStartSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField(required=False)
    start_km = serializers.IntegerField(min_value=0)
    odo_start_image = serializers.ImageField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)

    def validate(self, attrs):
        user = self.context["request"].user
        if not hasattr(user, "driver_profile"):
            raise serializers.ValidationError("Driver profile does not exist.")

        driver = user.driver_profile
        attendance_date = timezone.localdate()
        if Attendance.objects.filter(driver=driver, date=attendance_date).exists():
            raise serializers.ValidationError("Attendance already marked for today.")

        vehicle_id = attrs.get("vehicle_id")
        if vehicle_id:
            vehicle = Vehicle.objects.filter(id=vehicle_id).first()
            if not vehicle:
                raise serializers.ValidationError("Vehicle does not exist.")
        else:
            vehicle = driver.assigned_vehicle
            if not vehicle:
                raise serializers.ValidationError(
                    "No assigned vehicle found. Provide vehicle_id."
                )

        if vehicle.transporter_id != driver.transporter_id:
            raise serializers.ValidationError(
                "Selected vehicle is not managed by the driver's transporter."
            )

        attrs["driver"] = driver
        attrs["vehicle"] = vehicle
        attrs["date"] = attendance_date
        return attrs

    def create(self, validated_data):
        driver = validated_data["driver"]
        vehicle = validated_data["vehicle"]
        return Attendance.objects.create(
            driver=driver,
            vehicle=vehicle,
            date=validated_data["date"],
            start_km=validated_data["start_km"],
            odo_start_image=validated_data["odo_start_image"],
            latitude=validated_data["latitude"],
            longitude=validated_data["longitude"],
            status=Attendance.Status.ON_DUTY,
        )


class AttendanceEndSerializer(serializers.Serializer):
    end_km = serializers.IntegerField(min_value=0)
    odo_end_image = serializers.ImageField(required=False, allow_null=True)

    def validate_end_km(self, value):
        attendance = self.instance
        if attendance and value < attendance.start_km:
            raise serializers.ValidationError(
                "End KM must be greater than or equal to start KM."
            )
        return value

    def update(self, instance, validated_data):
        instance.end_km = validated_data["end_km"]
        if "odo_end_image" in validated_data:
            instance.odo_end_image = validated_data["odo_end_image"]
        instance.ended_at = timezone.now()

        if instance.status == Attendance.Status.ON_DUTY and not instance.trips.exists():
            instance.status = Attendance.Status.NO_TRIP

        instance.save()
        return instance
