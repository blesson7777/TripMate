from datetime import timedelta

from django.utils import timezone
from django.db.models import Count
from rest_framework import serializers

from attendance.models import (
    Attendance,
    AttendanceLocationPoint,
    DriverDailyAttendanceMark,
    TransportService,
)
from drivers.models import Driver
from trips.models import Trip
from users.notification_utils import create_attendance_mark_updated_notification
from vehicles.models import Vehicle
from tripmate.odometer_utils import get_latest_vehicle_odometer

DEFAULT_SERVICE_NAMES = [
    "DTM Vehicle",
    "Generator Vehicle",
    "Maintenance Vehicle",
    "Diesel Filling Vehicle",
]
MAX_ODOMETER_SUBMISSION_DELTA_KM = 300


def ensure_default_services_for_transporter(transporter):
    if TransportService.objects.filter(transporter=transporter).exists():
        return
    TransportService.objects.bulk_create(
        [
            TransportService(
                transporter=transporter,
                name=name,
                description="Default service",
                is_active=True,
            )
            for name in DEFAULT_SERVICE_NAMES
        ]
    )


def create_attendance_location_point(
    attendance: Attendance,
    *,
    point_type: str,
    latitude,
    longitude,
    accuracy_m=None,
    speed_kph=None,
    recorded_at=None,
):
    if not attendance.vehicle.transporter.location_tracking_enabled:
        return None
    return AttendanceLocationPoint.objects.create(
        attendance=attendance,
        transporter=attendance.vehicle.transporter,
        driver=attendance.driver,
        vehicle=attendance.vehicle,
        point_type=point_type,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        speed_kph=speed_kph,
        recorded_at=recorded_at or timezone.now(),
    )


class AttendanceSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)
    trips_count = serializers.SerializerMethodField()
    service_id = serializers.IntegerField(read_only=True)

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
            "service_id",
            "service_name",
            "service_purpose",
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
    service_id = serializers.IntegerField(required=False)
    service_purpose = serializers.CharField(required=False, allow_blank=True, max_length=255)
    destination = serializers.CharField(required=False, allow_blank=True, max_length=255)
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
        ensure_default_services_for_transporter(driver.transporter)
        attendance_date = timezone.localdate()
        active_driver_attendance = Attendance.objects.filter(
            driver=driver,
            ended_at__isnull=True,
            vehicle__transporter_id=driver.transporter_id,
        ).order_by("-date", "-started_at").first()
        if active_driver_attendance is not None:
            raise serializers.ValidationError(
                (
                    "Current run is already active. End the current run before "
                    "starting another service."
                )
            )

        if Trip.objects.filter(
            attendance__driver=driver,
            attendance__vehicle__transporter_id=driver.transporter_id,
            status=Trip.Status.OPEN,
        ).exists():
            raise serializers.ValidationError(
                "An open trip exists. Close it before starting another run."
            )

        daily_mark = DriverDailyAttendanceMark.objects.filter(
            driver=driver,
            transporter_id=driver.transporter_id,
            date=attendance_date,
        ).first()
        if daily_mark and daily_mark.status in {
            DriverDailyAttendanceMark.Status.ABSENT,
            DriverDailyAttendanceMark.Status.LEAVE,
        }:
            raise serializers.ValidationError(
                "Transporter marked you absent/leave for today. You cannot start day."
            )

        vehicle_id = attrs.get("vehicle_id")
        if vehicle_id is not None:
            vehicle = Vehicle.objects.filter(id=vehicle_id).first()
            if not vehicle:
                raise serializers.ValidationError("Vehicle does not exist.")
        else:
            vehicle = self._resolve_default_vehicle(driver, attendance_date)
            if vehicle is None:
                raise serializers.ValidationError(
                    "No eligible vehicle found for your transporter."
                )

        if vehicle.transporter_id != driver.transporter_id:
            raise serializers.ValidationError(
                "Selected vehicle is not managed by the driver's transporter."
            )

        active_vehicle_attendance = (
            Attendance.objects.select_related("driver__user")
            .filter(
                vehicle=vehicle,
                ended_at__isnull=True,
                vehicle__transporter_id=driver.transporter_id,
            )
            .order_by("-date", "-started_at")
            .first()
        )
        if active_vehicle_attendance is not None:
            if active_vehicle_attendance.driver_id == driver.id:
                raise serializers.ValidationError(
                    "This vehicle already has your active run. End it before starting again."
                )
            raise serializers.ValidationError(
                (
                    f"Vehicle {vehicle.vehicle_number} is already in an active run "
                    f"under {active_vehicle_attendance.driver.user.username}. "
                    "Close that run before reusing the vehicle."
                )
            )

        latest_odometer = get_latest_vehicle_odometer(vehicle)
        start_km = attrs.get("start_km")
        if (
            latest_odometer is not None
            and start_km is not None
            and start_km < latest_odometer
        ):
            raise serializers.ValidationError(
                {
                    "start_km": (
                        f"Start KM cannot be less than the latest recorded odometer "
                        f"for this vehicle ({latest_odometer})."
                    )
                }
            )
        if (
            latest_odometer is not None
            and start_km is not None
            and start_km > latest_odometer + MAX_ODOMETER_SUBMISSION_DELTA_KM
        ):
            raise serializers.ValidationError(
                {
                    "start_km": (
                        "Start KM cannot be greater than the latest recorded odometer "
                        f"by more than {MAX_ODOMETER_SUBMISSION_DELTA_KM} km "
                        f"for this vehicle ({latest_odometer})."
                    )
                }
            )

        service_id = attrs.get("service_id")
        if service_id is not None:
            service = (
                TransportService.objects.filter(
                    id=service_id,
                    transporter_id=driver.transporter_id,
                    is_active=True,
                )
                .only("id", "name")
                .first()
            )
        else:
            service = self._resolve_default_service(driver)
        if service is None:
            raise serializers.ValidationError(
                {
                    "service_id": (
                        "No active default service found. Select a service or add services."
                    )
                }
            )

        attrs["driver"] = driver
        attrs["vehicle"] = vehicle
        attrs["service"] = service
        attrs["date"] = attendance_date
        attrs["daily_mark"] = daily_mark
        attrs["latest_odometer"] = latest_odometer
        return attrs

    def _resolve_default_vehicle(self, driver, attendance_date):
        if (
            driver.assigned_vehicle_id is not None
            and driver.assigned_vehicle is not None
            and driver.assigned_vehicle.transporter_id == driver.transporter_id
        ):
            return driver.assigned_vehicle

        latest_attendance = (
            Attendance.objects.filter(
                driver=driver,
                vehicle__transporter_id=driver.transporter_id,
            )
            .select_related("vehicle")
            .order_by("-date", "-started_at")
            .first()
        )
        if latest_attendance is not None:
            return latest_attendance.vehicle

        candidate = (
            Vehicle.objects.filter(
                transporter_id=driver.transporter_id,
                status=Vehicle.Status.ACTIVE,
            )
            .order_by("vehicle_number")
            .first()
            or Vehicle.objects.filter(
                transporter_id=driver.transporter_id,
            )
            .order_by("vehicle_number")
            .first()
        )
        if candidate is not None:
            return candidate

        return (
            Vehicle.objects.filter(
                transporter_id=driver.transporter_id,
                status=Vehicle.Status.ACTIVE,
            )
            .order_by("vehicle_number")
            .first()
            or Vehicle.objects.filter(transporter_id=driver.transporter_id)
            .order_by("vehicle_number")
            .first()
        )

    def _resolve_default_service(self, driver):
        if (
            driver.default_service_id is not None
            and driver.default_service is not None
            and driver.default_service.transporter_id == driver.transporter_id
            and driver.default_service.is_active
        ):
            return driver.default_service

        latest_attendance = (
            Attendance.objects.filter(
                driver=driver,
                service__transporter_id=driver.transporter_id,
                service__is_active=True,
            )
            .select_related("service")
            .order_by("-date", "-started_at")
            .first()
        )
        if latest_attendance is not None and latest_attendance.service is not None:
            return latest_attendance.service

        frequent = (
            Attendance.objects.filter(
                driver=driver,
                service__transporter_id=driver.transporter_id,
                service__is_active=True,
            )
            .values("service_id")
            .annotate(total=Count("id"))
            .order_by("-total", "-service_id")
            .first()
        )
        if frequent is not None and frequent.get("service_id") is not None:
            service = (
                TransportService.objects.filter(
                    id=frequent["service_id"],
                    transporter_id=driver.transporter_id,
                    is_active=True,
                )
                .only("id", "name")
                .first()
            )
            if service is not None:
                return service

        return (
            TransportService.objects.filter(
                transporter_id=driver.transporter_id,
                is_active=True,
            )
            .order_by("name")
            .first()
        )

    def create(self, validated_data):
        driver = validated_data["driver"]
        vehicle = validated_data["vehicle"]
        service = validated_data["service"]
        attendance = Attendance.objects.create(
            driver=driver,
            vehicle=vehicle,
            date=validated_data["date"],
            service=service,
            service_name=service.name,
            service_purpose=validated_data.get("service_purpose", "").strip(),
            start_km=validated_data["start_km"],
            odo_start_image=validated_data["odo_start_image"],
            latitude=validated_data["latitude"],
            longitude=validated_data["longitude"],
            status=Attendance.Status.ON_DUTY,
        )
        create_attendance_location_point(
            attendance,
            point_type=AttendanceLocationPoint.PointType.START,
            latitude=attendance.latitude,
            longitude=attendance.longitude,
            recorded_at=attendance.started_at,
        )

        daily_mark = validated_data.get("daily_mark")
        if daily_mark is None:
            DriverDailyAttendanceMark.objects.create(
                driver=driver,
                transporter=driver.transporter,
                date=validated_data["date"],
                status=DriverDailyAttendanceMark.Status.PRESENT,
                marked_by=None,
            )
        elif daily_mark.status != DriverDailyAttendanceMark.Status.PRESENT:
            daily_mark.status = DriverDailyAttendanceMark.Status.PRESENT
            daily_mark.marked_by = None
            daily_mark.save(update_fields=["status", "marked_by", "marked_at"])

        service_purpose = attendance.service_purpose.strip()
        master_purpose = (
            service_purpose
            if service_purpose
            else f"Service duty: {attendance.service_name}."
        )

        Trip.objects.create(
            attendance=attendance,
            parent_trip=None,
            start_location="Day Start",
            destination=validated_data.get("destination", "").strip() or "Day End",
            start_km=attendance.start_km,
            purpose=master_purpose,
            start_odo_image=attendance.odo_start_image,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            started_at=attendance.started_at,
        )

        return attendance


class TransportServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportService
        fields = ("id", "name", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class TransportServiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportService
        fields = ("name", "description", "is_active")

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Service name is required.")
        return name

    def create(self, validated_data):
        transporter = self.context["request"].user.transporter_profile
        return TransportService.objects.create(
            transporter=transporter,
            name=validated_data["name"].strip(),
            description=validated_data.get("description", "").strip(),
            is_active=validated_data.get("is_active", True),
        )


class AttendanceEndSerializer(serializers.Serializer):
    end_km = serializers.IntegerField(min_value=0)
    confirm_large_run = serializers.BooleanField(required=False, default=False)
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
        attendance = self.instance
        if attendance is not None and attendance.trips.filter(
            is_day_trip=False,
            status=Trip.Status.OPEN,
        ).exists():
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Close all pending trips before ending the day."
                    )
                }
            )

        end_km = attrs.get("end_km")
        if attendance is not None and end_km is not None:
            run_km = end_km - attendance.start_km
            if run_km > 400:
                raise serializers.ValidationError(
                    {
                        "detail": (
                            f"Closing KM implies a run of {run_km} km today. "
                            "Runs above 400 km are not allowed. Please verify the odometer reading."
                        )
                    }
                )
            if run_km > 300 and not attrs.get("confirm_large_run", False):
                raise serializers.ValidationError(
                    {
                        "detail": (
                            f"Closing KM implies a run of {run_km} km today. "
                            "If this is correct, submit again with confirm_large_run=true."
                        )
                    }
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
        # Starting and closing a day means the driver has performed duty.
        # Keep status as ON_DUTY regardless of whether child trips exist.
        instance.status = Attendance.Status.ON_DUTY

        instance.save()
        if instance.end_latitude is not None and instance.end_longitude is not None:
            create_attendance_location_point(
                instance,
                point_type=AttendanceLocationPoint.PointType.END,
                latitude=instance.end_latitude,
                longitude=instance.end_longitude,
                recorded_at=instance.ended_at,
            )
        return instance


class AttendanceLocationPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceLocationPoint
        fields = (
            "id",
            "attendance",
            "driver",
            "vehicle",
            "point_type",
            "latitude",
            "longitude",
            "accuracy_m",
            "speed_kph",
            "recorded_at",
        )
        read_only_fields = ("id", "attendance", "driver", "vehicle", "point_type")


class AttendanceLocationTrackSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    speed_kph = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    recorded_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        request = self.context["request"]
        if not hasattr(request.user, "driver_profile"):
            raise serializers.ValidationError("Driver profile does not exist.")

        driver = request.user.driver_profile
        if driver.transporter_id is None:
            raise serializers.ValidationError("Driver is not allocated to a transporter.")
        transporter = driver.transporter
        if transporter is None or not transporter.location_tracking_enabled:
            raise serializers.ValidationError(
                {"detail": "Location monitoring is disabled for your transporter."}
            )

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        attendance = (
            Attendance.objects.filter(
                driver=driver,
                date__in=[today, yesterday],
                ended_at__isnull=True,
                vehicle__transporter_id=driver.transporter_id,
            )
            .select_related("vehicle", "vehicle__transporter")
            .order_by("-date", "-started_at")
            .first()
        )
        if attendance is None:
            raise serializers.ValidationError(
                {"detail": "No active run found for location tracking."}
            )

        recorded_at = attrs.get("recorded_at")
        now = timezone.now()
        if recorded_at is not None and recorded_at > now + timedelta(minutes=5):
            attrs["recorded_at"] = now
        attrs["attendance"] = attendance
        return attrs

    def create(self, validated_data):
        attendance = validated_data["attendance"]
        return create_attendance_location_point(
            attendance,
            point_type=AttendanceLocationPoint.PointType.TRACK,
            latitude=validated_data["latitude"],
            longitude=validated_data["longitude"],
            accuracy_m=validated_data.get("accuracy_m"),
            speed_kph=validated_data.get("speed_kph"),
            recorded_at=validated_data.get("recorded_at"),
        )


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

        if attrs["status"] in {
            DriverDailyAttendanceMark.Status.ABSENT,
            DriverDailyAttendanceMark.Status.LEAVE,
        } and Attendance.objects.filter(driver=driver, date=target_date).exists():
            raise serializers.ValidationError(
                {
                    "status": (
                        "Cannot mark absent/leave after driver has already started attendance."
                    )
                }
            )

        attrs["driver"] = driver
        attrs["transporter"] = transporter
        attrs["date"] = target_date
        return attrs

    def save(self):
        request = self.context["request"]
        driver = self.validated_data["driver"]
        target_date = self.validated_data["date"]
        status = self.validated_data["status"]

        existing_mark = DriverDailyAttendanceMark.objects.filter(
            driver=driver,
            transporter=self.validated_data["transporter"],
            date=target_date,
        ).first()
        previous_status = existing_mark.status if existing_mark is not None else None

        mark, _ = DriverDailyAttendanceMark.objects.update_or_create(
            driver=driver,
            transporter=self.validated_data["transporter"],
            date=target_date,
            defaults={
                "status": status,
                "marked_by": request.user,
            },
        )
        if previous_status != mark.status:
            create_attendance_mark_updated_notification(
                mark=mark,
                previous_status=previous_status,
            )
        return mark
