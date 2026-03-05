from django.utils import timezone
from rest_framework import serializers

from attendance.models import Attendance, DriverDailyAttendanceMark
from drivers.models import Driver
from trips.models import Trip
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
            "end_latitude",
            "end_longitude",
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
        if driver.transporter_id is None:
            raise serializers.ValidationError(
                "Driver is not allocated to any transporter yet."
            )
        attendance_date = timezone.localdate()
        if Attendance.objects.filter(driver=driver, date=attendance_date).exists():
            raise serializers.ValidationError("Attendance already marked for today.")

        daily_mark = DriverDailyAttendanceMark.objects.filter(
            driver=driver,
            date=attendance_date,
        ).first()
        if daily_mark and daily_mark.status == DriverDailyAttendanceMark.Status.ABSENT:
            raise serializers.ValidationError(
                "Transporter marked you absent for today. You cannot start day."
            )

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
        attrs["daily_mark"] = daily_mark
        return attrs

    def create(self, validated_data):
        driver = validated_data["driver"]
        vehicle = validated_data["vehicle"]
        attendance = Attendance.objects.create(
            driver=driver,
            vehicle=vehicle,
            date=validated_data["date"],
            start_km=validated_data["start_km"],
            odo_start_image=validated_data["odo_start_image"],
            latitude=validated_data["latitude"],
            longitude=validated_data["longitude"],
            status=Attendance.Status.ON_DUTY,
        )

        daily_mark = validated_data.get("daily_mark")
        if daily_mark is None:
            DriverDailyAttendanceMark.objects.create(
                driver=driver,
                date=validated_data["date"],
                status=DriverDailyAttendanceMark.Status.PRESENT,
                marked_by=None,
            )
        elif daily_mark.status != DriverDailyAttendanceMark.Status.PRESENT:
            daily_mark.status = DriverDailyAttendanceMark.Status.PRESENT
            daily_mark.marked_by = None
            daily_mark.save(update_fields=["status", "marked_by", "marked_at"])

        Trip.objects.create(
            attendance=attendance,
            parent_trip=None,
            start_location="Day Start",
            destination="Day End",
            start_km=attendance.start_km,
            purpose="Auto-started with start day.",
            start_odo_image=attendance.odo_start_image,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            started_at=attendance.started_at,
        )

        return attendance


class AttendanceEndSerializer(serializers.Serializer):
    end_km = serializers.IntegerField(min_value=0)
    odo_end_image = serializers.ImageField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)

    def validate(self, attrs):
        has_latitude = "latitude" in attrs
        has_longitude = "longitude" in attrs
        if has_latitude != has_longitude:
            raise serializers.ValidationError(
                "Both latitude and longitude are required together."
            )
        return attrs

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
        if "latitude" in validated_data:
            instance.end_latitude = validated_data["latitude"]
            instance.end_longitude = validated_data["longitude"]
        instance.ended_at = timezone.now()

        master_trip = (
            instance.trips.filter(
                status=Trip.Status.OPEN,
                is_day_trip=True,
                parent_trip__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )
        if master_trip is not None:
            if instance.end_km < master_trip.start_km:
                raise serializers.ValidationError(
                    {
                        "end_km": (
                            "End KM must be greater than or equal to the master trip start KM."
                        )
                    }
                )
            master_trip.end_km = instance.end_km
            master_trip.end_odo_image = instance.odo_end_image
            master_trip.status = Trip.Status.CLOSED
            master_trip.ended_at = instance.ended_at
            master_trip.save()
        elif not instance.trips.exists():
            instance.status = Attendance.Status.NO_TRIP

        instance.save()
        return instance


class DriverDailyAttendanceMarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverDailyAttendanceMark
        fields = ("id", "driver", "date", "status", "marked_by", "marked_at")
        read_only_fields = ("id", "marked_by", "marked_at")


class DriverAttendanceMarkRequestSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=DriverDailyAttendanceMark.Status.choices)
    date = serializers.DateField(required=False)

    def validate(self, attrs):
        request = self.context["request"]
        transporter = request.user.transporter_profile
        target_date = attrs.get("date") or timezone.localdate()

        try:
            driver = Driver.objects.select_related("user").get(pk=attrs["driver_id"])
        except Driver.DoesNotExist as exception:
            raise serializers.ValidationError({"driver_id": "Driver does not exist."}) from exception

        if driver.transporter_id != transporter.id:
            raise serializers.ValidationError(
                {"driver_id": "You can only mark attendance for your own drivers."}
            )

        if (
            attrs["status"] == DriverDailyAttendanceMark.Status.ABSENT
            and Attendance.objects.filter(driver=driver, date=target_date).exists()
        ):
            raise serializers.ValidationError(
                {
                    "status": "Cannot mark absent after driver has already started attendance."
                }
            )

        attrs["driver"] = driver
        attrs["date"] = target_date
        return attrs

    def save(self):
        request = self.context["request"]
        driver = self.validated_data["driver"]
        target_date = self.validated_data["date"]
        status = self.validated_data["status"]

        mark, _ = DriverDailyAttendanceMark.objects.update_or_create(
            driver=driver,
            date=target_date,
            defaults={
                "status": status,
                "marked_by": request.user,
            },
        )
        return mark
