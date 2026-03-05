from django.utils import timezone
from rest_framework import serializers

from attendance.models import Attendance
from trips.models import Trip


class TripSerializer(serializers.ModelSerializer):
    attendance_date = serializers.DateField(source="attendance.date", read_only=True)
    driver_name = serializers.CharField(source="attendance.driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="attendance.vehicle.vehicle_number", read_only=True)
    attendance_status = serializers.CharField(source="attendance.status", read_only=True)
    attendance_started_at = serializers.DateTimeField(source="attendance.started_at", read_only=True)
    attendance_ended_at = serializers.DateTimeField(source="attendance.ended_at", read_only=True)
    attendance_start_km = serializers.IntegerField(source="attendance.start_km", read_only=True)
    attendance_end_km = serializers.IntegerField(source="attendance.end_km", read_only=True)
    attendance_latitude = serializers.DecimalField(
        source="attendance.latitude",
        max_digits=9,
        decimal_places=6,
        read_only=True,
    )
    attendance_longitude = serializers.DecimalField(
        source="attendance.longitude",
        max_digits=9,
        decimal_places=6,
        read_only=True,
    )
    opening_odo_image = serializers.SerializerMethodField()
    closing_odo_image = serializers.SerializerMethodField()
    is_live = serializers.SerializerMethodField()
    trip_status = serializers.CharField(source="status", read_only=True)
    parent_trip = serializers.IntegerField(source="parent_trip_id", read_only=True)
    child_count = serializers.SerializerMethodField()
    is_master_trip = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = (
            "id",
            "attendance",
            "attendance_date",
            "attendance_status",
            "attendance_started_at",
            "attendance_ended_at",
            "attendance_start_km",
            "attendance_end_km",
            "attendance_latitude",
            "attendance_longitude",
            "opening_odo_image",
            "closing_odo_image",
            "is_live",
            "trip_status",
            "parent_trip",
            "child_count",
            "is_master_trip",
            "is_day_trip",
            "started_at",
            "ended_at",
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

    def get_opening_odo_image(self, obj):
        if obj.start_odo_image:
            request = self.context.get("request")
            if request is not None:
                return request.build_absolute_uri(obj.start_odo_image.url)
            return obj.start_odo_image.url
        if obj.attendance.odo_start_image:
            request = self.context.get("request")
            if request is not None:
                return request.build_absolute_uri(obj.attendance.odo_start_image.url)
            return obj.attendance.odo_start_image.url
        return None

    def get_closing_odo_image(self, obj):
        if obj.end_odo_image:
            request = self.context.get("request")
            if request is not None:
                return request.build_absolute_uri(obj.end_odo_image.url)
            return obj.end_odo_image.url
        if obj.attendance.odo_end_image:
            request = self.context.get("request")
            if request is not None:
                return request.build_absolute_uri(obj.attendance.odo_end_image.url)
            return obj.attendance.odo_end_image.url
        return None

    def get_is_live(self, obj):
        return obj.status == Trip.Status.OPEN

    def get_child_count(self, obj):
        return obj.child_trips.count()

    def get_is_master_trip(self, obj):
        return obj.is_day_trip and obj.parent_trip_id is None


class TripCreateSerializer(serializers.ModelSerializer):
    start_odo_image = serializers.ImageField()

    class Meta:
        model = Trip
        fields = ("start_location", "destination", "start_km", "purpose", "start_odo_image")

    def validate(self, attrs):
        attendance = self.context.get("attendance")
        if not attendance:
            raise serializers.ValidationError("No active attendance found.")

        if attendance.date != timezone.localdate():
            raise serializers.ValidationError("Trips can only be created for today's attendance.")

        return attrs

    def create(self, validated_data):
        attendance = self.context["attendance"]
        master_trip = get_or_create_master_trip(attendance)
        return Trip.objects.create(
            attendance=attendance,
            parent_trip=master_trip,
            start_location=validated_data["start_location"],
            destination=validated_data["destination"],
            start_km=validated_data["start_km"],
            purpose=validated_data.get("purpose", ""),
            start_odo_image=validated_data["start_odo_image"],
            status=Trip.Status.OPEN,
            is_day_trip=False,
            started_at=timezone.now(),
        )


class TripCloseSerializer(serializers.Serializer):
    end_km = serializers.IntegerField(min_value=0)
    end_odo_image = serializers.ImageField()

    def validate_end_km(self, value):
        trip = self.instance
        if trip and value < trip.start_km:
            raise serializers.ValidationError("End KM must be greater than or equal to start KM.")
        return value

    def update(self, instance, validated_data):
        instance.end_km = validated_data["end_km"]
        instance.end_odo_image = validated_data["end_odo_image"]
        instance.status = Trip.Status.CLOSED
        instance.ended_at = timezone.now()
        instance.save()
        return instance


def get_today_attendance_for_driver(driver):
    return (
        Attendance.objects.filter(driver=driver, date=timezone.localdate())
        .order_by("-started_at")
        .first()
    )


def get_or_create_master_trip(attendance):
    master_trip = (
        attendance.trips.filter(is_day_trip=True, parent_trip__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if master_trip is not None:
        return master_trip

    is_closed = attendance.ended_at is not None
    return Trip.objects.create(
        attendance=attendance,
        parent_trip=None,
        start_location="Day Start",
        destination="Day End",
        start_km=attendance.start_km,
        end_km=attendance.end_km if is_closed else None,
        purpose="Auto-generated master trip for attendance.",
        start_odo_image=attendance.odo_start_image,
        end_odo_image=attendance.odo_end_image if is_closed else None,
        status=Trip.Status.CLOSED if is_closed else Trip.Status.OPEN,
        is_day_trip=True,
        started_at=attendance.started_at,
        ended_at=attendance.ended_at if is_closed else None,
    )
