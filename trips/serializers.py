from django.utils import timezone
from rest_framework import serializers

from attendance.models import Attendance
from trips.models import Trip


class TripSerializer(serializers.ModelSerializer):
    attendance_date = serializers.DateField(source="attendance.date", read_only=True)
    driver_name = serializers.CharField(source="attendance.driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="attendance.vehicle.vehicle_number", read_only=True)

    class Meta:
        model = Trip
        fields = (
            "id",
            "attendance",
            "attendance_date",
            "driver_name",
            "vehicle_number",
            "start_location",
            "destination",
            "start_km",
            "end_km",
            "total_km",
            "purpose",
            "created_at",
        )


class TripCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = ("start_location", "destination", "start_km", "end_km", "purpose")

    def validate(self, attrs):
        if attrs["end_km"] < attrs["start_km"]:
            raise serializers.ValidationError("Trip end_km must be >= start_km.")

        attendance = self.context.get("attendance")
        if not attendance:
            raise serializers.ValidationError("No active attendance found.")

        if attendance.date != timezone.localdate():
            raise serializers.ValidationError(
                "Trips can only be created for today's attendance."
            )

        return attrs

    def create(self, validated_data):
        attendance = self.context["attendance"]
        return Trip.objects.create(attendance=attendance, **validated_data)


def get_today_attendance_for_driver(driver):
    return (
        Attendance.objects.filter(driver=driver, date=timezone.localdate())
        .order_by("-started_at")
        .first()
    )
