import calendar
from datetime import date, datetime, timedelta

from django.utils import timezone
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import (
    Attendance,
    AttendanceLocationPoint,
    DriverDailyAttendanceMark,
    TransportService,
)
from attendance.serializers import (
    AttendanceEndSerializer,
    AttendanceLocationPointSerializer,
    AttendanceLocationTrackSerializer,
    DriverAttendanceMarkRequestSerializer,
    AttendanceSerializer,
    AttendanceStartSerializer,
    TransportServiceCreateSerializer,
    TransportServiceSerializer,
)
from drivers.models import Driver
from trips.models import Trip
from trips.serializers import get_or_create_master_trip
from users.notification_utils import (
    create_trip_closed_notification,
    create_trip_started_notification,
)
from users.permissions import IsDriverRole, IsTransporterRole

DEFAULT_SERVICE_NAMES = [
    "DTM Vehicle",
    "Generator Vehicle",
    "Maintenance Vehicle",
    "Diesel Filling Vehicle",
]


def _resolve_effective_end_km(attendance: Attendance) -> int:
    candidates = [attendance.start_km]
    if attendance.end_km is not None:
        candidates.append(attendance.end_km)
    for trip in getattr(attendance, "_prefetched_closed_child_trips", []):
        if trip.end_km is not None:
            candidates.append(trip.end_km)
    return max(candidates)


def _aggregate_attendances_by_driver_date(attendances):
    grouped = {}
    for attendance in attendances:
        key = (attendance.driver_id, attendance.date)
        summary = grouped.get(key)
        effective_end_km = _resolve_effective_end_km(attendance)
        vehicle_number = attendance.vehicle.vehicle_number
        service_name = (attendance.service_name or "").strip()
        service_purpose = (attendance.service_purpose or "").strip()

        if summary is None:
            grouped[key] = {
                "attendance": attendance,
                "has_open_run": attendance.ended_at is None,
                "vehicle_numbers": {vehicle_number} if vehicle_number else set(),
                "service_names": {service_name} if service_name else set(),
                "service_purposes": {service_purpose} if service_purpose else set(),
                "start_km": attendance.start_km,
                "end_km": effective_end_km,
                "started_at": attendance.started_at,
                "ended_at": attendance.ended_at,
                "attendance_count": 1,
            }
            continue

        summary["has_open_run"] = summary["has_open_run"] or attendance.ended_at is None
        if vehicle_number:
            summary["vehicle_numbers"].add(vehicle_number)
        if service_name:
            summary["service_names"].add(service_name)
        if service_purpose:
            summary["service_purposes"].add(service_purpose)
        summary["start_km"] = min(summary["start_km"], attendance.start_km)
        summary["end_km"] = max(summary["end_km"], effective_end_km)
        if attendance.started_at and (
            summary["started_at"] is None or attendance.started_at < summary["started_at"]
        ):
            summary["started_at"] = attendance.started_at
        if attendance.ended_at and (
            summary["ended_at"] is None or attendance.ended_at > summary["ended_at"]
        ):
            summary["ended_at"] = attendance.ended_at
        summary["attendance_count"] += 1
        if summary["has_open_run"]:
            summary["ended_at"] = None

    return grouped


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


def resolve_attendance_view_status(*, attendance, mark, target_date, today, joined_date=None):
    if joined_date is not None and target_date < joined_date:
        return "NOT_JOINED"

    if attendance is not None:
        if attendance.status == Attendance.Status.LEAVE:
            return "LEAVE"
        return "PRESENT"

    if mark is not None:
        if mark.status == DriverDailyAttendanceMark.Status.ABSENT:
            return "ABSENT"
        if mark.status == DriverDailyAttendanceMark.Status.LEAVE:
            return "LEAVE"
        return "NO_DUTY"

    if target_date > today:
        return "FUTURE"
    return "NO_DUTY"


class AttendanceStartView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        serializer = AttendanceStartSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()
        master_trip = get_or_create_master_trip(attendance)
        create_trip_started_notification(master_trip)
        response_serializer = AttendanceSerializer(attendance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TransportServiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        services = self._scoped_queryset(request)

        include_inactive = (
            request.query_params.get("include_inactive", "").strip().lower() in {"1", "true", "yes"}
        )
        if not include_inactive:
            services = services.filter(is_active=True)

        serializer = TransportServiceSerializer(services.order_by("name"), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if request.user.role != "TRANSPORTER" or not hasattr(request.user, "transporter_profile"):
            return Response(
                {"detail": "Only transporter can add service types."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TransportServiceCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(
            TransportServiceSerializer(service).data,
            status=status.HTTP_201_CREATED,
        )

    def _scoped_queryset(self, request):
        user = request.user
        if user.role == "TRANSPORTER" and hasattr(user, "transporter_profile"):
            ensure_default_services_for_transporter(user.transporter_profile)
            return TransportService.objects.filter(transporter=user.transporter_profile)
        if (
            user.role == "DRIVER"
            and hasattr(user, "driver_profile")
            and user.driver_profile.transporter_id is not None
        ):
            transporter = user.driver_profile.transporter
            if transporter is not None:
                ensure_default_services_for_transporter(transporter)
            return TransportService.objects.filter(
                transporter_id=user.driver_profile.transporter_id
            )
        return TransportService.objects.none()


class TransportServiceDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def patch(self, request, service_id: int):
        service = (
            TransportService.objects.filter(
                id=service_id,
                transporter=request.user.transporter_profile,
            )
            .order_by("id")
            .first()
        )
        if service is None:
            return Response(
                {"detail": "Service not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TransportServiceCreateSerializer(
            instance=service,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        return Response(
            TransportServiceSerializer(service).data,
            status=status.HTTP_200_OK,
        )


class AttendanceEndView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        if not hasattr(request.user, "driver_profile"):
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        attendance = (
            Attendance.objects.filter(
                driver=request.user.driver_profile,
                date__in=[today, yesterday],
                ended_at__isnull=True,
                vehicle__transporter_id=request.user.driver_profile.transporter_id,
            )
            .order_by("-date", "-started_at")
            .first()
        )

        if not attendance:
            return Response(
                {"detail": "No active attendance found to close."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AttendanceEndSerializer(instance=attendance, data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()
        master_trip = get_or_create_master_trip(attendance)
        create_trip_closed_notification(master_trip)

        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_200_OK)


class AttendanceLocationTrackView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        serializer = AttendanceLocationTrackSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        point = serializer.save()
        return Response(
            {
                "detail": "Location point recorded.",
                "point": AttendanceLocationPointSerializer(point).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TransporterDriverLocationsView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        target_date = request.query_params.get("date")
        if target_date:
            try:
                target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        driver_id = (request.query_params.get("driver_id") or "").strip()
        attendance_id = (request.query_params.get("attendance_id") or "").strip()
        open_only_value = (request.query_params.get("open_only") or "").strip().lower()
        open_only = open_only_value in {"1", "true", "yes", "y"}

        transporter = request.user.transporter_profile

        attendances = (
            Attendance.objects.select_related(
                "driver",
                "driver__user",
                "vehicle",
                "vehicle__transporter",
            )
            .prefetch_related(
                Prefetch(
                    "location_points",
                    queryset=AttendanceLocationPoint.objects.order_by("recorded_at", "id"),
                    to_attr="_prefetched_location_points",
                )
            )
            .filter(date=target_date, vehicle__transporter=transporter)
        )

        if open_only:
            attendances = attendances.filter(ended_at__isnull=True)

        if driver_id.isdigit():
            attendances = attendances.filter(driver_id=int(driver_id))

        if attendance_id.isdigit():
            attendances = attendances.filter(id=int(attendance_id))

        map_points: list[dict] = []
        session_rows: list[dict] = []

        for attendance in attendances.order_by("started_at", "id"):
            driver_name = attendance.driver.user.username
            vehicle_number = attendance.vehicle.vehicle_number
            service_name = attendance.service_name or "Unspecified Service"
            transporter_name = attendance.vehicle.transporter.company_name

            started_at_label = (
                timezone.localtime(attendance.started_at).strftime("%I:%M %p")
                if attendance.started_at
                else "-"
            )
            ended_at_label = (
                timezone.localtime(attendance.ended_at).strftime("%I:%M %p")
                if attendance.ended_at
                else "-"
            )

            prefetched_points = list(getattr(attendance, "_prefetched_location_points", []))
            if not prefetched_points:
                prefetched_points = [
                    AttendanceLocationPoint(
                        attendance=attendance,
                        transporter=attendance.vehicle.transporter,
                        driver=attendance.driver,
                        vehicle=attendance.vehicle,
                        point_type=AttendanceLocationPoint.PointType.START,
                        latitude=attendance.latitude,
                        longitude=attendance.longitude,
                        recorded_at=attendance.started_at,
                    )
                ]
                if attendance.end_latitude is not None and attendance.end_longitude is not None:
                    prefetched_points.append(
                        AttendanceLocationPoint(
                            attendance=attendance,
                            transporter=attendance.vehicle.transporter,
                            driver=attendance.driver,
                            vehicle=attendance.vehicle,
                            point_type=AttendanceLocationPoint.PointType.END,
                            latitude=attendance.end_latitude,
                            longitude=attendance.end_longitude,
                            recorded_at=attendance.ended_at or attendance.started_at,
                        )
                    )

            route_points = []
            for point in prefetched_points:
                point_lat = float(point.latitude)
                point_lon = float(point.longitude)
                route_points.append({"latitude": point_lat, "longitude": point_lon})

                point_recorded_at = timezone.localtime(point.recorded_at) if point.recorded_at else None
                point_time_label = (
                    point_recorded_at.strftime("%I:%M:%S %p") if point_recorded_at else "-"
                )

                map_points.append(
                    {
                        "attendance_id": attendance.id,
                        "driver_id": attendance.driver_id,
                        "driver_name": driver_name,
                        "vehicle_number": vehicle_number,
                        "transporter_name": transporter_name,
                        "service_name": service_name,
                        "purpose": attendance.service_purpose or "-",
                        "point_type": point.point_type.lower(),
                        "point_label": point.get_point_type_display(),
                        "latitude": point_lat,
                        "longitude": point_lon,
                        "recorded_at": point_recorded_at.isoformat() if point_recorded_at else None,
                        "time_label": point_time_label,
                        "status_label": "Open" if attendance.ended_at is None else "Closed",
                        "accuracy_m": float(point.accuracy_m) if point.accuracy_m is not None else None,
                        "speed_kph": float(point.speed_kph) if point.speed_kph is not None else None,
                    }
                )

            last_seen_label = (
                timezone.localtime(prefetched_points[-1].recorded_at).strftime("%I:%M:%S %p")
                if prefetched_points and prefetched_points[-1].recorded_at
                else "-"
            )

            session_rows.append(
                {
                    "attendance_id": attendance.id,
                    "driver_id": attendance.driver_id,
                    "driver_name": driver_name,
                    "vehicle_number": vehicle_number,
                    "service_name": service_name,
                    "purpose": attendance.service_purpose or "-",
                    "status_label": "Open" if attendance.ended_at is None else "Closed",
                    "started_at_label": started_at_label,
                    "ended_at_label": ended_at_label,
                    "start_km": attendance.start_km,
                    "end_km": attendance.end_km,
                    "total_km": attendance.total_km if attendance.end_km is not None else 0,
                    "point_count": len(route_points),
                    "last_seen_label": last_seen_label,
                }
            )

        return Response(
            {
                "date": target_date.isoformat(),
                "generated_at": timezone.localtime(timezone.now()).isoformat(),
                "sessions": session_rows,
                "map_points": map_points,
                "total_sessions": len(session_rows),
                "total_markers": len(map_points),
            },
            status=status.HTTP_200_OK,
        )


class DailyAttendanceOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        target_date = request.query_params.get("date")
        if target_date:
            try:
                target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        transporter = request.user.transporter_profile
        drivers = list(
            Driver.objects.filter(transporter=transporter)
            .select_related("user", "assigned_vehicle")
            .order_by("user__username")
        )
        attendance_summaries = _aggregate_attendances_by_driver_date(
            Attendance.objects.filter(
                driver__in=drivers,
                date=target_date,
                vehicle__transporter=transporter,
            )
            .select_related("vehicle")
            .prefetch_related(
                Prefetch(
                    "trips",
                    queryset=Trip.objects.filter(
                        is_day_trip=False,
                        end_km__isnull=False,
                    ).only("id", "end_km", "attendance_id"),
                    to_attr="_prefetched_closed_child_trips",
                )
            )
        )
        marks = {
            mark.driver_id: mark
            for mark in DriverDailyAttendanceMark.objects.filter(
                driver__in=drivers,
                transporter=transporter,
                date=target_date,
            )
        }

        items = []
        for driver in drivers:
            attendance_summary = attendance_summaries.get((driver.id, target_date))
            attendance = (
                attendance_summary["attendance"]
                if attendance_summary is not None
                else None
            )
            mark = marks.get(driver.id)
            joined_date = driver.joined_transporter_date
            status_value = resolve_attendance_view_status(
                attendance=attendance,
                mark=mark,
                target_date=target_date,
                today=timezone.localdate(),
                joined_date=joined_date,
            )

            items.append(
                {
                    "driver_id": driver.id,
                    "driver_name": driver.user.username,
                    "license_number": driver.license_number,
                    "assigned_vehicle_number": (
                        driver.assigned_vehicle.vehicle_number
                        if driver.assigned_vehicle is not None
                        else None
                    ),
                    "date": target_date,
                    "status": status_value,
                    "mark_status": mark.status if mark is not None else None,
                    "has_mark": mark is not None,
                    "has_attendance": attendance is not None,
                    "attendance_vehicle_number": (
                        ", ".join(sorted(attendance_summary["vehicle_numbers"]))
                        if attendance_summary is not None
                        else None
                    ),
                    "service_id": attendance.service_id if attendance is not None else None,
                    "service_name": (
                        ", ".join(sorted(attendance_summary["service_names"]))
                        if attendance_summary is not None
                        else None
                    ),
                    "service_purpose": (
                        " | ".join(sorted(attendance_summary["service_purposes"]))
                        if attendance_summary is not None
                        else None
                    ),
                    "started_at": (
                        attendance_summary["started_at"]
                        if attendance_summary is not None
                        else None
                    ),
                    "ended_at": (
                        attendance_summary["ended_at"]
                        if attendance_summary is not None
                        else None
                    ),
                    "start_km": (
                        attendance_summary["start_km"]
                        if attendance_summary is not None
                        else None
                    ),
                    "end_km": (
                        attendance_summary["end_km"]
                        if attendance_summary is not None
                        else None
                    ),
                    "can_start_day": (
                        target_date == timezone.localdate()
                        and (joined_date is None or target_date >= joined_date)
                        and (
                            mark is None
                            or mark.status
                            not in {
                                DriverDailyAttendanceMark.Status.ABSENT,
                                DriverDailyAttendanceMark.Status.LEAVE,
                            }
                        )
                        and not (
                            attendance_summary is not None
                            and attendance_summary["has_open_run"]
                        )
                    ),
                }
            )

        return Response(
            {
                "date": target_date,
                "items": items,
            },
            status=status.HTTP_200_OK,
        )


class DailyAttendanceMarkView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        serializer = DriverAttendanceMarkRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        mark = serializer.save()

        return Response(
            {
                "detail": "Attendance mark updated successfully.",
                "driver_id": mark.driver_id,
                "date": mark.date,
                "status": mark.status,
            },
            status=status.HTTP_200_OK,
        )


class DriverAttendanceCalendarView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request, driver_id: int):
        try:
            month = int(request.query_params.get("month", timezone.localdate().month))
            year = int(request.query_params.get("year", timezone.localdate().year))
        except ValueError:
            return Response(
                {"detail": "Month and year must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if month < 1 or month > 12:
            return Response(
                {"detail": "Month must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transporter = request.user.transporter_profile
        driver = (
            Driver.objects.filter(id=driver_id, transporter=transporter)
            .select_related("user")
            .first()
        )
        if driver is None:
            return Response(
                {"detail": "Driver not found for your transporter."},
                status=status.HTTP_404_NOT_FOUND,
            )

        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        today = timezone.localdate()

        attendance_summaries = _aggregate_attendances_by_driver_date(
            Attendance.objects.filter(
                driver=driver,
                date__gte=first_day,
                date__lte=last_day,
                vehicle__transporter=transporter,
            )
            .select_related("vehicle")
            .prefetch_related(
                Prefetch(
                    "trips",
                    queryset=Trip.objects.filter(
                        is_day_trip=False,
                        end_km__isnull=False,
                    ).only("id", "end_km", "attendance_id"),
                    to_attr="_prefetched_closed_child_trips",
                )
            )
        )
        marks = {
            item.date: item
            for item in DriverDailyAttendanceMark.objects.filter(
                driver=driver,
                transporter=transporter,
                date__gte=first_day,
                date__lte=last_day,
            )
        }

        days = []
        present_days = 0
        absent_days = 0
        no_duty_days = 0

        total_days = (last_day - first_day).days + 1
        for offset in range(total_days):
            target_date = date(year, month, 1) + timedelta(days=offset)
            attendance_summary = attendance_summaries.get((driver.id, target_date))
            attendance = (
                attendance_summary["attendance"]
                if attendance_summary is not None
                else None
            )
            mark = marks.get(target_date)
            joined_date = driver.joined_transporter_date
            status_value = resolve_attendance_view_status(
                attendance=attendance,
                mark=mark,
                target_date=target_date,
                today=today,
                joined_date=joined_date,
            )

            if status_value == "PRESENT":
                present_days += 1
            elif status_value in {"ABSENT", "LEAVE"}:
                absent_days += 1
            elif status_value == "NO_DUTY":
                no_duty_days += 1

            days.append(
                {
                    "date": target_date,
                    "status": status_value,
                    "has_attendance": attendance is not None,
                    "has_mark": mark is not None,
                    "vehicle_number": (
                        ", ".join(sorted(attendance_summary["vehicle_numbers"]))
                        if attendance_summary is not None
                        else None
                    ),
                    "service_name": (
                        ", ".join(sorted(attendance_summary["service_names"]))
                        if attendance_summary is not None
                        else None
                    ),
                    "start_km": (
                        attendance_summary["start_km"]
                        if attendance_summary is not None
                        else None
                    ),
                    "end_km": (
                        attendance_summary["end_km"]
                        if attendance_summary is not None
                        else None
                    ),
                }
            )

        return Response(
            {
                "driver_id": driver.id,
                "driver_name": driver.user.username,
                "month": month,
                "year": year,
                "totals": {
                    "present_days": present_days,
                    "absent_days": absent_days,
                    "no_duty_days": no_duty_days,
                    "effective_present_days": present_days + no_duty_days,
                },
                "days": days,
            },
            status=status.HTTP_200_OK,
        )
