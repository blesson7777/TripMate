from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import math

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Max, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from diesel.models import (
    DieselDailyRoutePlan,
    DieselDailyRoutePlanStop,
    DieselRouteStartPoint,
    IndusTowerSite,
)
from diesel.route_planner import (
    format_route_legs,
    normalize_coordinate_input,
    optimize_route_order,
    validate_lat_lon,
)
from diesel.site_utils import validate_indus_site_id
from diesel.serializers import (
    TowerDieselRecordCreateSerializer,
    TowerDieselRecordSerializer,
)
from fuel.models import FuelRecord
from services.route_optimizer import (
    MAX_TOWERS_PER_REQUEST,
    RouteOptimizerError,
    optimize_route_path,
)
from trips.serializers import get_today_attendance_for_driver
from users.permissions import IsDriverRole
from vehicles.models import Vehicle

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

User = get_user_model()


def _diesel_module_disabled_response():
    return Response(
        {
            "status": "error",
            "message": "Diesel module disabled for your transporter",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _is_diesel_module_enabled_for_user(user):
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TRANSPORTER:
        transporter = getattr(user, "transporter_profile", None)
        return bool(transporter and transporter.diesel_tracking_enabled)
    if user.role == User.Role.DRIVER:
        driver = getattr(user, "driver_profile", None)
        transporter = getattr(driver, "transporter", None) if driver else None
        return bool(transporter and transporter.diesel_tracking_enabled)
    return False


def _is_diesel_readings_enabled_for_user(user):
    if user.role == User.Role.ADMIN:
        return True
    if user.role == User.Role.TRANSPORTER:
        transporter = getattr(user, "transporter_profile", None)
        return bool(
            transporter
            and transporter.diesel_tracking_enabled
            and transporter.diesel_readings_enabled
        )
    if user.role == User.Role.DRIVER:
        driver = getattr(user, "driver_profile", None)
        transporter = getattr(driver, "transporter", None) if driver else None
        return bool(
            transporter
            and transporter.diesel_tracking_enabled
            and transporter.diesel_readings_enabled
        )
    return False


def _contains_diesel_keyword(value):
    normalized = (value or "").strip().lower()
    return "diesel" in normalized


def _attendance_allows_tower_diesel(attendance):
    if attendance is None:
        return False
    if attendance.vehicle.vehicle_type == Vehicle.Type.DIESEL_SERVICE:
        return True
    if _contains_diesel_keyword(attendance.service_name):
        return True
    service = getattr(attendance, "service", None)
    if service is not None and _contains_diesel_keyword(service.name):
        return True
    return False


def _diesel_queryset_for_user(user):
    queryset = FuelRecord.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "attendance",
        "partner",
        "tower_site",
    ).filter(entry_type=FuelRecord.EntryType.TOWER_DIESEL)
    if user.role == User.Role.ADMIN:
        return queryset
    if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
        return queryset.filter(vehicle__transporter=user.transporter_profile)
    if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
        if user.driver_profile.transporter_id is None:
            return FuelRecord.objects.none()
        return queryset.filter(
            driver=user.driver_profile,
            vehicle__transporter_id=user.driver_profile.transporter_id,
        )
    return FuelRecord.objects.none()


def _parse_date_range(request):
    today = timezone.localdate()
    date_from_raw = request.query_params.get("date_from")
    date_to_raw = request.query_params.get("date_to")

    if date_from_raw or date_to_raw:
        try:
            date_from = date.fromisoformat(date_from_raw) if date_from_raw else today
            date_to = date.fromisoformat(date_to_raw) if date_to_raw else today
        except ValueError:
            return None, None, Response(
                {"detail": "date_from/date_to must be in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        return date_from, date_to, None

    try:
        month = int(request.query_params.get("month", today.month))
        year = int(request.query_params.get("year", today.year))
    except ValueError:
        return None, None, Response(
            {"detail": "Month and year must be numeric values."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if month < 1 or month > 12:
        return None, None, Response(
            {"detail": "Month must be between 1 and 12."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    date_from = date(year, month, 1)
    if month == 12:
        date_to = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        date_to = date(year, month + 1, 1) - timedelta(days=1)
    return date_from, date_to, None


class TowerDieselAddView(APIView):
    permission_classes = [IsAuthenticated, IsDriverRole]

    def post(self, request):
        if not hasattr(request.user, "driver_profile"):
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _is_diesel_module_enabled_for_user(request.user):
            return _diesel_module_disabled_response()

        attendance = get_today_attendance_for_driver(request.user.driver_profile)
        if not attendance:
            return Response(
                {"detail": "Attendance must be started before adding tower diesel log."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if attendance.ended_at is not None:
            return Response(
                {
                    "detail": (
                        "Tower diesel filling is available only during an active day. "
                        "Start day with Diesel Filling Vehicle."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _attendance_allows_tower_diesel(attendance):
            return Response(
                {
                    "detail": (
                        "Tower diesel filling can be used only when the active day "
                        "is started with Diesel Filling Vehicle service."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TowerDieselRecordCreateSerializer(
            data=request.data,
            context={"attendance": attendance, "driver": request.user.driver_profile},
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        return Response(
            TowerDieselRecordSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TowerDieselListView(generics.ListAPIView):
    serializer_class = TowerDieselRecordSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = _diesel_queryset_for_user(self.request.user)
        search_query = (self.request.query_params.get("q") or "").strip()

        vehicle_id = self.request.query_params.get("vehicle_id")
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        fill_date = self.request.query_params.get("fill_date")
        if fill_date:
            try:
                parsed = date.fromisoformat(fill_date)
            except ValueError:
                return FuelRecord.objects.none()
            queryset = queryset.filter(fill_date=parsed)

        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")
        if month and year:
            try:
                queryset = queryset.filter(fill_date__month=int(month), fill_date__year=int(year))
            except ValueError:
                return FuelRecord.objects.none()

        if search_query:
            queryset = queryset.filter(
                Q(tower_site__indus_site_id__icontains=search_query)
                | Q(indus_site_id__icontains=search_query)
                | Q(tower_site__site_name__icontains=search_query)
                | Q(site_name__icontains=search_query)
            )

        if self.request.user.role == User.Role.DRIVER:
            queryset = queryset.filter(fill_date=timezone.localdate())

        return queryset.order_by("-fill_date", "-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class TowerDieselDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, record_id):
        if request.user.role not in {
            User.Role.ADMIN,
            User.Role.TRANSPORTER,
            User.Role.DRIVER,
        }:
            return Response(
                {"detail": "Only admin, transporter or driver can delete tower diesel entries."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()
        record = _diesel_queryset_for_user(request.user).filter(id=record_id).first()
        if record is None:
            return Response(
                {"detail": "Tower diesel record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        record.delete()
        return Response(
            {"detail": "Tower diesel record deleted successfully."},
            status=status.HTTP_200_OK,
        )


class TowerDieselLogbookPhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, record_id):
        record = _diesel_queryset_for_user(request.user).filter(id=record_id).first()
        if record is None:
            return Response(
                {"detail": "Tower diesel record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not record.logbook_photo:
            return Response(
                {"detail": "Logbook photo not available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return FileResponse(record.logbook_photo.open("rb"), content_type="image/jpeg")


def _haversine_distance_meters(lat1, lon1, lat2, lon2):
    earth_radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def _tower_site_queryset_for_user(
    user,
    partner_id=None,
    require_site_name=True,
    require_coordinates=True,
):
    queryset = IndusTowerSite.objects.exclude(indus_site_id="")
    if require_coordinates:
        queryset = queryset.exclude(
            latitude__isnull=True
        ).exclude(
            longitude__isnull=True
        )
    if require_site_name:
        queryset = queryset.exclude(site_name="")

    if user.role == User.Role.ADMIN:
        if partner_id is not None:
            return queryset.filter(partner_id=partner_id)
        return queryset
    if user.role == User.Role.TRANSPORTER and hasattr(user, "transporter_profile"):
        return queryset.filter(partner=user.transporter_profile)
    if user.role == User.Role.DRIVER and hasattr(user, "driver_profile"):
        return queryset.filter(partner=user.driver_profile.transporter)
    return IndusTowerSite.objects.none()


class TowerDieselNearbySitesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER, User.Role.DRIVER}:
            return Response(
                {"detail": "Only admin, transporter or driver can access nearby sites."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()

        try:
            latitude = float(request.query_params.get("latitude"))
            longitude = float(request.query_params.get("longitude"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "latitude and longitude are required numeric values."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if latitude < -90 or latitude > 90:
            return Response(
                {"detail": "latitude must be between -90 and 90."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if longitude < -180 or longitude > 180:
            return Response(
                {"detail": "longitude must be between -180 and 180."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            radius_m = float(request.query_params.get("radius_m", 100))
        except ValueError:
            radius_m = 100
        radius_m = min(max(radius_m, 10), 1000)

        partner_id = request.query_params.get("partner_id")
        if request.user.role == User.Role.ADMIN and partner_id is not None:
            try:
                partner_id = int(partner_id)
            except ValueError:
                return Response(
                    {"detail": "partner_id must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif request.user.role != User.Role.ADMIN:
            partner_id = None

        site_queryset = _tower_site_queryset_for_user(
            request.user,
            partner_id=partner_id,
        )
        fill_dates = {
            row["tower_site_id"]: row["last_fill_date"]
            for row in FuelRecord.objects.filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                tower_site_id__in=site_queryset.values_list("id", flat=True),
            )
            .values("tower_site_id")
            .annotate(last_fill_date=Max("fill_date"))
        }
        queryset = site_queryset.values(
            "id",
            "indus_site_id",
            "site_name",
            "latitude",
            "longitude",
        )
        nearest_by_site = {}
        for row in queryset:
            tower_lat = float(row["latitude"])
            tower_lon = float(row["longitude"])
            distance_m = _haversine_distance_meters(latitude, longitude, tower_lat, tower_lon)
            if distance_m > radius_m:
                continue

            key = (
                row["indus_site_id"].strip().upper(),
                row["site_name"].strip().lower(),
            )
            existing = nearest_by_site.get(key)
            if existing is None or distance_m < existing["distance_m"]:
                nearest_by_site[key] = {
                    "indus_site_id": row["indus_site_id"].strip(),
                    "site_name": row["site_name"].strip(),
                    "latitude": tower_lat,
                    "longitude": tower_lon,
                    "distance_m": round(distance_m, 1),
                    "last_fill_date": (
                        fill_dates[row["id"]].isoformat()
                        if fill_dates.get(row["id"]) is not None
                        else None
                    ),
                }

        items = sorted(
            nearest_by_site.values(),
            key=lambda item: (item["distance_m"], item["site_name"].lower()),
        )
        return Response(
            {
                "radius_m": radius_m,
                "count": len(items),
                "items": items,
            },
            status=status.HTTP_200_OK,
        )


class TowerDieselRouteOptimizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER, User.Role.DRIVER}:
            return Response(
                {"detail": "Only admin, transporter or driver can optimize routes."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(request.user):
            return _diesel_module_disabled_response()

        payload = request.data if isinstance(request.data, dict) else {}
        stops_raw = payload.get("stops")
        if not isinstance(stops_raw, list) or not stops_raw:
            return Response(
                {"detail": "stops must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(stops_raw) > 200:
            return Response(
                {"detail": "Too many stops (max 200)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_coordinate = None
        start_raw = payload.get("start")
        if start_raw is not None:
            if not isinstance(start_raw, dict):
                return Response(
                    {"detail": "start must be an object with latitude and longitude."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                start_lat = normalize_coordinate_input(start_raw.get("latitude"))
                start_lon = normalize_coordinate_input(start_raw.get("longitude"))
                validate_lat_lon(start_lat, start_lon)
            except ValueError as exc:
                return Response(
                    {"detail": f"Invalid start coordinates: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            start_coordinate = (start_lat, start_lon)

        return_to_start = bool(payload.get("return_to_start"))

        normalized_stops = []
        coords = []
        for index, stop in enumerate(stops_raw, start=1):
            if not isinstance(stop, dict):
                return Response(
                    {"detail": f"Stop #{index} must be an object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                lat = normalize_coordinate_input(stop.get("latitude"))
                lon = normalize_coordinate_input(stop.get("longitude"))
                validate_lat_lon(lat, lon)
            except ValueError as exc:
                return Response(
                    {"detail": f"Invalid coordinates for stop #{index}: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            normalized_stops.append(
                {
                    "site_id": (stop.get("site_id") or "").strip(),
                    "site_name": (stop.get("site_name") or "").strip(),
                    "qty": stop.get("qty"),
                    "latitude": lat,
                    "longitude": lon,
                }
            )
            coords.append((lat, lon))

        optimization_mode = "local"
        used_fallback = True
        route_order: list[int] = []
        total_km: float = 0.0

        if start_coordinate is not None and len(coords) <= MAX_TOWERS_PER_REQUEST:
            try:
                optimized = optimize_route_path(
                    start=start_coordinate,
                    towers=coords,
                    return_to_start=return_to_start,
                )
                route_order = [
                    index - 1
                    for index in optimized["route"]
                    if index not in {0}
                ]
                total_km = float(optimized["distance"])
                optimization_mode = str(optimized.get("mode") or "road")
                used_fallback = bool(optimized.get("used_fallback"))
            except (RouteOptimizerError, ValueError) as exc:
                optimization_mode = "local"
                used_fallback = True

        if not route_order:
            optimized = optimize_route_order(
                coords,
                start=start_coordinate,
                return_to_start=return_to_start,
                max_swaps=4000 if len(coords) <= 120 else 2500,
            )
            route_order = list(optimized.order)
            total_km = float(optimized.total_km)
            optimization_mode = "local"
            used_fallback = True

        legs = format_route_legs(
            coords,
            route_order,
            start=start_coordinate,
            return_to_start=return_to_start,
        )

        ordered_stops = []
        for leg in legs:
            if leg.get("is_return_leg"):
                ordered_stops.append(
                    {
                        "seq": leg["seq"],
                        "original_idx": None,
                        "site_id": "RETURN",
                        "site_name": "Return",
                        "qty": None,
                        "latitude": leg["latitude"],
                        "longitude": leg["longitude"],
                        "leg_km": leg["leg_km"],
                        "cumulative_km": leg["cumulative_km"],
                        "is_return_leg": True,
                    }
                )
                continue

            original_idx = int(leg["idx"])
            stop = normalized_stops[original_idx]
            ordered_stops.append(
                {
                    "seq": leg["seq"],
                    "original_idx": original_idx,
                    "site_id": stop["site_id"],
                    "site_name": stop["site_name"],
                    "qty": stop["qty"],
                    "latitude": stop["latitude"],
                    "longitude": stop["longitude"],
                    "leg_km": leg["leg_km"],
                    "cumulative_km": leg["cumulative_km"],
                    "is_return_leg": False,
                }
            )

        return Response(
            {
                "start": (
                    {"latitude": start_coordinate[0], "longitude": start_coordinate[1]}
                    if start_coordinate is not None
                    else None
                ),
                "return_to_start": return_to_start,
                "total_km": total_km,
                "mode": optimization_mode,
                "used_fallback": used_fallback,
                "stops": ordered_stops,
            },
            status=status.HTTP_200_OK,
        )


class TowerDieselDailyRoutePlanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER, User.Role.DRIVER}:
            return Response(
                {"detail": "Only admin, transporter or driver can access daily plans."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(request.user):
            return _diesel_module_disabled_response()

        date_raw = (request.query_params.get("date") or "").strip()
        target_date = timezone.localdate()
        if date_raw:
            try:
                target_date = date.fromisoformat(date_raw)
            except ValueError:
                return Response(
                    {"detail": "date must be in YYYY-MM-DD format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        vehicle = None
        vehicle_id_raw = (request.query_params.get("vehicle_id") or "").strip()
        if vehicle_id_raw.isdigit():
            vehicle = Vehicle.objects.select_related("transporter").filter(id=int(vehicle_id_raw)).first()

        if vehicle is None and request.user.role == User.Role.DRIVER and hasattr(request.user, "driver_profile"):
            if target_date == timezone.localdate():
                attendance = get_today_attendance_for_driver(request.user.driver_profile)
                if attendance is not None:
                    vehicle = attendance.vehicle
            if vehicle is None:
                assigned_vehicle = getattr(request.user.driver_profile, "assigned_vehicle", None)
                if assigned_vehicle is not None:
                    vehicle = assigned_vehicle

        if vehicle is None:
            return Response(
                {"detail": "vehicle_id is required (or start day for today)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.role == User.Role.TRANSPORTER and hasattr(request.user, "transporter_profile"):
            if vehicle.transporter_id != request.user.transporter_profile.id:
                return Response(
                    {"detail": "Vehicle does not belong to your transporter."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if request.user.role == User.Role.DRIVER and hasattr(request.user, "driver_profile"):
            if vehicle.transporter_id != request.user.driver_profile.transporter_id:
                return Response(
                    {"detail": "Vehicle does not belong to your transporter."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        plan = (
            DieselDailyRoutePlan.objects.select_related("vehicle", "transporter")
            .prefetch_related("stops", "stops__tower_site")
            .filter(vehicle=vehicle, plan_date=target_date)
            .first()
        )
        if plan is None:
            return Response(
                {"detail": "No daily plan found for this vehicle/date."},
                status=status.HTTP_404_NOT_FOUND,
            )

        start_point = DieselRouteStartPoint.objects.filter(transporter=plan.transporter).first()
        fill_records = list(
            FuelRecord.objects.select_related("tower_site", "driver", "driver__user")
            .filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                vehicle=vehicle,
                fill_date=target_date,
            )
            .order_by("-created_at", "-id")
        )
        fill_by_tower_site_id: dict[int, FuelRecord] = {}
        fill_by_indus_site_id: dict[str, FuelRecord] = {}
        for record in fill_records:
            if record.tower_site_id is not None and record.tower_site_id not in fill_by_tower_site_id:
                fill_by_tower_site_id[record.tower_site_id] = record
            record_site_id = (record.resolved_indus_site_id or "").strip().upper()
            if record_site_id and record_site_id not in fill_by_indus_site_id:
                fill_by_indus_site_id[record_site_id] = record

        stops = []
        total_planned_qty = 0.0
        filled_stops_count = 0
        mapped_coordinates: list[tuple[float, float]] = []
        for stop in plan.stops.all().order_by("sequence", "id"):
            total_planned_qty += float(stop.planned_qty)
            latitude = float(stop.resolved_latitude) if stop.resolved_latitude is not None else None
            longitude = float(stop.resolved_longitude) if stop.resolved_longitude is not None else None
            if latitude is not None and longitude is not None:
                mapped_coordinates.append((latitude, longitude))
            fill_record = None
            if stop.tower_site_id is not None:
                fill_record = fill_by_tower_site_id.get(stop.tower_site_id)
            if fill_record is None:
                stop_site_id = (stop.resolved_indus_site_id or "").strip().upper()
                if stop_site_id:
                    fill_record = fill_by_indus_site_id.get(stop_site_id)
            is_filled = fill_record is not None
            if is_filled:
                filled_stops_count += 1
            stops.append(
                {
                    "sequence": stop.sequence,
                    "indus_site_id": (stop.resolved_indus_site_id or "").strip(),
                    "site_name": (stop.resolved_site_name or "").strip(),
                    "planned_qty": str(stop.planned_qty),
                    "latitude": latitude,
                    "longitude": longitude,
                    "notes": (stop.notes or "").strip(),
                    "is_filled": is_filled,
                    "filled_record_id": fill_record.id if fill_record is not None else None,
                    "filled_qty": (
                        float(fill_record.fuel_filled)
                        if fill_record is not None and fill_record.fuel_filled is not None
                        else None
                    ),
                    "filled_at": (
                        timezone.localtime(fill_record.created_at).isoformat()
                        if fill_record is not None
                        else None
                    ),
                    "filled_by": (
                        fill_record.driver.user.get_full_name().strip() or fill_record.driver.user.username
                        if fill_record is not None and fill_record.driver_id is not None
                        else ""
                    ),
                }
            )

        estimated_distance_km = None
        if mapped_coordinates:
            start_coordinate = None
            if start_point is not None:
                start_coordinate = (float(start_point.latitude), float(start_point.longitude))
            route_legs = format_route_legs(
                mapped_coordinates,
                list(range(len(mapped_coordinates))),
                start=start_coordinate,
                return_to_start=False,
            )
            estimated_distance_km = float(route_legs[-1]["cumulative_km"]) if route_legs else 0.0

        return Response(
            {
                "id": plan.id,
                "plan_date": plan.plan_date.isoformat(),
                "status": plan.status,
                "transporter_id": plan.transporter_id,
                "transporter_name": plan.transporter.company_name,
                "vehicle_id": plan.vehicle_id,
                "vehicle_number": plan.vehicle.vehicle_number,
                "estimated_distance_km": estimated_distance_km,
                "total_planned_qty": round(total_planned_qty, 2),
                "filled_stops_count": filled_stops_count,
                "pending_stops_count": max(len(stops) - filled_stops_count, 0),
                "start_point": (
                    {
                        "name": start_point.name,
                        "latitude": float(start_point.latitude),
                        "longitude": float(start_point.longitude),
                    }
                    if start_point is not None
                    else None
                ),
                "stops": stops,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER}:
            return Response(
                {"detail": "Only admin or transporter can save daily plans."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(request.user):
            return _diesel_module_disabled_response()

        payload = request.data if isinstance(request.data, dict) else {}
        date_raw = (payload.get("date") or "").strip()
        try:
            target_date = date.fromisoformat(date_raw) if date_raw else timezone.localdate()
        except ValueError:
            return Response(
                {"detail": "date must be in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vehicle_id = payload.get("vehicle_id")
        try:
            vehicle_id = int(vehicle_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "vehicle_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vehicle = Vehicle.objects.select_related("transporter").filter(id=vehicle_id).first()
        if vehicle is None:
            return Response(
                {"detail": "Vehicle not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.role == User.Role.TRANSPORTER:
            transporter = getattr(request.user, "transporter_profile", None)
            if transporter is None or vehicle.transporter_id != transporter.id:
                return Response(
                    {"detail": "Vehicle does not belong to your transporter."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            transporter = vehicle.transporter

        stops_raw = payload.get("stops")
        if not isinstance(stops_raw, list):
            return Response(
                {"detail": "stops must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(stops_raw) > 250:
            return Response(
                {"detail": "Too many stops (max 250)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan, _created = DieselDailyRoutePlan.objects.get_or_create(
            vehicle=vehicle,
            plan_date=target_date,
            defaults={
                "transporter": transporter,
                "created_by": request.user if request.user.role == User.Role.ADMIN else None,
                "status": DieselDailyRoutePlan.Status.PUBLISHED,
            },
        )
        if plan.transporter_id != transporter.id:
            plan.transporter = transporter
        requested_status = (payload.get("status") or "").strip().upper()
        if requested_status not in {
            DieselDailyRoutePlan.Status.DRAFT,
            DieselDailyRoutePlan.Status.PUBLISHED,
        }:
            requested_status = DieselDailyRoutePlan.Status.PUBLISHED
        plan.status = requested_status
        if request.user.role == User.Role.ADMIN:
            plan.created_by = request.user
        plan.save(update_fields=["transporter", "status", "created_by", "updated_at"])

        if not stops_raw:
            plan.stops.all().delete()
            return Response(
                {
                    "detail": "Daily route plan cleared.",
                    "plan_id": plan.id,
                    "stops_count": 0,
                },
                status=status.HTTP_200_OK,
            )

        normalized_stops: list[DieselDailyRoutePlanStop] = []
        seen_site_ids: set[str] = set()
        for index, raw_stop in enumerate(stops_raw, start=1):
            if not isinstance(raw_stop, dict):
                return Response(
                    {"detail": f"Stop #{index} is invalid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                site_id = validate_indus_site_id(raw_stop.get("indus_site_id"))
            except DjangoValidationError as exc:
                return Response(
                    {"detail": f"Stop #{index}: {exc.messages[0]}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if site_id.upper() in seen_site_ids:
                return Response(
                    {"detail": f"Stop #{index}: duplicate site ID {site_id}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen_site_ids.add(site_id.upper())

            qty_raw = raw_stop.get("planned_qty")
            try:
                planned_qty = Decimal(str(qty_raw))
            except (InvalidOperation, TypeError, ValueError):
                return Response(
                    {"detail": f"Stop #{index}: planned quantity is invalid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if planned_qty < 0:
                return Response(
                    {"detail": f"Stop #{index}: planned quantity cannot be negative."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tower_site = (
                IndusTowerSite.objects.filter(
                    partner=transporter,
                    indus_site_id__iexact=site_id,
                )
                .order_by("id")
                .first()
            )

            site_name = (raw_stop.get("site_name") or "").strip()
            if not site_name and tower_site is not None:
                site_name = tower_site.site_name or ""
            latitude_raw = raw_stop.get("latitude")
            longitude_raw = raw_stop.get("longitude")
            latitude = None
            longitude = None
            if latitude_raw not in {None, ""} and longitude_raw not in {None, ""}:
                try:
                    latitude = Decimal(str(latitude_raw))
                    longitude = Decimal(str(longitude_raw))
                    validate_lat_lon(float(latitude), float(longitude))
                except (InvalidOperation, ValueError) as exc:
                    return Response(
                        {"detail": f"Stop #{index}: invalid coordinates ({exc})."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif tower_site is not None:
                latitude = tower_site.latitude
                longitude = tower_site.longitude

            stop = DieselDailyRoutePlanStop(
                plan=plan,
                sequence=index,
                tower_site=tower_site,
                indus_site_id=site_id,
                site_name=site_name,
                latitude=latitude,
                longitude=longitude,
                planned_qty=planned_qty,
                notes=(raw_stop.get("notes") or "").strip(),
            )
            try:
                stop.full_clean()
            except DjangoValidationError as exc:
                message = exc.messages[0] if exc.messages else "Invalid stop."
                return Response(
                    {"detail": f"Stop #{index}: {message}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            normalized_stops.append(stop)

        plan.stops.all().delete()
        DieselDailyRoutePlanStop.objects.bulk_create(normalized_stops, batch_size=200)
        return Response(
            {
                "detail": "Daily route plan saved successfully.",
                "plan_id": plan.id,
                "stops_count": len(normalized_stops),
                "status": plan.status,
            },
            status=status.HTTP_200_OK,
        )


class TowerDieselSiteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER, User.Role.DRIVER}:
            return Response(
                {"detail": "Only admin, transporter or driver can access tower site list."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()

        search_query = (request.query_params.get("q") or "").strip()
        try:
            limit = int(request.query_params.get("limit", 250))
        except ValueError:
            limit = 250
        limit = max(1, min(limit, 500))
        latitude_raw = (request.query_params.get("latitude") or "").strip()
        longitude_raw = (request.query_params.get("longitude") or "").strip()
        latitude = None
        longitude = None
        if latitude_raw or longitude_raw:
            try:
                latitude = float(latitude_raw)
                longitude = float(longitude_raw)
            except ValueError:
                return Response(
                    {"detail": "latitude and longitude must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        partner_id = request.query_params.get("partner_id")
        if request.user.role == User.Role.ADMIN and partner_id is not None:
            try:
                partner_id = int(partner_id)
            except ValueError:
                return Response(
                    {"detail": "partner_id must be numeric."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif request.user.role != User.Role.ADMIN:
            partner_id = None

        site_queryset = _tower_site_queryset_for_user(
            request.user,
            partner_id=partner_id,
            require_site_name=False,
        )
        if search_query:
            site_queryset = site_queryset.filter(
                Q(indus_site_id__icontains=search_query)
                | Q(site_name__icontains=search_query)
            )

        rows = list(
            site_queryset.values(
                "id",
                "indus_site_id",
                "site_name",
                "latitude",
                "longitude",
            )
            .order_by("site_name", "indus_site_id")[:limit]
        )
        if not rows:
            return Response({"count": 0, "items": []}, status=status.HTTP_200_OK)

        site_ids = [row["id"] for row in rows]
        latest_fill_by_site = {}
        latest_fill_records = (
            FuelRecord.objects.filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                tower_site_id__in=site_ids,
            )
            .only("tower_site_id", "fill_date", "fuel_filled", "created_at")
            .order_by("tower_site_id", "-fill_date", "-created_at", "-id")
        )
        for fill_record in latest_fill_records:
            if fill_record.tower_site_id in latest_fill_by_site:
                continue
            latest_fill_by_site[fill_record.tower_site_id] = {
                "last_fill_date": fill_record.fill_date,
                "last_filled_quantity": float(fill_record.fuel_filled)
                if fill_record.fuel_filled is not None
                else None,
            }
        items = [
            {
                "indus_site_id": row["indus_site_id"].strip(),
                "site_name": row["site_name"].strip(),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "distance_m": (
                    round(
                        _haversine_distance_meters(
                            latitude,
                            longitude,
                            float(row["latitude"]),
                            float(row["longitude"]),
                        ),
                        1,
                    )
                    if latitude is not None and longitude is not None
                    else 0
                ),
                "last_fill_date": (
                    latest_fill_by_site[row["id"]]["last_fill_date"].isoformat()
                    if latest_fill_by_site.get(row["id"]) is not None
                    else None
                ),
                "last_filled_quantity": (
                    latest_fill_by_site[row["id"]]["last_filled_quantity"]
                    if latest_fill_by_site.get(row["id"]) is not None
                    else None
                ),
            }
            for row in rows
        ]
        if latitude is not None and longitude is not None:
            items.sort(key=lambda item: (item["distance_m"], item["site_name"].lower()))
        return Response(
            {
                "count": len(items),
                "items": items,
            },
            status=status.HTTP_200_OK,
        )


class TowerDieselSiteByIdView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER, User.Role.DRIVER}:
            return Response(
                {"detail": "Only admin, transporter or driver can access tower site lookup."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()

        site_id = (request.query_params.get("indus_site_id") or "").strip()
        if not site_id:
            return Response(
                {"detail": "indus_site_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            site_id = validate_indus_site_id(site_id)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = _tower_site_queryset_for_user(
            request.user,
            require_site_name=False,
            require_coordinates=False,
        )
        site = queryset.filter(indus_site_id__iexact=site_id).order_by("id").first()
        if site is None:
            return Response(
                {"detail": "Tower site not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        latest_fill = (
            FuelRecord.objects.filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                tower_site=site,
            )
            .only("fill_date", "fuel_filled", "created_at")
            .order_by("-fill_date", "-created_at", "-id")
            .first()
        )
        return Response(
            {
                "indus_site_id": site.indus_site_id,
                "site_name": site.site_name,
                "latitude": float(site.latitude) if site.latitude is not None else None,
                "longitude": float(site.longitude) if site.longitude is not None else None,
                "distance_m": 0,
                "last_fill_date": latest_fill.fill_date.isoformat() if latest_fill else None,
                "last_filled_quantity": (
                    float(latest_fill.fuel_filled)
                    if latest_fill and latest_fill.fuel_filled is not None
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )


def _build_tripsheet_rows(queryset):
    grouped = {}
    for item in queryset:
        day_key = (item.fill_date, item.vehicle_id)
        attendance_start_km = (
            item.attendance.start_km if item.attendance_id and item.attendance else None
        )
        attendance_end_km = (
            item.attendance.end_km if item.attendance_id and item.attendance else None
        )
        started_at = (
            item.attendance.started_at
            if item.attendance_id and item.attendance and item.attendance.started_at
            else item.created_at
        )
        bucket = grouped.setdefault(
            day_key,
            {
                "date": item.fill_date,
                "vehicle_number": item.vehicle.vehicle_number,
                "start_km": attendance_start_km if attendance_start_km is not None else (item.start_km or 0),
                "end_km": attendance_end_km if attendance_end_km is not None else (item.end_km or 0),
                "sort_started_at": started_at,
                "records": [],
            },
        )
        bucket["sort_started_at"] = min(bucket["sort_started_at"], started_at)
        start_candidates = [value for value in [attendance_start_km, item.start_km] if value is not None]
        if start_candidates:
            bucket["start_km"] = min([bucket["start_km"], *start_candidates])

        end_candidates = [value for value in [attendance_end_km, item.end_km] if value is not None]
        if end_candidates:
            bucket["end_km"] = max([bucket["end_km"], *end_candidates])
        bucket["records"].append(item)

    day_groups = sorted(
        grouped.values(),
        key=lambda row: (row["date"], row["sort_started_at"], row["vehicle_number"]),
    )

    rows = []
    index = 1
    for day_group in day_groups:
        run_km = max(day_group["end_km"] - day_group["start_km"], 0)
        sorted_records = sorted(day_group["records"], key=lambda record: (record.created_at, record.id))
        for record_index, item in enumerate(sorted_records):
            rows.append(
                {
                    "sl_no": index,
                    "date": item.fill_date,
                    "start_km": day_group["start_km"] if record_index == 0 else "",
                    "end_km": day_group["end_km"] if record_index == 0 else "",
                    "run_km": run_km if record_index == 0 else "",
                    "indus_site_id": item.resolved_indus_site_id or "",
                    "site_name": item.resolved_site_name or "",
                    "fuel_filled": str(item.fuel_filled or item.liters or ""),
                    "piu_reading": str(item.piu_reading) if item.piu_reading is not None else "",
                    "dg_hmr": str(item.dg_hmr) if item.dg_hmr is not None else "",
                    "opening_stock": str(item.opening_stock) if item.opening_stock is not None else "",
                    "purpose": item.purpose or "Diesel Filling",
                    "vehicle_number": item.vehicle.vehicle_number,
                    "driver_name": item.driver.user.username,
                    "is_day_summary": record_index == 0,
                }
            )
            index += 1
    return rows


def _build_diesel_pdf_table_data(
    rows,
    include_filled_quantity: bool = False,
    include_readings: bool = False,
):
    header_row = [
        "Sl No",
        "Date",
        "Vehicle",
        "Start KM",
        "End KM",
        "Run KM",
        "Site ID",
        "Site Name",
    ]
    if include_readings:
        header_row.extend(["PIU", "DG HMR", "Opening Stock"])
    if include_filled_quantity:
        header_row.append("Filled Qty")
    header_row.append("Purpose")
    table_data = [header_row]
    vehicle_change_row_indexes = []
    previous_date = None
    previous_vehicle = None

    for row in rows:
        if (
            row["is_day_summary"]
            and previous_date == row["date"]
            and previous_vehicle
            and previous_vehicle != row["vehicle_number"]
        ):
            marker_row = [f"Vehicle changed to {row['vehicle_number']}"]
            marker_row.extend([""] * (len(header_row) - 1))
            table_data.append(marker_row)
            vehicle_change_row_indexes.append(len(table_data) - 1)

        data_row = [
            row["sl_no"],
            row["date"],
            row["vehicle_number"],
            row["start_km"],
            row["end_km"],
            row["run_km"],
            row["indus_site_id"],
            row["site_name"],
        ]
        if include_readings:
            data_row.extend(
                [
                    row.get("piu_reading", ""),
                    row.get("dg_hmr", ""),
                    row.get("opening_stock", ""),
                ]
            )
        if include_filled_quantity:
            data_row.append(row["fuel_filled"])
        data_row.append(row["purpose"])
        table_data.append(data_row)
        if row["is_day_summary"]:
            previous_date = row["date"]
            previous_vehicle = row["vehicle_number"]

    return table_data, vehicle_change_row_indexes


class TowerDieselTripSheetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in {User.Role.ADMIN, User.Role.TRANSPORTER}:
            return Response(
                {"detail": "Only admin or transporter can access tower diesel trip sheet."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.role != User.Role.ADMIN and not _is_diesel_module_enabled_for_user(
            request.user
        ):
            return _diesel_module_disabled_response()

        date_from, date_to, error_response = _parse_date_range(request)
        if error_response is not None:
            return error_response

        queryset = _diesel_queryset_for_user(request.user).filter(
            fill_date__gte=date_from,
            fill_date__lte=date_to,
        )
        vehicle_id = request.query_params.get("vehicle_id")
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        queryset = queryset.order_by("fill_date", "vehicle__vehicle_number", "created_at")
        rows = _build_tripsheet_rows(queryset)
        total_run_km = sum(int(item["run_km"]) for item in rows if item["is_day_summary"])
        total_days = len({item["date"] for item in rows})
        total_fillings = len(rows)
        return Response(
            {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "total_entries": len(rows),
                "total_days": total_days,
                "total_fillings": total_fillings,
                "total_run_km": total_run_km,
                "rows": rows,
            },
            status=status.HTTP_200_OK,
        )


class TowerDieselTripSheetPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"detail": "PDF dependency missing. Install reportlab on server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        json_response = TowerDieselTripSheetView().get(request)
        if json_response.status_code != status.HTTP_200_OK:
            return json_response

        payload = json_response.data
        include_filled_quantity = str(
            request.query_params.get("include_filled_quantity", "")
        ).strip().lower() in {"1", "true", "yes", "on"}
        include_readings_requested = str(
            request.query_params.get("include_readings", "")
        ).strip().lower() in {"1", "true", "yes", "on"}
        include_readings = include_readings_requested and _is_diesel_readings_enabled_for_user(
            request.user
        )
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )
        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph("Diesel Fill Trip Sheet", styles["Title"]))
        elements.append(
            Paragraph(
                f"Date Range: {payload['date_from']} to {payload['date_to']}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 3 * mm))

        table_data, vehicle_change_row_indexes = _build_diesel_pdf_table_data(
            payload["rows"],
            include_filled_quantity=include_filled_quantity,
            include_readings=include_readings,
        )

        if include_readings:
            col_widths = [
                12 * mm,  # Sl No
                18 * mm,  # Date
                22 * mm,  # Vehicle
                16 * mm,  # Start KM
                16 * mm,  # End KM
                16 * mm,  # Run KM
                22 * mm,  # Site ID
                36 * mm,  # Site Name
                16 * mm,  # PIU
                16 * mm,  # DG HMR
                18 * mm,  # Opening Stock
            ]
            if include_filled_quantity:
                col_widths.append(16 * mm)  # Filled Qty
                col_widths.append(39 * mm)  # Purpose
            else:
                col_widths.append(55 * mm)  # Purpose
        else:
            col_widths = [
                14 * mm,
                20 * mm,
                24 * mm,
                18 * mm,
                18 * mm,
                18 * mm,
                24 * mm,
                42 * mm,
            ]
            if include_filled_quantity:
                col_widths.append(18 * mm)
                col_widths.append(54 * mm)
            else:
                col_widths.append(64 * mm)

        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
        )
        site_name_column = 7
        purpose_column = len(table_data[0]) - 1
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17395F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.3),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (site_name_column, 0), (site_name_column, -1), "LEFT"),
                    ("ALIGN", (purpose_column, 0), (purpose_column, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        for row_index in vehicle_change_row_indexes:
            table.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, row_index), (-1, row_index)),
                        ("FONTNAME", (0, row_index), (0, row_index), "Helvetica-Bold"),
                        ("ALIGN", (0, row_index), (0, row_index), "LEFT"),
                    ]
                )
            )
        elements.append(table)
        elements.append(Spacer(1, 3 * mm))
        elements.append(
            Paragraph(
                f"Total Days: {payload['total_days']} | Total Fillings: {payload['total_fillings']} | Total Run KM: {payload['total_run_km']}",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 10 * mm))

        signature_table = Table(
            [
                [
                    "Accountant",
                    "IME Manager",
                    "Zonal Head",
                ],
                [
                    "__________________________",
                    "__________________________",
                    "__________________________",
                ],
            ],
            colWidths=[85 * mm, 85 * mm, 85 * mm],
            hAlign="CENTER",
        )
        signature_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.append(signature_table)

        document.build(elements)
        pdf_bytes = buffer.getvalue()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response[
            "Content-Disposition"
        ] = f'attachment; filename="diesel-fill-trip-sheet-{payload["date_from"]}-to-{payload["date_to"]}.pdf"'
        return response
