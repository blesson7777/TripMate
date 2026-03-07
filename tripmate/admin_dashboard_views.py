from __future__ import annotations

from base64 import b64decode
from calendar import monthrange
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import urlencode
import uuid

from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from attendance.models import Attendance, DriverDailyAttendanceMark, TransportService
from diesel.models import IndusTowerSite
from diesel.site_utils import (
    SiteNameUpdateConfirmationRequired,
    ensure_site_name_update_confirmed,
    validate_indus_site_id,
    validate_site_name,
)
from diesel.views import (
    _build_diesel_pdf_table_data,
    _build_tripsheet_rows as _build_diesel_tripsheet_rows,
)
from drivers.models import Driver
from fuel.analytics import get_vehicle_fuel_status
from fuel.models import FuelRecord
from salary.email_utils import send_salary_balance_email_now
from trips.models import Trip
from users.models import (
    AdminBroadcastNotification,
    AppRelease,
    FeatureToggleLog,
    Transporter,
    UserDeviceToken,
    User,
)
from users.notification_utils import (
    create_app_release_update_notifications,
    create_attendance_mark_updated_notification,
    create_driver_account_status_notification,
    create_driver_force_password_reset_notification,
    create_driver_transporter_removed_notification,
    create_transporter_account_status_notification,
    create_transporter_force_password_reset_notification,
    create_diesel_module_toggled_notifications,
    send_admin_broadcast_push,
)
from users.services import send_password_reset_otp
from vehicles.models import Vehicle

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


def _is_admin_console_user(request: HttpRequest) -> bool:
    if not request.user.is_authenticated:
        return False
    return bool(request.user.is_superuser or request.user.role == User.Role.ADMIN)


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not _is_admin_console_user(request):
            return redirect("admin_login")
        if request.session.get("admin_locked") and request.resolver_match and request.resolver_match.url_name != "lock_screen":
            return redirect("lock_screen")
        return view_func(request, *args, **kwargs)

    return wrapper


def _safe_next_url(request: HttpRequest, fallback: str) -> str:
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def _base_context(request: HttpRequest) -> dict:
    return {
        "current_theme": request.session.get("admin_theme", "light"),
        "profile_photo_url": request.session.get("admin_profile_photo_url", ""),
        "phone_number": getattr(request.user, "phone", "") if request.user.is_authenticated else "",
        "is_admin_console_user": _is_admin_console_user(request),
    }


def _render_admin(request: HttpRequest, template_name: str, context: dict | None = None) -> HttpResponse:
    payload = _base_context(request)
    if context:
        payload.update(context)
    return render(request, template_name, payload)


def _has_active_mobile_token(user: User, app_variant: str) -> bool:
    return UserDeviceToken.objects.filter(
        user=user,
        app_variant=app_variant,
        is_active=True,
    ).exists()


def _parse_date_param(raw_value: str | None, fallback: date) -> date:
    if not raw_value:
        return fallback
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return fallback


def _parse_month_year(request: HttpRequest) -> tuple[int, int]:
    today = timezone.localdate()
    try:
        month = int(request.GET.get("month", today.month))
    except (TypeError, ValueError):
        month = today.month

    try:
        year = int(request.GET.get("year", today.year))
    except (TypeError, ValueError):
        year = today.year

    if month < 1 or month > 12:
        month = today.month

    return month, year


def _previous_month(value: date) -> tuple[int, int]:
    if value.month == 1:
        return 12, value.year - 1
    return value.month - 1, value.year


def _activate_app_release(release: AppRelease) -> None:
    published_at = release.published_at or timezone.now()
    (
        AppRelease.objects.filter(app_variant=release.app_variant)
        .exclude(pk=release.pk)
        .update(is_active=False)
    )
    release.is_active = True
    release.published_at = published_at
    release.save(update_fields=["is_active", "published_at", "updated_at"])
    create_app_release_update_notifications(release=release)


def _resolve_admin_attendance_view_status(
    *,
    attendance: Attendance | None,
    mark: DriverDailyAttendanceMark | None,
    target_date: date,
    today: date,
    joined_date: date | None = None,
) -> str:
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


def _build_admin_fuel_mileage_summary(
    *,
    month: int,
    year: int,
    transporter_id: str,
) -> dict:
    # Keep this aligned with reports.views.FuelMonthlySummaryView logic.
    scoped_fuel_records = FuelRecord.objects.select_related(
        "vehicle",
        "driver",
        "driver__user",
    ).filter(entry_type=FuelRecord.EntryType.VEHICLE_FILLING)
    if transporter_id.isdigit():
        scoped_fuel_records = scoped_fuel_records.filter(
            vehicle__transporter_id=int(transporter_id)
        )

    fuel_records = scoped_fuel_records.filter(
        date__year=year,
        date__month=month,
    )

    grouped_fuel = (
        fuel_records.values("vehicle_id", "vehicle__vehicle_number")
        .annotate(
            fuel_fill_count=Count("id"),
            total_liters=Coalesce(Sum("liters"), Decimal("0.00")),
            total_amount=Coalesce(Sum("amount"), Decimal("0.00")),
        )
        .order_by("vehicle__vehicle_number")
    )

    monthly_records_by_vehicle = {}
    for record in fuel_records.order_by("vehicle_id", "date", "created_at", "id"):
        monthly_records_by_vehicle.setdefault(record.vehicle_id, []).append(record)

    month_start = date(year, month, 1)
    previous_full_records = {}
    if monthly_records_by_vehicle:
        previous_queryset = (
            scoped_fuel_records.filter(
                vehicle_id__in=list(monthly_records_by_vehicle.keys()),
                date__lt=month_start,
                odometer_km__isnull=False,
            )
            .order_by("vehicle_id", "-date", "-created_at", "-id")
        )
        for previous in previous_queryset:
            if previous.vehicle_id not in previous_full_records:
                previous_full_records[previous.vehicle_id] = previous

    rows = []
    overall_liters = Decimal("0.00")
    overall_amount = Decimal("0.00")
    overall_mileage_km = 0
    overall_mileage_liters = Decimal("0.00")

    for item in grouped_fuel:
        vehicle_id = item["vehicle_id"]
        total_liters = Decimal(item["total_liters"] or 0)
        total_amount = Decimal(item["total_amount"] or 0)
        mileage_km = 0
        mileage_liters = Decimal("0.00")

        sequence = []
        previous_record = previous_full_records.get(vehicle_id)
        if previous_record is not None:
            sequence.append(previous_record)
        sequence.extend(monthly_records_by_vehicle.get(vehicle_id, []))

        for index in range(1, len(sequence)):
            prev_record = sequence[index - 1]
            curr_record = sequence[index]
            if prev_record.odometer_km is None or curr_record.odometer_km is None:
                continue
            delta_km = curr_record.odometer_km - prev_record.odometer_km
            if delta_km <= 0:
                continue
            if curr_record.liters is None or curr_record.liters <= 0:
                continue
            mileage_km += delta_km
            mileage_liters += Decimal(curr_record.liters)

        if mileage_liters > 0:
            average_mileage = (Decimal(mileage_km) / mileage_liters).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        else:
            average_mileage = Decimal("0.00")

        rows.append(
            {
                "vehicle_number": item["vehicle__vehicle_number"],
                "fuel_fill_count": int(item["fuel_fill_count"] or 0),
                "total_liters": total_liters.quantize(Decimal("0.01")),
                "total_amount": total_amount.quantize(Decimal("0.01")),
                "total_km": mileage_km,
                "average_mileage": average_mileage,
            }
        )

        overall_liters += total_liters
        overall_amount += total_amount
        overall_mileage_km += mileage_km
        overall_mileage_liters += mileage_liters

    if overall_mileage_liters > 0:
        overall_average = (Decimal(overall_mileage_km) / overall_mileage_liters).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    else:
        overall_average = Decimal("0.00")

    return {
        "month": month,
        "year": year,
        "rows": rows,
        "total_vehicles": len(rows),
        "total_liters": overall_liters.quantize(Decimal("0.01")),
        "total_amount": overall_amount.quantize(Decimal("0.01")),
        "overall_average_mileage": overall_average,
    }


def _build_admin_fuel_balance_rows(
    *,
    transporter_id: str,
    fuel_records: list[FuelRecord],
) -> list[dict]:
    vehicles_queryset = Vehicle.objects.select_related("transporter").order_by("vehicle_number")
    if transporter_id.isdigit():
        vehicles_queryset = vehicles_queryset.filter(transporter_id=int(transporter_id))
    else:
        vehicle_ids = sorted({record.vehicle_id for record in fuel_records})
        vehicles_queryset = vehicles_queryset.filter(id__in=vehicle_ids)

    rows = []
    for vehicle in vehicles_queryset:
        snapshot = get_vehicle_fuel_status(vehicle)
        if snapshot is None:
            continue

        percent_left = float(snapshot.estimated_fuel_left_percent)
        if percent_left <= 10:
            progress_class = "bg-danger"
        elif percent_left <= 30:
            progress_class = "bg-warning"
        elif percent_left <= 50:
            progress_class = "bg-info"
        else:
            progress_class = "bg-success"

        rows.append(
            {
                "vehicle_number": vehicle.vehicle_number,
                "transporter_name": vehicle.transporter.company_name,
                "tank_capacity_liters": snapshot.estimated_tank_capacity_liters,
                "tank_capacity_source": snapshot.tank_capacity_source,
                "fuel_left_liters": snapshot.estimated_fuel_left_liters,
                "fuel_left_percent": snapshot.estimated_fuel_left_percent,
                "km_left": snapshot.estimated_km_left,
                "average_mileage": snapshot.average_mileage_km_per_liter,
                "last_fill_date": snapshot.last_fill_date,
                "last_fill_liters": snapshot.last_fill_liters,
                "latest_odometer_km": snapshot.latest_odometer_km,
                "progress_width": max(0.0, min(percent_left, 100.0)),
                "progress_class": progress_class,
            }
        )

    rows.sort(key=lambda item: (item["fuel_left_percent"], item["vehicle_number"]))
    return rows


def _audit_items(query: str = "") -> list[SimpleNamespace]:
    entries = LogEntry.objects.select_related("user").order_by("-action_time")[:150]
    query_lc = query.lower()
    items: list[SimpleNamespace] = []
    for entry in entries:
        action = entry.get_change_message() or entry.get_action_flag_display() or "Updated"
        details = entry.object_repr or ""
        actor = entry.user
        haystack = f"{action} {details} {actor.username if actor else ''}".lower()
        if query_lc and query_lc not in haystack:
            continue
        items.append(
            SimpleNamespace(
                created_at=entry.action_time,
                actor=actor,
                action=action,
                target_user=None,
                details=details,
            )
        )
    return items


_ADMIN_PLACEHOLDER_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBgL9l9wAAAABJRU5ErkJggg=="
)


def _admin_placeholder_odo_image(label: str) -> ContentFile:
    return ContentFile(
        _ADMIN_PLACEHOLDER_PNG,
        name=f"admin-odo-{label}-{uuid.uuid4().hex[:10]}.png",
    )


def _build_admin_diesel_manual_context(request: HttpRequest) -> dict:
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_input = request.GET.get("date", "").strip()
    manual_driver_id = request.GET.get("manual_driver_id", "").strip()
    manual_attendance_id = request.GET.get("manual_attendance_id", "").strip()

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).select_related("user").first()
        if transporter_id.isdigit()
        else None
    )

    diesel_vehicles = Vehicle.objects.select_related("transporter").filter(
        vehicle_type=Vehicle.Type.DIESEL_SERVICE
    ).order_by("vehicle_number")
    drivers = Driver.objects.select_related("user", "transporter").order_by("user__username")
    services = TransportService.objects.select_related("transporter").order_by("name")

    if selected_transporter is not None:
        diesel_vehicles = diesel_vehicles.filter(transporter=selected_transporter)
        drivers = drivers.filter(transporter=selected_transporter)
        services = services.filter(transporter=selected_transporter)
    else:
        diesel_vehicles = diesel_vehicles.none()
        drivers = drivers.none()
        services = services.none()

    prepared_attendances = (
        Attendance.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
            "service",
        )
        .filter(
            Q(vehicle__vehicle_type=Vehicle.Type.DIESEL_SERVICE)
            | Q(service__name__iexact="Diesel Filling Vehicle")
            | Q(service_name__iexact="Diesel Filling Vehicle")
        )
        .order_by("-date", "-started_at", "-id")
    )
    if selected_transporter is not None:
        prepared_attendances = prepared_attendances.filter(
            vehicle__transporter=selected_transporter
        )
    else:
        prepared_attendances = prepared_attendances.none()
    if date_input:
        prepared_attendances = prepared_attendances.filter(
            date=_parse_date_param(date_input, timezone.localdate())
        )

    return {
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id,
        "date_input": date_input,
        "manual_driver_id": manual_driver_id,
        "manual_attendance_id": manual_attendance_id,
        "drivers": drivers[:400],
        "diesel_vehicles": diesel_vehicles[:300],
        "services": services[:200],
        "prepared_attendances": prepared_attendances[:120],
    }


def _build_admin_manual_vehicle_trip_context(request: HttpRequest) -> dict:
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_input = request.GET.get("date", "").strip()
    edit_attendance_id = request.GET.get("edit_attendance_id", "").strip()

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).select_related("user").first()
        if transporter_id.isdigit()
        else None
    )

    vehicles = Vehicle.objects.select_related("transporter").order_by("vehicle_number")
    drivers = Driver.objects.select_related("user", "transporter").order_by("user__username")
    services = TransportService.objects.select_related("transporter").order_by("name")
    attendance_rows = (
        Attendance.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
            "service",
        )
        .order_by("-date", "-started_at", "-id")
    )

    if selected_transporter is not None:
        vehicles = vehicles.filter(transporter=selected_transporter)
        drivers = drivers.filter(transporter=selected_transporter)
        services = services.filter(transporter=selected_transporter)
        attendance_rows = attendance_rows.filter(vehicle__transporter=selected_transporter)
    else:
        vehicles = vehicles.none()
        drivers = drivers.none()
        services = services.none()
        attendance_rows = attendance_rows.none()

    if date_input:
        attendance_rows = attendance_rows.filter(
            date=_parse_date_param(date_input, timezone.localdate())
        )

    edit_attendance = None
    if edit_attendance_id.isdigit():
        edit_attendance = attendance_rows.filter(id=int(edit_attendance_id)).first()
        if edit_attendance is None:
            edit_attendance = (
                Attendance.objects.select_related(
                    "driver",
                    "driver__user",
                    "vehicle",
                    "service",
                )
                .filter(id=int(edit_attendance_id))
                .first()
            )

    if edit_attendance is not None:
        initial_driver_id = str(edit_attendance.driver_id)
        initial_vehicle_id = str(edit_attendance.vehicle_id)
        initial_service_id = str(edit_attendance.service_id) if edit_attendance.service_id else ""
        initial_trip_date = edit_attendance.date.isoformat()
        initial_start_km = edit_attendance.start_km
        initial_end_km = (
            edit_attendance.end_km
            if edit_attendance.end_km is not None
            else edit_attendance.start_km
        )
        initial_service_purpose = edit_attendance.service_purpose
    else:
        initial_driver_id = request.GET.get("driver_id", "").strip()
        initial_vehicle_id = request.GET.get("vehicle_id", "").strip()
        initial_service_id = request.GET.get("service_id", "").strip()
        initial_trip_date = date_input
        initial_start_km = request.GET.get("start_km", "").strip()
        initial_end_km = request.GET.get("end_km", "").strip()
        initial_service_purpose = request.GET.get("service_purpose", "").strip()

    return {
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id,
        "date_input": date_input,
        "vehicles": vehicles[:500],
        "drivers": drivers[:400],
        "services": services[:200],
        "attendance_rows": attendance_rows[:160],
        "edit_attendance": edit_attendance,
        "initial_driver_id": initial_driver_id,
        "initial_vehicle_id": initial_vehicle_id,
        "initial_service_id": initial_service_id,
        "initial_trip_date": initial_trip_date,
        "initial_start_km": initial_start_km,
        "initial_end_km": initial_end_km,
        "initial_service_purpose": initial_service_purpose,
    }


def _create_or_update_admin_day_trip(
    *,
    driver: Driver,
    vehicle: Vehicle,
    service: TransportService,
    target_date: date,
    start_km: int,
    end_km: int,
    service_purpose: str,
    master_purpose: str,
    marked_by: User | None,
    start_odo_image=None,
    end_odo_image=None,
    existing_attendance: Attendance | None = None,
) -> Attendance:
    if end_km < start_km:
        raise ValidationError("Closing KM must be greater than or equal to opening KM.")
    if driver.transporter_id != vehicle.transporter_id:
        raise ValidationError("Driver and vehicle must belong to the same transporter.")
    if driver.transporter_id != service.transporter_id:
        raise ValidationError("Selected service must belong to the same transporter.")

    attendance = existing_attendance
    if attendance is None:
        attendance = (
            Attendance.objects.select_related("service")
            .filter(
                driver=driver,
                date=target_date,
                vehicle=vehicle,
                service=service,
            )
            .order_by("-started_at", "-id")
            .first()
        )
    elif Attendance.objects.filter(
        driver=driver,
        date=target_date,
        vehicle=vehicle,
        service=service,
    ).exclude(id=attendance.id).exists():
        raise ValidationError(
            "Another day trip already exists for this driver, vehicle, service, and date."
        )

    if attendance is not None and attendance.trips.filter(is_day_trip=False).exists():
        raise ValidationError(
            (
                "This day record already has child trips. "
                "Use the trips page for that service record."
            )
        )

    now = timezone.now()
    resolved_start_odo_image = start_odo_image
    if attendance is None:
        attendance = Attendance.objects.create(
            driver=driver,
            vehicle=vehicle,
            date=target_date,
            status=Attendance.Status.ON_DUTY,
            service=service,
            service_name=service.name,
            service_purpose=service_purpose,
            start_km=start_km,
            end_km=end_km,
            odo_start_image=resolved_start_odo_image
            or _admin_placeholder_odo_image(
                f"{driver.id}-{vehicle.id}-{target_date.isoformat()}"
            ),
            odo_end_image=end_odo_image,
            latitude=Decimal("0.000000"),
            longitude=Decimal("0.000000"),
            started_at=now,
            ended_at=now,
        )
    else:
        fields_to_update = [
            "driver",
            "vehicle",
            "date",
            "service",
            "service_name",
            "service_purpose",
            "start_km",
            "end_km",
            "status",
            "ended_at",
        ]
        attendance.driver = driver
        attendance.vehicle = vehicle
        attendance.date = target_date
        attendance.service = service
        attendance.service_name = service.name
        attendance.service_purpose = service_purpose
        attendance.start_km = start_km
        attendance.end_km = end_km
        attendance.status = Attendance.Status.ON_DUTY
        attendance.ended_at = now
        if attendance.started_at is None:
            attendance.started_at = now
            fields_to_update.append("started_at")
        if resolved_start_odo_image is not None:
            attendance.odo_start_image = resolved_start_odo_image
            fields_to_update.append("odo_start_image")
        elif not attendance.odo_start_image:
            attendance.odo_start_image = _admin_placeholder_odo_image(
                f"{driver.id}-{vehicle.id}-{target_date.isoformat()}"
            )
            fields_to_update.append("odo_start_image")
        if end_odo_image is not None:
            attendance.odo_end_image = end_odo_image
            fields_to_update.append("odo_end_image")
        attendance.save(update_fields=fields_to_update)

    DriverDailyAttendanceMark.objects.update_or_create(
        driver=driver,
        transporter=driver.transporter,
        date=target_date,
        defaults={
            "status": DriverDailyAttendanceMark.Status.PRESENT,
            "marked_by": marked_by,
        },
    )

    master_trip = (
        attendance.trips.filter(
            is_day_trip=True,
            parent_trip__isnull=True,
        )
        .order_by("-started_at", "-id")
        .first()
    )
    if master_trip is None:
        Trip.objects.create(
            attendance=attendance,
            parent_trip=None,
            start_location="Day Start",
            destination="Day End",
            start_km=start_km,
            end_km=end_km,
            purpose=master_purpose,
            start_odo_image=attendance.odo_start_image,
            end_odo_image=attendance.odo_end_image,
            status=Trip.Status.CLOSED,
            is_day_trip=True,
            started_at=attendance.started_at,
            ended_at=attendance.ended_at or now,
        )
    else:
        master_trip.start_location = "Day Start"
        master_trip.destination = "Day End"
        master_trip.start_km = start_km
        master_trip.end_km = end_km
        master_trip.purpose = master_purpose
        if not master_trip.start_odo_image or start_odo_image is not None:
            master_trip.start_odo_image = attendance.odo_start_image
        if end_odo_image is not None or (
            not master_trip.end_odo_image and attendance.odo_end_image
        ):
            master_trip.end_odo_image = attendance.odo_end_image
        master_trip.status = Trip.Status.CLOSED
        master_trip.started_at = attendance.started_at
        master_trip.ended_at = attendance.ended_at or now
        master_trip.save()

    return attendance


def admin_login(request: HttpRequest) -> HttpResponse:
    if _is_admin_console_user(request) and not request.session.get("admin_locked"):
        return redirect("dashboard")

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        matched_user = User.objects.filter(
            Q(username__iexact=identifier)
            | Q(email__iexact=identifier)
            | Q(phone__iexact=identifier)
        ).first()
        username = matched_user.username if matched_user else identifier

        user = authenticate(request, username=username, password=password)
        if not user or not (user.is_superuser or user.role == User.Role.ADMIN):
            messages.error(request, "Invalid admin credentials.")
            return _render_admin(request, "admin/login.html")

        auth_login(request, user)
        request.session["admin_locked"] = False
        return redirect(_safe_next_url(request, "/admin/"))

    return _render_admin(request, "admin/login.html")


@admin_required
def admin_logout(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("admin_login")


@admin_required
def dashboard(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()

    total_transporters = Transporter.objects.count()
    total_vehicles = Vehicle.objects.count()
    active_vehicles = Vehicle.objects.filter(status=Vehicle.Status.ACTIVE).count()
    total_drivers = Driver.objects.count()
    active_drivers = Driver.objects.filter(is_active=True).count()

    attendance_today = Attendance.objects.filter(date=today)
    on_duty_count = attendance_today.filter(status=Attendance.Status.ON_DUTY).count()
    no_trip_count = attendance_today.filter(status=Attendance.Status.NO_TRIP).count()

    trips_today = Trip.objects.filter(attendance__date=today).count()
    fuel_today = FuelRecord.objects.filter(date=today).count()

    labels = []
    trip_values = []
    fuel_values = []
    for offset in range(6, -1, -1):
        target_day = today - timedelta(days=offset)
        labels.append(target_day.strftime("%d %b"))
        trip_values.append(Trip.objects.filter(attendance__date=target_day).count())
        fuel_values.append(FuelRecord.objects.filter(date=target_day).count())

    role_distribution = {
        "labels": ["Admin", "Transporter", "Driver"],
        "values": [
            User.objects.filter(role=User.Role.ADMIN).count(),
            User.objects.filter(role=User.Role.TRANSPORTER).count(),
            User.objects.filter(role=User.Role.DRIVER).count(),
        ],
    }

    vehicle_status_distribution = {
        "labels": ["Active", "Maintenance", "Inactive"],
        "values": [
            Vehicle.objects.filter(status=Vehicle.Status.ACTIVE).count(),
            Vehicle.objects.filter(status=Vehicle.Status.MAINTENANCE).count(),
            Vehicle.objects.filter(status=Vehicle.Status.INACTIVE).count(),
        ],
    }

    recent_attendances = (
        Attendance.objects.select_related("driver", "driver__user", "vehicle")
        .order_by("-started_at")[:8]
    )

    context = {
        "total_transporters": total_transporters,
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "total_drivers": total_drivers,
        "active_drivers": active_drivers,
        "attendance_today_count": attendance_today.count(),
        "on_duty_count": on_duty_count,
        "no_trip_count": no_trip_count,
        "trips_today": trips_today,
        "fuel_today": fuel_today,
        "today": today,
        "recent_attendances": recent_attendances,
        "chart_payload": {
            "role_distribution": role_distribution,
            "vehicle_status_distribution": vehicle_status_distribution,
            "activity_trend": {
                "labels": labels,
                "trip_values": trip_values,
                "fuel_values": fuel_values,
            },
        },
    }
    return _render_admin(request, "admin/dashboard.html", context)


@admin_required
def admin_users(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    users = User.objects.order_by("-date_joined")

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(role__icontains=query)
        )

    users = users[:250]

    context = {
        "query": query,
        "users": users,
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "inactive_users": User.objects.filter(is_active=False).count(),
    }
    return _render_admin(request, "admin/users.html", context)


@admin_required
def admin_user_details(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = get_object_or_404(User, id=user_id)

    transporter_profile = getattr(target_user, "transporter_profile", None)
    driver_profile = getattr(target_user, "driver_profile", None)

    transporter_stats = None
    if transporter_profile:
        transporter_stats = {
            "vehicles": Vehicle.objects.filter(transporter=transporter_profile).count(),
            "drivers": Driver.objects.filter(transporter=transporter_profile).count(),
            "trips": Trip.objects.filter(attendance__vehicle__transporter=transporter_profile).count(),
            "fuel_records": FuelRecord.objects.filter(vehicle__transporter=transporter_profile).count(),
        }

    driver_stats = None
    if driver_profile:
        driver_stats = {
            "attendance_days": Attendance.objects.filter(driver=driver_profile).count(),
            "trips": Trip.objects.filter(attendance__driver=driver_profile).count(),
            "fuel_records": FuelRecord.objects.filter(driver=driver_profile).count(),
        }

    context = {
        "target_user": target_user,
        "target_phone_number": target_user.phone or "-",
        "member_since": target_user.date_joined,
        "last_login": target_user.last_login,
        "is_active": target_user.is_active,
        "transporter_profile": transporter_profile,
        "driver_profile": driver_profile,
        "transporter_stats": transporter_stats,
        "driver_stats": driver_stats,
    }
    return _render_admin(request, "admin/user_details.html", context)


@admin_required
def admin_toggle_user_active(request: HttpRequest, user_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_users")

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot change your own active status.")
        return redirect(_safe_next_url(request, "/admin/users/"))

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    if target_user.role == User.Role.DRIVER and hasattr(target_user, "driver_profile"):
        driver_profile = target_user.driver_profile
        if driver_profile.is_active != target_user.is_active:
            driver_profile.is_active = target_user.is_active
            driver_profile.save(update_fields=["is_active"])

    if (
        target_user.role == User.Role.TRANSPORTER
        and hasattr(target_user, "transporter_profile")
    ):
        create_transporter_account_status_notification(
            transporter=target_user.transporter_profile,
            enabled=target_user.is_active,
            actor_username=request.user.username,
        )
        if not _has_active_mobile_token(
            target_user,
            UserDeviceToken.AppVariant.TRANSPORTER,
        ):
            messages.warning(
                request,
                (
                    f"Transporter '{target_user.username}' has no active mobile token. "
                    "Ask them to login in transporter app once to enable push notifications."
                ),
            )
    elif target_user.role == User.Role.DRIVER and hasattr(target_user, "driver_profile"):
        create_driver_account_status_notification(
            driver=target_user.driver_profile,
            enabled=target_user.is_active,
            actor_username=request.user.username,
        )
        if not _has_active_mobile_token(
            target_user,
            UserDeviceToken.AppVariant.DRIVER,
        ):
            messages.warning(
                request,
                (
                    f"Driver '{target_user.username}' has no active mobile token. "
                    "Ask them to login in driver app once to enable push notifications."
                ),
            )

    messages.success(
        request,
        f"User '{target_user.username}' is now {'active' if target_user.is_active else 'inactive'}.",
    )
    return redirect(_safe_next_url(request, "/admin/users/"))


@admin_required
def admin_force_password_reset(request: HttpRequest, user_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_users")

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot force-reset your own password from this panel.")
        return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))

    normalized_email = (target_user.email or "").strip().lower()
    if not normalized_email:
        messages.error(
            request,
            f"'{target_user.username}' does not have an email configured for OTP reset.",
        )
        return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))

    try:
        send_password_reset_otp(normalized_email)
    except Exception as exc:
        messages.error(
            request,
            f"Unable to send password reset OTP for '{target_user.username}': {exc}",
        )
        return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))

    target_user.set_unusable_password()
    target_user.save(update_fields=["password"])
    if (
        target_user.role == User.Role.TRANSPORTER
        and hasattr(target_user, "transporter_profile")
    ):
        create_transporter_force_password_reset_notification(
            transporter=target_user.transporter_profile,
            actor_username=request.user.username,
        )
        if not _has_active_mobile_token(
            target_user,
            UserDeviceToken.AppVariant.TRANSPORTER,
        ):
            messages.warning(
                request,
                (
                    f"Transporter '{target_user.username}' has no active mobile token. "
                    "Push notification cannot be delivered until they login the transporter app."
                ),
            )
    elif target_user.role == User.Role.DRIVER and hasattr(target_user, "driver_profile"):
        create_driver_force_password_reset_notification(
            driver=target_user.driver_profile,
            actor_username=request.user.username,
        )
        if not _has_active_mobile_token(
            target_user,
            UserDeviceToken.AppVariant.DRIVER,
        ):
            messages.warning(
                request,
                (
                    f"Driver '{target_user.username}' has no active mobile token. "
                    "Push notification cannot be delivered until they login the driver app."
                ),
            )

    messages.success(
        request,
        (
            f"Forced password reset for '{target_user.username}'. "
            f"OTP sent to {normalized_email}."
        ),
    )
    return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))


@admin_required
def admin_delete_user(request: HttpRequest, user_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_users")

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot delete your own admin account.")
        return redirect("admin_users")
    if target_user.is_superuser:
        messages.error(request, "Deleting superuser accounts is blocked.")
        return redirect("admin_users")

    username = target_user.username
    target_user.delete()
    messages.success(request, f"User '{username}' deleted.")
    return redirect("admin_users")


@admin_required
def admin_transporters(request: HttpRequest) -> HttpResponse:
    create_form = {
        "username": "",
        "email": "",
        "phone": "",
        "company_name": "",
        "address": "",
    }

    if request.method == "POST" and request.POST.get("form_action") == "toggle_salary_auto_email":
        transporter_id_raw = request.POST.get("transporter_id", "").strip()
        enabled_raw = request.POST.get("enabled", "").strip()
        transporter = (
            Transporter.objects.select_related("user").filter(id=int(transporter_id_raw)).first()
            if transporter_id_raw.isdigit()
            else None
        )
        if transporter is None:
            messages.error(request, "Selected transporter does not exist.")
            return redirect("admin_transporters")
        if enabled_raw not in {"0", "1"}:
            messages.error(request, "Invalid salary auto mail value.")
            return redirect("admin_transporters")
        enabled = enabled_raw == "1"
        if transporter.salary_auto_email_enabled != enabled:
            transporter.salary_auto_email_enabled = enabled
            transporter.save(update_fields=["salary_auto_email_enabled"])
        messages.success(
            request,
            (
                f"Salary auto mailing {'enabled' if enabled else 'disabled'} for "
                f"'{transporter.company_name}'."
            ),
        )
        return redirect("admin_transporters")

    if request.method == "POST" and request.POST.get("form_action") == "create_transporter":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        company_name = request.POST.get("company_name", "").strip()
        address = request.POST.get("address", "").strip()

        create_form = {
            "username": username,
            "email": email,
            "phone": phone,
            "company_name": company_name,
            "address": address,
        }

        if not username or not password or not company_name:
            messages.error(request, "Username, password, and company name are required.")
        elif len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists. Choose a different username.")
        else:
            try:
                with transaction.atomic():
                    transporter_user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        phone=phone,
                        role=User.Role.TRANSPORTER,
                    )
                    Transporter.objects.create(
                        user=transporter_user,
                        company_name=company_name,
                        address=address,
                    )
                messages.success(request, f"Transporter '{company_name}' created successfully.")
                return redirect("admin_transporters")
            except IntegrityError:
                messages.error(request, "Unable to create transporter due to duplicate data.")

    query = request.GET.get("q", "").strip()
    transporters = Transporter.objects.select_related("user").annotate(
        vehicles_count=Count("vehicles", distinct=True),
        drivers_count=Count("drivers", distinct=True),
    )

    if query:
        transporters = transporters.filter(
            Q(company_name__icontains=query)
            | Q(address__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__phone__icontains=query)
        )

    context = {
        "query": query,
        "transporters": transporters.order_by("company_name")[:250],
        "total_transporters": Transporter.objects.count(),
        "total_vehicles": Vehicle.objects.count(),
        "total_drivers": Driver.objects.count(),
        "create_form": create_form,
    }
    return _render_admin(request, "admin/transporters.html", context)


@admin_required
def admin_partner_features(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        partner_id_raw = request.POST.get("partner_id", "").strip()
        enabled_raw = request.POST.get("enabled", "").strip()

        transporter = None
        if partner_id_raw.isdigit():
            transporter = Transporter.objects.filter(id=int(partner_id_raw)).first()

        if transporter is None:
            messages.error(request, "Selected transporter does not exist.")
            return redirect("admin_partner_features")

        if enabled_raw not in {"0", "1"}:
            messages.error(request, "Invalid feature toggle value.")
            return redirect("admin_partner_features")

        enabled = enabled_raw == "1"
        if transporter.diesel_tracking_enabled != enabled:
            transporter.diesel_tracking_enabled = enabled
            transporter.save(update_fields=["diesel_tracking_enabled"])
            FeatureToggleLog.objects.create(
                admin=request.user,
                partner=transporter,
                feature_name="diesel_module",
                action=(
                    FeatureToggleLog.Action.ENABLED
                    if enabled
                    else FeatureToggleLog.Action.DISABLED
                ),
            )
            create_diesel_module_toggled_notifications(
                transporter=transporter,
                enabled=enabled,
            )
            messages.success(
                request,
                (
                    f"Diesel module {'enabled' if enabled else 'disabled'} for "
                    f"{transporter.company_name}."
                ),
            )
        else:
            messages.info(
                request,
                f"Diesel module is already {'enabled' if enabled else 'disabled'} "
                f"for {transporter.company_name}.",
            )

        return redirect("admin_partner_features")

    transporters = Transporter.objects.select_related("user").order_by("company_name")
    recent_logs = FeatureToggleLog.objects.select_related("admin", "partner")[:25]
    context = {
        "transporters": transporters,
        "recent_logs": recent_logs,
    }
    return _render_admin(request, "admin/partner_features.html", context)


@admin_required
def admin_notifications(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form_action = request.POST.get("form_action", "").strip()

        if form_action == "create_notification":
            title = request.POST.get("title", "").strip()
            message = request.POST.get("message", "").strip()
            audience = request.POST.get("audience", AdminBroadcastNotification.Audience.ALL).strip()
            is_active = request.POST.get("is_active") == "1"

            valid_audiences = {choice[0] for choice in AdminBroadcastNotification.Audience.choices}
            if not title or not message:
                messages.error(request, "Title and message are required.")
                return redirect("admin_notifications")
            if audience not in valid_audiences:
                messages.error(request, "Invalid audience selected.")
                return redirect("admin_notifications")

            broadcast = AdminBroadcastNotification.objects.create(
                created_by=request.user,
                title=title,
                message=message,
                audience=audience,
                is_active=is_active,
            )
            if is_active:
                send_admin_broadcast_push(broadcast)
            messages.success(request, "Notification broadcast created.")
            return redirect("admin_notifications")

        if form_action == "toggle_notification":
            broadcast_id_raw = request.POST.get("broadcast_id", "").strip()
            if not broadcast_id_raw.isdigit():
                messages.error(request, "Invalid notification id.")
                return redirect("admin_notifications")
            broadcast = AdminBroadcastNotification.objects.filter(id=int(broadcast_id_raw)).first()
            if broadcast is None:
                messages.error(request, "Notification not found.")
                return redirect("admin_notifications")
            broadcast.is_active = not broadcast.is_active
            broadcast.save(update_fields=["is_active", "updated_at"])
            if broadcast.is_active:
                send_admin_broadcast_push(broadcast)
            messages.success(
                request,
                f"Notification {'enabled' if broadcast.is_active else 'disabled'}.",
            )
            return redirect("admin_notifications")

    broadcasts = AdminBroadcastNotification.objects.select_related("created_by")[:200]
    context = {
        "broadcasts": broadcasts,
        "audience_choices": AdminBroadcastNotification.Audience.choices,
    }
    return _render_admin(request, "admin/notifications.html", context)


@admin_required
def admin_app_releases(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form_action = request.POST.get("form_action", "").strip()

        if form_action == "create_release":
            app_variant = request.POST.get("app_variant", "").strip().upper()
            version_name = request.POST.get("version_name", "").strip()
            build_number_raw = request.POST.get("build_number", "").strip()
            apk_file = request.FILES.get("apk_file")
            message_text = request.POST.get("message", "").strip()
            force_update = request.POST.get("force_update") == "1"
            publish_now = request.POST.get("publish_now") == "1"

            if app_variant not in AppRelease.AppVariant.values:
                messages.error(request, "Select a valid app variant.")
                return redirect("admin_app_releases")
            if not version_name:
                messages.error(request, "Version name is required.")
                return redirect("admin_app_releases")
            if not build_number_raw.isdigit():
                messages.error(request, "Build number must be a positive integer.")
                return redirect("admin_app_releases")
            if apk_file is None:
                messages.error(request, "APK file is required.")
                return redirect("admin_app_releases")
            if not apk_file.name.lower().endswith(".apk"):
                messages.error(request, "Only APK files are supported.")
                return redirect("admin_app_releases")

            try:
                release = AppRelease.objects.create(
                    app_variant=app_variant,
                    version_name=version_name,
                    build_number=int(build_number_raw),
                    apk_file=apk_file,
                    force_update=force_update,
                    message=message_text,
                    is_active=publish_now,
                    uploaded_by=request.user,
                    published_at=timezone.now() if publish_now else None,
                )
            except IntegrityError:
                messages.error(
                    request,
                    "A release with the same app, version, and build number already exists.",
                )
                return redirect("admin_app_releases")

            if publish_now:
                _activate_app_release(release)
                messages.success(
                    request,
                    f"{release.get_app_variant_display()} release {release.version_name} published and pushed.",
                )
            else:
                messages.success(
                    request,
                    f"{release.get_app_variant_display()} release {release.version_name} uploaded.",
                )
            return redirect("admin_app_releases")

        if form_action in {"activate_release", "push_release", "delete_release"}:
            release_id_raw = request.POST.get("release_id", "").strip()
            if not release_id_raw.isdigit():
                messages.error(request, "Invalid release id.")
                return redirect("admin_app_releases")
            release = AppRelease.objects.filter(id=int(release_id_raw)).first()
            if release is None:
                messages.error(request, "Release not found.")
                return redirect("admin_app_releases")

            if form_action == "activate_release":
                _activate_app_release(release)
                messages.success(
                    request,
                    f"{release.get_app_variant_display()} release {release.version_name} is now active.",
                )
                return redirect("admin_app_releases")

            if form_action == "push_release":
                create_app_release_update_notifications(release=release, force_push=True)
                messages.success(
                    request,
                    f"Update push sent again for {release.get_app_variant_display()} {release.version_name}.",
                )
                return redirect("admin_app_releases")

            release.apk_file.delete(save=False)
            release.delete()
            messages.success(request, "Release deleted.")
            return redirect("admin_app_releases")

    releases = AppRelease.objects.select_related("uploaded_by").order_by(
        "app_variant",
        "-build_number",
        "-created_at",
    )
    context = {
        "releases": releases,
        "app_variant_choices": AppRelease.AppVariant.choices,
        "driver_update_api": request.build_absolute_uri(reverse("app-update", args=["driver"])),
        "transporter_update_api": request.build_absolute_uri(
            reverse("app-update", args=["transporter"])
        ),
    }
    return _render_admin(request, "admin/app_releases.html", context)


@admin_required
def admin_vehicles(request: HttpRequest) -> HttpResponse:
    create_form = {
        "transporter_id": "",
        "vehicle_number": "",
        "model": "",
        "status": Vehicle.Status.ACTIVE,
        "vehicle_type": Vehicle.Type.GENERAL,
        "tank_capacity_liters": "",
    }

    if request.method == "POST" and request.POST.get("form_action") == "update_vehicle_type":
        vehicle_id_raw = request.POST.get("vehicle_id", "").strip()
        vehicle_type_value = request.POST.get("vehicle_type", "").strip()
        valid_vehicle_types = {choice[0] for choice in Vehicle.Type.choices}
        vehicle = None
        if vehicle_id_raw.isdigit():
            vehicle = Vehicle.objects.filter(id=int(vehicle_id_raw)).first()

        if vehicle is None:
            messages.error(request, "Vehicle not found.")
            return redirect("admin_vehicles")
        if vehicle_type_value not in valid_vehicle_types:
            messages.error(request, "Invalid vehicle type.")
            return redirect("admin_vehicles")

        vehicle.vehicle_type = vehicle_type_value
        vehicle.save(update_fields=["vehicle_type"])
        messages.success(
            request,
            f"Vehicle type updated for '{vehicle.vehicle_number}'.",
        )
        return redirect("admin_vehicles")

    if request.method == "POST" and request.POST.get("form_action") == "update_vehicle_capacity":
        vehicle_id_raw = request.POST.get("vehicle_id", "").strip()
        tank_capacity_raw = request.POST.get("tank_capacity_liters", "").strip()
        vehicle = None
        if vehicle_id_raw.isdigit():
            vehicle = Vehicle.objects.filter(id=int(vehicle_id_raw)).first()

        if vehicle is None:
            messages.error(request, "Vehicle not found.")
            return redirect("admin_vehicles")

        if not tank_capacity_raw:
            vehicle.tank_capacity_liters = None
            vehicle.save(update_fields=["tank_capacity_liters"])
            messages.success(
                request,
                f"Tank capacity cleared for '{vehicle.vehicle_number}'. Estimation will use history.",
            )
            return redirect("admin_vehicles")

        try:
            tank_capacity = Decimal(tank_capacity_raw)
        except (InvalidOperation, TypeError):
            messages.error(request, "Tank capacity must be a numeric value.")
            return redirect("admin_vehicles")

        if tank_capacity <= 0:
            messages.error(request, "Tank capacity must be greater than zero.")
            return redirect("admin_vehicles")

        vehicle.tank_capacity_liters = tank_capacity.quantize(Decimal("0.01"))
        vehicle.save(update_fields=["tank_capacity_liters"])
        messages.success(
            request,
            f"Tank capacity updated for '{vehicle.vehicle_number}'.",
        )
        return redirect("admin_vehicles")

    if request.method == "POST" and request.POST.get("form_action") == "create_vehicle":
        transporter_id_raw = request.POST.get("transporter_id", "").strip()
        vehicle_number = request.POST.get("vehicle_number", "").strip().upper()
        model = request.POST.get("model", "").strip()
        status_value = request.POST.get("status", Vehicle.Status.ACTIVE).strip()
        vehicle_type_value = request.POST.get(
            "vehicle_type", Vehicle.Type.GENERAL
        ).strip()
        tank_capacity_raw = request.POST.get("tank_capacity_liters", "").strip()

        create_form = {
            "transporter_id": transporter_id_raw,
            "vehicle_number": vehicle_number,
            "model": model,
            "status": status_value,
            "vehicle_type": vehicle_type_value,
            "tank_capacity_liters": tank_capacity_raw,
        }

        transporter = None
        if transporter_id_raw.isdigit():
            transporter = Transporter.objects.filter(id=int(transporter_id_raw)).first()

        valid_statuses = {choice[0] for choice in Vehicle.Status.choices}
        valid_vehicle_types = {choice[0] for choice in Vehicle.Type.choices}
        tank_capacity_value = None
        if tank_capacity_raw:
            try:
                tank_capacity_value = Decimal(tank_capacity_raw)
            except (InvalidOperation, TypeError):
                messages.error(request, "Tank capacity must be a numeric value.")
                tank_capacity_value = "invalid"

        if not transporter:
            messages.error(request, "Select a valid transporter.")
        elif not vehicle_number or not model:
            messages.error(request, "Vehicle number and model are required.")
        elif Vehicle.objects.filter(vehicle_number__iexact=vehicle_number).exists():
            messages.error(request, "Vehicle number already exists in the system.")
        elif status_value not in valid_statuses:
            messages.error(request, "Invalid vehicle status.")
        elif vehicle_type_value not in valid_vehicle_types:
            messages.error(request, "Invalid vehicle type.")
        elif tank_capacity_value == "invalid":
            pass
        elif tank_capacity_value is not None and tank_capacity_value <= 0:
            messages.error(request, "Tank capacity must be greater than zero.")
        else:
            try:
                Vehicle.objects.create(
                    transporter=transporter,
                    vehicle_number=vehicle_number,
                    model=model,
                    status=status_value,
                    vehicle_type=vehicle_type_value,
                    tank_capacity_liters=(
                        tank_capacity_value.quantize(Decimal("0.01"))
                        if isinstance(tank_capacity_value, Decimal)
                        else None
                    ),
                )
                messages.success(request, f"Vehicle '{vehicle_number}' created successfully.")
                return redirect("admin_vehicles")
            except IntegrityError:
                messages.error(
                    request,
                    "Vehicle number already exists in the system.",
                )

    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    status_filter = request.GET.get("status", "").strip()
    vehicle_type_filter = request.GET.get("vehicle_type", "").strip()

    vehicles = Vehicle.objects.select_related("transporter", "transporter__user")

    if query:
        vehicles = vehicles.filter(
            Q(vehicle_number__icontains=query)
            | Q(model__icontains=query)
            | Q(transporter__company_name__icontains=query)
        )

    if transporter_id.isdigit():
        vehicles = vehicles.filter(transporter_id=int(transporter_id))

    if status_filter in {choice[0] for choice in Vehicle.Status.choices}:
        vehicles = vehicles.filter(status=status_filter)
    if vehicle_type_filter in {choice[0] for choice in Vehicle.Type.choices}:
        vehicles = vehicles.filter(vehicle_type=vehicle_type_filter)

    context = {
        "query": query,
        "vehicles": vehicles.order_by("vehicle_number")[:400],
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "selected_status": status_filter,
        "selected_vehicle_type": vehicle_type_filter,
        "status_choices": Vehicle.Status.choices,
        "vehicle_type_choices": Vehicle.Type.choices,
        "total_vehicles": Vehicle.objects.count(),
        "active_vehicles": Vehicle.objects.filter(status=Vehicle.Status.ACTIVE).count(),
        "maintenance_vehicles": Vehicle.objects.filter(status=Vehicle.Status.MAINTENANCE).count(),
        "diesel_service_vehicles": Vehicle.objects.filter(
            vehicle_type=Vehicle.Type.DIESEL_SERVICE
        ).count(),
        "create_form": create_form,
    }
    return _render_admin(request, "admin/vehicles.html", context)


@admin_required
def admin_drivers(request: HttpRequest) -> HttpResponse:
    create_form = {
        "transporter_id": "",
        "username": "",
        "email": "",
        "phone": "",
        "license_number": "",
        "assigned_vehicle_id": "",
        "is_active": True,
    }
    today = timezone.localdate()
    default_salary_email_month, default_salary_email_year = _previous_month(today)

    if request.method == "POST" and request.POST.get("form_action") == "remove_driver_transporter":
        driver_id_raw = request.POST.get("driver_id", "").strip()
        if not driver_id_raw.isdigit():
            messages.error(request, "Invalid driver selected for allocation removal.")
            return redirect(_safe_next_url(request, "/admin/drivers/"))

        driver = Driver.objects.select_related(
            "user",
            "transporter",
            "assigned_vehicle",
            "default_service",
        ).filter(id=int(driver_id_raw)).first()
        if driver is None:
            messages.error(request, "Driver not found.")
            return redirect(_safe_next_url(request, "/admin/drivers/"))

        previous_transporter = driver.transporter
        if previous_transporter is None:
            messages.info(request, f"Driver '{driver.user.username}' is already unallocated.")
            return redirect(_safe_next_url(request, "/admin/drivers/"))

        had_vehicle = driver.assigned_vehicle is not None
        had_service = driver.default_service is not None
        driver.transporter = None
        driver.assigned_vehicle = None
        driver.default_service = None
        driver.save(update_fields=["transporter", "assigned_vehicle", "default_service"])

        create_driver_transporter_removed_notification(
            driver=driver,
            previous_transporter=previous_transporter,
            actor_username=request.user.username,
        )

        if not _has_active_mobile_token(driver.user, UserDeviceToken.AppVariant.DRIVER):
            messages.warning(
                request,
                (
                    f"Driver '{driver.user.username}' has no active mobile token. "
                    "Push notification may not be delivered."
                ),
            )
        if not _has_active_mobile_token(
            previous_transporter.user,
            UserDeviceToken.AppVariant.TRANSPORTER,
        ):
            messages.warning(
                request,
                (
                    f"Transporter '{previous_transporter.user.username}' has no active mobile token. "
                    "Allocation removal push may not be delivered."
                ),
            )

        clear_bits = []
        if had_vehicle:
            clear_bits.append("assigned vehicle")
        if had_service:
            clear_bits.append("default service")
        clear_suffix = f" and cleared {', '.join(clear_bits)}." if clear_bits else "."
        messages.success(
            request,
            (
                f"Removed driver '{driver.user.username}' from transporter "
                f"'{previous_transporter.company_name}'{clear_suffix}"
            ),
        )
        return redirect(_safe_next_url(request, "/admin/drivers/"))

    if request.method == "POST" and request.POST.get("form_action") == "send_driver_salary_email":
        driver_id_raw = request.POST.get("driver_id", "").strip()
        month_raw = request.POST.get("salary_email_month", "").strip()
        year_raw = request.POST.get("salary_email_year", "").strip()
        next_url = _safe_next_url(request, "/admin/drivers/")

        driver = (
            Driver.objects.select_related("user", "transporter")
            .filter(id=int(driver_id_raw))
            .first()
            if driver_id_raw.isdigit()
            else None
        )
        if driver is None:
            messages.error(request, "Driver not found.")
            return redirect(next_url)
        if driver.transporter is None:
            messages.error(request, "Driver is not allocated to any transporter.")
            return redirect(next_url)
        if not driver.user.email:
            messages.error(request, "Driver does not have an email address.")
            return redirect(next_url)
        try:
            month = int(month_raw or default_salary_email_month)
            year = int(year_raw or default_salary_email_year)
        except ValueError:
            messages.error(request, "Salary email month/year must be numeric.")
            return redirect(next_url)
        if month < 1 or month > 12:
            messages.error(request, "Salary email month must be between 1 and 12.")
            return redirect(next_url)
        try:
            sent = send_salary_balance_email_now(
                driver=driver,
                month=month,
                year=year,
                current_time=timezone.now(),
            )
        except Exception as exc:
            messages.error(
                request,
                f"Unable to send salary email for '{driver.user.username}': {exc}",
            )
            return redirect(next_url)
        if sent:
            messages.success(
                request,
                (
                    f"Salary email sent to '{driver.user.username}' "
                    f"for {month:02d}/{year}."
                ),
            )
        else:
            messages.error(request, "Salary email was not sent.")
        return redirect(next_url)

    if request.method == "POST" and request.POST.get("form_action") == "create_driver":
        transporter_id_raw = request.POST.get("transporter_id", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        license_number = request.POST.get("license_number", "").strip()
        assigned_vehicle_id_raw = request.POST.get("assigned_vehicle_id", "").strip()
        is_active = request.POST.get("is_active") == "on"

        create_form = {
            "transporter_id": transporter_id_raw,
            "username": username,
            "email": email,
            "phone": phone,
            "license_number": license_number,
            "assigned_vehicle_id": assigned_vehicle_id_raw,
            "is_active": is_active,
        }

        transporter = None
        if transporter_id_raw.isdigit():
            transporter = Transporter.objects.filter(id=int(transporter_id_raw)).first()

        has_form_error = False
        assigned_vehicle = None
        if assigned_vehicle_id_raw:
            if assigned_vehicle_id_raw.isdigit():
                assigned_vehicle = Vehicle.objects.filter(id=int(assigned_vehicle_id_raw)).first()
            if not assigned_vehicle:
                messages.error(request, "Assigned vehicle does not exist.")
                has_form_error = True
            elif transporter and assigned_vehicle.transporter_id != transporter.id:
                messages.error(
                    request,
                    "Assigned vehicle must belong to the selected transporter.",
                )
                has_form_error = True

        if has_form_error:
            pass
        elif not transporter:
            messages.error(request, "Select a valid transporter.")
        elif not username or not password or not license_number:
            messages.error(request, "Username, password, and license number are required.")
        elif len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists. Choose a different username.")
        elif Driver.objects.filter(license_number__iexact=license_number).exists():
            messages.error(request, "License number already exists.")
        else:
            try:
                with transaction.atomic():
                    driver_user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        phone=phone,
                        role=User.Role.DRIVER,
                        is_active=is_active,
                    )
                    Driver.objects.create(
                        user=driver_user,
                        transporter=transporter,
                        license_number=license_number,
                        assigned_vehicle=assigned_vehicle,
                        is_active=is_active,
                    )
                messages.success(request, f"Driver '{username}' created successfully.")
                return redirect("admin_drivers")
            except (IntegrityError, ValidationError) as exc:
                messages.error(request, f"Unable to create driver: {exc}")

    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    salary_email_month = request.GET.get("salary_email_month", str(default_salary_email_month)).strip()
    salary_email_year = request.GET.get("salary_email_year", str(default_salary_email_year)).strip()

    drivers = Driver.objects.select_related(
        "user", "transporter", "assigned_vehicle"
    )

    if query:
        drivers = drivers.filter(
            Q(user__username__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(license_number__icontains=query)
            | Q(transporter__company_name__icontains=query)
        )

    if transporter_id.isdigit():
        drivers = drivers.filter(transporter_id=int(transporter_id))

    context = {
        "query": query,
        "drivers": drivers.order_by("user__username")[:400],
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "total_drivers": Driver.objects.count(),
        "active_drivers": Driver.objects.filter(is_active=True).count(),
        "all_vehicles": Vehicle.objects.select_related("transporter").order_by("vehicle_number"),
        "create_form": create_form,
        "salary_email_month": salary_email_month,
        "salary_email_year": salary_email_year,
    }
    return _render_admin(request, "admin/drivers.html", context)


@admin_required
def admin_attendance(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    mark_status_values = {choice[0] for choice in DriverDailyAttendanceMark.Status.choices}

    if request.method == "POST" and request.POST.get("form_action") == "force_absent":
        driver_id_raw = request.POST.get("driver_id", "").strip()
        mark_date_raw = request.POST.get("mark_date", "").strip()

        redirect_params = {
            "date": request.POST.get("date", "").strip() or today.isoformat(),
            "transporter_id": request.POST.get("transporter_id", "").strip(),
            "status": request.POST.get("status", "").strip(),
            "driver_id": driver_id_raw,
            "month": request.POST.get("month", "").strip(),
            "year": request.POST.get("year", "").strip(),
            "mark_date": mark_date_raw,
        }
        redirect_query = urlencode(
            {key: value for key, value in redirect_params.items() if value}
        )
        redirect_url = reverse("admin_attendance")
        if redirect_query:
            redirect_url = f"{redirect_url}?{redirect_query}"

        if not driver_id_raw.isdigit():
            messages.error(request, "Select a valid driver before forcing absent.")
            return redirect(redirect_url)

        target_driver = (
            Driver.objects.select_related("user", "transporter")
            .filter(id=int(driver_id_raw))
            .first()
        )
        if target_driver is None:
            messages.error(request, "Selected driver does not exist.")
            return redirect(redirect_url)

        try:
            mark_date = date.fromisoformat(mark_date_raw)
        except ValueError:
            messages.error(request, "Invalid attendance date.")
            return redirect(redirect_url)

        day_attendances = Attendance.objects.filter(
            driver=target_driver,
            date=mark_date,
        )
        day_trip_count = Trip.objects.filter(attendance__in=day_attendances).count()
        attendance_count = day_attendances.count()

        with transaction.atomic():
            if attendance_count:
                day_attendances.delete()

            existing_mark = DriverDailyAttendanceMark.objects.filter(
                driver=target_driver,
                transporter=target_driver.transporter,
                date=mark_date,
            ).first()
            previous_status = existing_mark.status if existing_mark is not None else None
            mark, _ = DriverDailyAttendanceMark.objects.update_or_create(
                driver=target_driver,
                transporter=target_driver.transporter,
                date=mark_date,
                defaults={
                    "status": DriverDailyAttendanceMark.Status.ABSENT,
                    "marked_by": request.user,
                },
            )

        if previous_status != mark.status:
            create_attendance_mark_updated_notification(
                mark=mark,
                previous_status=previous_status,
            )

        messages.success(
            request,
            (
                f"Forced absent for '{target_driver.user.username}' on "
                f"{mark_date.isoformat()}. Deleted {attendance_count} attendance record(s) "
                f"and {day_trip_count} trip record(s)."
            ),
        )
        return redirect(redirect_url)

    if request.method == "POST" and request.POST.get("form_action") == "mark_attendance":
        driver_id_raw = request.POST.get("driver_id", "").strip()
        mark_date_raw = request.POST.get("mark_date", "").strip()
        mark_status = request.POST.get("mark_status", "").strip()

        redirect_params = {
            "date": request.POST.get("date", "").strip() or today.isoformat(),
            "transporter_id": request.POST.get("transporter_id", "").strip(),
            "status": request.POST.get("status", "").strip(),
            "driver_id": driver_id_raw,
            "month": request.POST.get("month", "").strip(),
            "year": request.POST.get("year", "").strip(),
            "mark_date": mark_date_raw,
        }
        redirect_query = urlencode(
            {key: value for key, value in redirect_params.items() if value}
        )
        redirect_url = reverse("admin_attendance")
        if redirect_query:
            redirect_url = f"{redirect_url}?{redirect_query}"

        if not driver_id_raw.isdigit():
            messages.error(request, "Select a valid driver to mark attendance.")
            return redirect(redirect_url)

        target_driver = (
            Driver.objects.select_related("user", "transporter")
            .filter(id=int(driver_id_raw))
            .first()
        )
        if target_driver is None:
            messages.error(request, "Selected driver does not exist.")
            return redirect(redirect_url)

        try:
            mark_date = date.fromisoformat(mark_date_raw)
        except ValueError:
            messages.error(request, "Invalid attendance date.")
            return redirect(redirect_url)

        if mark_status not in mark_status_values:
            messages.error(request, "Invalid attendance status selected.")
            return redirect(redirect_url)

        if mark_status in {
            DriverDailyAttendanceMark.Status.ABSENT,
            DriverDailyAttendanceMark.Status.LEAVE,
        } and Attendance.objects.filter(driver=target_driver, date=mark_date).exists():
            messages.error(
                request,
                (
                    "Cannot mark absent/leave because the driver has already started "
                    "attendance for the selected date."
                ),
            )
            return redirect(redirect_url)

        existing_mark = DriverDailyAttendanceMark.objects.filter(
            driver=target_driver,
            transporter=target_driver.transporter,
            date=mark_date,
        ).first()
        previous_status = existing_mark.status if existing_mark is not None else None

        mark, _ = DriverDailyAttendanceMark.objects.update_or_create(
            driver=target_driver,
            transporter=target_driver.transporter,
            date=mark_date,
            defaults={
                "status": mark_status,
                "marked_by": request.user,
            },
        )

        if previous_status != mark.status:
            create_attendance_mark_updated_notification(
                mark=mark,
                previous_status=previous_status,
            )

        messages.success(
            request,
            (
                f"Attendance for '{target_driver.user.username}' on "
                f"{mark_date.isoformat()} marked as {mark.get_status_display()}."
            ),
        )
        return redirect(redirect_url)

    date_filter = _parse_date_param(request.GET.get("date"), today)
    transporter_id = request.GET.get("transporter_id", "").strip()
    status_filter = request.GET.get("status", "").strip()
    selected_driver_id = request.GET.get("driver_id", "").strip()
    month, year = _parse_month_year(request)
    mark_date = _parse_date_param(request.GET.get("mark_date"), date_filter)

    drivers_queryset = Driver.objects.select_related(
        "user",
        "transporter",
        "assigned_vehicle",
    ).order_by("user__username")
    if transporter_id.isdigit():
        drivers_queryset = drivers_queryset.filter(transporter_id=int(transporter_id))
    driver_options = list(drivers_queryset[:500])

    selected_driver = None
    if selected_driver_id.isdigit():
        selected_driver = next(
            (driver for driver in driver_options if driver.id == int(selected_driver_id)),
            None,
        )
    if selected_driver is None and driver_options:
        selected_driver = driver_options[0]
        selected_driver_id = str(selected_driver.id)

    attendances = Attendance.objects.select_related(
        "driver", "driver__user", "vehicle", "vehicle__transporter"
    ).prefetch_related("trips")

    attendances = attendances.filter(date=date_filter)

    if transporter_id.isdigit():
        attendances = attendances.filter(vehicle__transporter_id=int(transporter_id))

    if status_filter in {choice[0] for choice in Attendance.Status.choices}:
        attendances = attendances.filter(status=status_filter)
    if selected_driver_id.isdigit():
        attendances = attendances.filter(driver_id=int(selected_driver_id))

    attendance_rows = []
    for item in attendances.order_by("-started_at")[:500]:
        end_km = item.end_km if item.end_km is not None else item.start_km
        attendance_rows.append(
            {
                "attendance": item,
                "trips_count": item.trips.count(),
                "computed_total_km": max(end_km - item.start_km, 0),
            }
        )

    daily_marks = DriverDailyAttendanceMark.objects.select_related(
        "driver",
        "driver__user",
        "driver__transporter",
        "marked_by",
    ).filter(date=date_filter)
    if transporter_id.isdigit():
        daily_marks = daily_marks.filter(transporter_id=int(transporter_id))
    if selected_driver_id.isdigit():
        daily_marks = daily_marks.filter(driver_id=int(selected_driver_id))
    mark_rows = list(daily_marks.order_by("driver__user__username")[:500])

    calendar_days = []
    leading_blank_days: list[int] = []
    trailing_blank_days: list[int] = []
    calendar_month_label = ""
    calendar_totals = {
        "present_days": 0,
        "absent_days": 0,
        "no_duty_days": 0,
        "effective_present_days": 0,
    }
    if selected_driver is not None:
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        calendar_month_label = first_day.strftime("%B %Y")

        attendance_map = {
            item.date: item
            for item in Attendance.objects.filter(
                driver=selected_driver,
                date__gte=first_day,
                date__lte=last_day,
                vehicle__transporter_id=selected_driver.transporter_id,
            ).select_related("vehicle")
        }
        mark_map = {
            item.date: item
            for item in DriverDailyAttendanceMark.objects.filter(
                driver=selected_driver,
                transporter_id=selected_driver.transporter_id,
                date__gte=first_day,
                date__lte=last_day,
            )
        }

        total_days = (last_day - first_day).days + 1
        for day_offset in range(total_days):
            target_date = first_day + timedelta(days=day_offset)
            attendance = attendance_map.get(target_date)
            mark = mark_map.get(target_date)
            day_status = _resolve_admin_attendance_view_status(
                attendance=attendance,
                mark=mark,
                target_date=target_date,
                today=today,
                joined_date=selected_driver.joined_transporter_date,
            )

            if day_status == "PRESENT":
                calendar_totals["present_days"] += 1
            elif day_status in {"ABSENT", "LEAVE"}:
                calendar_totals["absent_days"] += 1
            elif day_status == "NO_DUTY":
                calendar_totals["no_duty_days"] += 1

            calendar_days.append(
                {
                    "date": target_date,
                    "day_number": target_date.day,
                    "status": day_status,
                    "status_label": day_status.replace("_", " ").title(),
                    "is_today": target_date == today,
                    "has_attendance": attendance is not None,
                    "has_mark": mark is not None,
                    "mark_status": mark.status if mark is not None else "",
                    "vehicle_number": (
                        attendance.vehicle.vehicle_number if attendance is not None else ""
                    ),
                    "service_name": attendance.service_name if attendance is not None else "",
                    "start_km": attendance.start_km if attendance is not None else None,
                    "end_km": attendance.end_km if attendance is not None else None,
                }
            )

        calendar_totals["effective_present_days"] = (
            calendar_totals["present_days"] + calendar_totals["no_duty_days"]
        )
        leading_blank_days = list(range(first_day.weekday()))
        remainder = (len(calendar_days) + len(leading_blank_days)) % 7
        trailing_blank_days = list(range((7 - remainder) % 7))

    month_options = [
        {"value": value, "label": date(2000, value, 1).strftime("%b")}
        for value in range(1, 13)
    ]
    year_options = [today.year - 2, today.year - 1, today.year, today.year + 1]

    context = {
        "date_filter": date_filter,
        "mark_date": mark_date,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "selected_status": status_filter,
        "driver_options": driver_options,
        "selected_driver": selected_driver,
        "selected_driver_id": selected_driver_id,
        "selected_month": month,
        "selected_year": year,
        "month_options": month_options,
        "year_options": year_options,
        "status_choices": Attendance.Status.choices,
        "mark_status_choices": DriverDailyAttendanceMark.Status.choices,
        "attendance_rows": attendance_rows,
        "mark_rows": mark_rows,
        "total_rows": len(attendance_rows),
        "total_marks": len(mark_rows),
        "calendar_days": calendar_days,
        "calendar_month_label": calendar_month_label,
        "calendar_totals": calendar_totals,
        "leading_blank_days": leading_blank_days,
        "trailing_blank_days": trailing_blank_days,
    }
    return _render_admin(request, "admin/attendance.html", context)


@admin_required
def admin_trips(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_filter = _parse_date_param(request.GET.get("date"), timezone.localdate())
    edit_id = request.GET.get("edit_id", "").strip()
    base_query_params = request.GET.copy()
    base_query_params.pop("edit_id", None)

    trips = Trip.objects.select_related(
        "attendance",
        "attendance__driver",
        "attendance__driver__user",
        "attendance__vehicle",
        "attendance__vehicle__transporter",
    )

    if query:
        trips = trips.filter(
            Q(start_location__icontains=query)
            | Q(destination__icontains=query)
            | Q(attendance__driver__user__username__icontains=query)
            | Q(attendance__vehicle__vehicle_number__icontains=query)
        )

    if transporter_id.isdigit():
        trips = trips.filter(attendance__vehicle__transporter_id=int(transporter_id))

    if request.GET.get("date"):
        trips = trips.filter(attendance__date=date_filter)

    trip_rows = list(trips.order_by("-created_at")[:500])
    edit_trip = None
    if edit_id.isdigit():
        edit_trip = next((item for item in trip_rows if item.id == int(edit_id)), None)
        if edit_trip is None:
            edit_trip = (
                Trip.objects.select_related(
                    "attendance",
                    "attendance__driver",
                    "attendance__driver__user",
                    "attendance__vehicle",
                    "attendance__vehicle__transporter",
                )
                .filter(id=int(edit_id))
                .first()
            )

    context = {
        "query": query,
        "date_filter": request.GET.get("date", ""),
        "trips": trip_rows,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "total_km": sum(item.total_km for item in trip_rows),
        "edit_trip": edit_trip,
        "base_query_string": base_query_params.urlencode(),
    }
    return _render_admin(request, "admin/trips.html", context)


@admin_required
def admin_update_trip_session(request: HttpRequest, trip_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_trips")

    trip = get_object_or_404(
        Trip.objects.select_related(
            "attendance",
            "attendance__driver",
            "attendance__driver__user",
            "attendance__vehicle",
        ),
        id=trip_id,
    )
    if not trip.is_day_trip or trip.parent_trip_id is not None:
        messages.error(
            request,
            "Admin KM override is supported only for master day sessions.",
        )
        return redirect(_safe_next_url(request, "/admin/trips/"))

    if trip.child_trips.filter(status=Trip.Status.OPEN).exists():
        messages.error(
            request,
            "Cannot force close the session while legacy child trips are still open.",
        )
        return redirect(_safe_next_url(request, "/admin/trips/"))

    start_km_raw = request.POST.get("start_km", "").strip()
    end_km_raw = request.POST.get("end_km", "").strip()
    if not start_km_raw.isdigit() or not end_km_raw.isdigit():
        messages.error(request, "Opening KM and closing KM must be numeric.")
        return redirect(_safe_next_url(request, "/admin/trips/"))

    start_km = int(start_km_raw)
    end_km = int(end_km_raw)
    if end_km < start_km:
        messages.error(
            request,
            "Closing KM must be greater than or equal to opening KM.",
        )
        return redirect(_safe_next_url(request, "/admin/trips/"))

    attendance = trip.attendance
    closing_time = attendance.ended_at or trip.ended_at or timezone.now()
    was_open = attendance.ended_at is None or trip.status == Trip.Status.OPEN

    with transaction.atomic():
        attendance.start_km = start_km
        attendance.end_km = end_km
        attendance.status = Attendance.Status.ON_DUTY
        if was_open:
            attendance.ended_at = closing_time
        attendance.save(
            update_fields=[
                "start_km",
                "end_km",
                "status",
                "ended_at",
            ]
        )

        trip.start_km = start_km
        trip.end_km = end_km
        trip.status = Trip.Status.CLOSED
        trip.ended_at = closing_time
        trip.save(
            update_fields=[
                "start_km",
                "end_km",
                "status",
                "ended_at",
            ]
        )

    action_label = "force-closed" if was_open else "updated"
    messages.success(
        request,
        (
            f"Session {action_label}: "
            f"{attendance.driver.user.username} | {attendance.vehicle.vehicle_number} | "
            f"{start_km} -> {end_km}"
        ),
    )
    return redirect(_safe_next_url(request, "/admin/trips/"))


@admin_required
def admin_delete_trip(request: HttpRequest, trip_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_trips")

    trip = get_object_or_404(
        Trip.objects.select_related(
            "attendance",
            "attendance__driver",
            "attendance__driver__user",
        ),
        id=trip_id,
    )

    if trip.is_day_trip and trip.parent_trip_id is None and trip.child_trips.exists():
        messages.error(
            request,
            (
                "Cannot delete master day trip while child trips exist. "
                "Delete child trips first."
            ),
        )
        return redirect(_safe_next_url(request, "/admin/trips/"))

    if trip.is_day_trip and trip.parent_trip_id is None and trip.status == Trip.Status.OPEN:
        messages.error(
            request,
            "Cannot delete an active open day trip. Force close it first from the admin session tool or from the driver flow.",
        )
        return redirect(_safe_next_url(request, "/admin/trips/"))

    attendance = trip.attendance
    trip_label = (
        f"{attendance.driver.user.username} | {attendance.date.isoformat()} | "
        f"{trip.start_location} -> {trip.destination}"
    )

    with transaction.atomic():
        trip.delete()
        if (
            attendance.ended_at is not None
            and attendance.status != Attendance.Status.NO_TRIP
            and not attendance.trips.filter(is_day_trip=False).exists()
        ):
            attendance.status = Attendance.Status.NO_TRIP
            attendance.save(update_fields=["status"])

    messages.success(request, f"Trip record deleted: {trip_label}.")
    return redirect(_safe_next_url(request, "/admin/trips/"))


@admin_required
def admin_fuel_records(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_filter = _parse_date_param(request.GET.get("date"), timezone.localdate())
    summary_month = date_filter.month
    summary_year = date_filter.year

    fuel_records = FuelRecord.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "attendance",
        "vehicle__transporter",
        "partner",
    ).filter(entry_type=FuelRecord.EntryType.VEHICLE_FILLING)

    if query:
        fuel_records = fuel_records.filter(
            Q(driver__user__username__icontains=query)
            | Q(vehicle__vehicle_number__icontains=query)
        )

    if transporter_id.isdigit():
        fuel_records = fuel_records.filter(vehicle__transporter_id=int(transporter_id))

    if request.GET.get("date"):
        fuel_records = fuel_records.filter(date=date_filter)

    rows = list(fuel_records.order_by("-date", "-created_at")[:500])
    total_amount = sum(float(item.amount) for item in rows)
    total_fuel_filled = sum(float(item.liters or 0) for item in rows)
    total_run_km = 0
    mileage_summary = _build_admin_fuel_mileage_summary(
        month=summary_month,
        year=summary_year,
        transporter_id=transporter_id,
    )
    fuel_balance_rows = _build_admin_fuel_balance_rows(
        transporter_id=transporter_id,
        fuel_records=rows,
    )
    summary_month_label = date(summary_year, summary_month, 1).strftime("%B %Y")

    context = {
        "query": query,
        "date_filter": request.GET.get("date", ""),
        "fuel_records": rows,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "total_amount": total_amount,
        "total_fuel_filled": total_fuel_filled,
        "total_run_km": total_run_km,
        "total_entries": len(rows),
        "mileage_summary": mileage_summary,
        "fuel_balance_rows": fuel_balance_rows,
        "summary_month_label": summary_month_label,
    }
    return _render_admin(request, "admin/fuel_records.html", context)


@admin_required
def admin_delete_fuel_record(request: HttpRequest, record_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_fuel_records")

    record = get_object_or_404(
        FuelRecord.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
        ),
        id=record_id,
    )
    if record.entry_type != FuelRecord.EntryType.VEHICLE_FILLING:
        messages.error(
            request,
            "Only vehicle fuel filling records can be deleted from this page.",
        )
        return redirect(_safe_next_url(request, "/admin/fuel-records/"))

    record_label = (
        f"{record.date.isoformat()} | {record.driver.user.username} | "
        f"{record.vehicle.vehicle_number}"
    )
    record.delete()
    messages.success(request, f"Fuel record deleted: {record_label}.")
    return redirect(_safe_next_url(request, "/admin/fuel-records/"))


@admin_required
def admin_fuel_record_photo(request: HttpRequest, record_id: int) -> HttpResponse:
    record = get_object_or_404(
        FuelRecord.objects.select_related("driver", "driver__user", "vehicle"),
        id=record_id,
    )
    image_file = record.meter_image or record.bill_image
    if not image_file:
        messages.error(request, "No vehicle fuel image is available for this record.")
        return redirect("admin_fuel_records")
    return FileResponse(image_file.open("rb"), content_type="image/jpeg")


def _build_admin_diesel_tripsheet_rows(rows: list[FuelRecord]) -> list[dict]:
    grouped: dict[tuple[date, int], dict] = {}
    for item in rows:
        row_date = item.fill_date or item.date
        key = (row_date, item.vehicle_id)
        start_value = item.start_km if item.start_km is not None else 0
        end_candidate = item.end_km if item.end_km is not None else start_value

        bucket = grouped.setdefault(
            key,
            {
                "date": row_date,
                "vehicle_number": item.vehicle.vehicle_number,
                "start_km": start_value,
                "end_km": end_candidate,
                "records": [],
            },
        )
        bucket["start_km"] = min(bucket["start_km"], start_value)
        bucket["end_km"] = max(bucket["end_km"], end_candidate)
        bucket["records"].append(item)

    sorted_groups = sorted(
        grouped.values(),
        key=lambda group: (group["date"], group["vehicle_number"]),
    )

    output_rows = []
    sl_no = 1
    for group in sorted_groups:
        run_km = max(group["end_km"] - group["start_km"], 0)
        output_rows.append(
            {
                "sl_no": sl_no,
                "date": group["date"],
                "start_km": group["start_km"],
                "end_km": group["end_km"],
                "run_km": run_km,
                "indus_site_id": "",
                "site_name": "",
                "fuel_filled": "",
                "purpose": "",
                "vehicle_number": group["vehicle_number"],
                "is_day_summary": True,
            }
        )
        sl_no += 1

        group_records = sorted(
            group["records"],
            key=lambda rec: (rec.created_at, rec.id),
        )
        for item in group_records:
            fuel_value = item.fuel_filled if item.fuel_filled is not None else item.liters
            output_rows.append(
                {
                    "sl_no": sl_no,
                    "date": item.fill_date or item.date,
                    "start_km": "",
                    "end_km": "",
                    "run_km": "",
                    "indus_site_id": (item.resolved_indus_site_id or "").strip(),
                    "site_name": (item.resolved_site_name or "").strip(),
                    "fuel_filled": f"{Decimal(fuel_value):.2f}" if fuel_value is not None else "",
                    "purpose": (item.purpose or "Diesel Filling").strip(),
                    "vehicle_number": item.vehicle.vehicle_number,
                    "is_day_summary": False,
                }
            )
            sl_no += 1

    return output_rows


def _build_diesel_tripsheet_pdf(
    *,
    date_from: date,
    date_to: date,
    selected_vehicle: Vehicle | None,
    rows: list[dict],
    total_days: int,
    total_fillings: int,
    total_run_km: int,
) -> bytes:
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

    title = "Diesel Service Trip Sheet"
    elements.append(Paragraph(title, styles["Title"]))
    vehicle_label = selected_vehicle.vehicle_number if selected_vehicle else "All Diesel Vehicles"
    elements.append(
        Paragraph(
            f"Vehicle: {vehicle_label} | Range: {date_from.isoformat()} to {date_to.isoformat()}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 3 * mm))

    table_data = [
        [
            "Sl No",
            "Date",
            "Vehicle",
            "Start KM",
            "End KM",
            "Run KM",
            "Site ID",
            "Site Name",
            "Filled Qty",
            "Purpose",
        ]
    ]
    for row in rows:
        row_date = row["date"]
        table_data.append(
            [
                str(row["sl_no"]),
                row_date.strftime("%d-%m-%Y") if hasattr(row_date, "strftime") else str(row_date),
                str(row["start_km"]),
                str(row["end_km"]),
                str(row["run_km"]),
                row["indus_site_id"],
                row["site_name"],
                row["fuel_filled"],
                row["purpose"],
            ]
        )

    table = Table(
        table_data,
        colWidths=[
            12 * mm,
            24 * mm,
            18 * mm,
            18 * mm,
            16 * mm,
            22 * mm,
            42 * mm,
            18 * mm,
            49 * mm,
        ],
        repeatRows=1,
    )

    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17395F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
        ("ALIGN", (0, 0), (4, -1), "CENTER"),
        ("ALIGN", (7, 1), (7, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    table_row_cursor = 1
    for row in rows:
        if row.get("is_day_summary"):
            table_styles.extend(
                [
                    ("BACKGROUND", (0, table_row_cursor), (-1, table_row_cursor), colors.HexColor("#EDF4FB")),
                    ("FONTNAME", (0, table_row_cursor), (4, table_row_cursor), "Helvetica-Bold"),
                ]
            )
        table_row_cursor += 1

    table.setStyle(TableStyle(table_styles))
    elements.append(table)
    elements.append(Spacer(1, 3 * mm))
    elements.append(
        Paragraph(
            f"Total Days: {total_days} | Total Fillings: {total_fillings} | Total Run KM: {total_run_km}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 8 * mm))

    signature_table = Table(
        [
            ["", "", "", ""],
            ["ENERGY MANAGET/ACCOUNTS", "IME MANAGER", "OM HEAD", "ZONAL HEAD"],
        ],
        colWidths=[68 * mm, 68 * mm, 68 * mm, 69 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor("#1A1A1A")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 8.2),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 1),
            ]
        )
    )
    elements.append(signature_table)
    document.build(elements)
    return buffer.getvalue()


@admin_required
def admin_diesel_tripsheet(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    default_date_from = today.replace(day=1)
    date_from = _parse_date_param(request.GET.get("date_from"), default_date_from)
    date_to = _parse_date_param(request.GET.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    vehicle_id_raw = request.GET.get("vehicle_id", "").strip()
    diesel_vehicles = Vehicle.objects.select_related("transporter").filter(
        vehicle_type=Vehicle.Type.DIESEL_SERVICE
    ).order_by("vehicle_number")

    selected_vehicle = None
    if vehicle_id_raw.isdigit():
        selected_vehicle = diesel_vehicles.filter(id=int(vehicle_id_raw)).first()
        if selected_vehicle is None:
            messages.error(request, "Selected diesel service vehicle does not exist.")
            return redirect("admin_diesel_tripsheet")

    records_qs = (
        FuelRecord.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
            "vehicle__transporter",
        )
        .filter(
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            vehicle__vehicle_type=Vehicle.Type.DIESEL_SERVICE,
            date__gte=date_from,
            date__lte=date_to,
        )
        .order_by("date", "vehicle__vehicle_number", "driver__user__username")
    )
    if selected_vehicle is not None:
        records_qs = records_qs.filter(vehicle=selected_vehicle)
    record_rows = list(records_qs)
    rows = _build_admin_diesel_tripsheet_rows(record_rows)
    total_days = sum(1 for row in rows if row["is_day_summary"])
    total_fillings = sum(1 for row in rows if not row["is_day_summary"])
    total_run_km = sum(
        int(row["run_km"])
        for row in rows
        if row["is_day_summary"] and row["run_km"] not in {"", None}
    )
    total_liters = sum(
        float(item.fuel_filled or item.liters or 0)
        for item in record_rows
    )

    if request.GET.get("download") == "pdf":
        if not REPORTLAB_AVAILABLE:
            messages.error(
                request,
                "PDF generation dependency missing. Install reportlab in server environment.",
            )
            return redirect("admin_diesel_tripsheet")

        pdf_bytes = _build_diesel_tripsheet_pdf(
            date_from=date_from,
            date_to=date_to,
            selected_vehicle=selected_vehicle,
            rows=rows,
            total_days=total_days,
            total_fillings=total_fillings,
            total_run_km=total_run_km,
        )
        vehicle_part = selected_vehicle.vehicle_number if selected_vehicle else "all"
        filename = (
            f"diesel-tripsheet-{vehicle_part}-"
            f"{date_from.isoformat()}-to-{date_to.isoformat()}.pdf"
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    context = {
        "diesel_vehicles": diesel_vehicles,
        "selected_vehicle_id": vehicle_id_raw,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "total_rows": len(rows),
        "total_days": total_days,
        "total_fillings": total_fillings,
        "total_liters": total_liters,
        "total_run_km": total_run_km,
        "selected_vehicle": selected_vehicle,
    }
    return _render_admin(request, "admin/diesel_tripsheet.html", context)


@admin_required
def admin_diesel_sites(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()
    date_input = request.GET.get("date", "").strip()
    edit_id = request.GET.get("edit_id", "").strip()
    manual_driver_id = request.GET.get("manual_driver_id", "").strip()
    manual_attendance_id = request.GET.get("manual_attendance_id", "").strip()
    return_to_name = request.POST.get("return_to", "").strip() or request.GET.get("return_to", "").strip()
    if return_to_name not in {"admin_diesel_sites", "admin_diesel_manual_entry"}:
        return_to_name = "admin_diesel_sites"

    def _parse_optional_decimal(value: str, field_label: str):
        if not value:
            return None
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValidationError(f"{field_label} must be a valid decimal value.") from exc

    def _resolve_or_create_tower_site(
        *,
        partner: Transporter,
        indus_site_id: str,
        site_name: str,
        latitude: Decimal | None,
        longitude: Decimal | None,
        confirm_site_name_update: bool = False,
        allow_blank_site_name_for_new: bool = False,
    ) -> tuple[object, bool]:
        try:
            normalized_site_id = validate_indus_site_id(indus_site_id)
        except ValidationError as exc:
            raise ValidationError(exc.messages[0]) from exc

        tower_site = (
            IndusTowerSite.objects.filter(
                partner=partner,
                indus_site_id__iexact=normalized_site_id,
            )
            .order_by("id")
            .first()
        )
        try:
            normalized_site_name = validate_site_name(
                site_name,
                required=tower_site is None and not allow_blank_site_name_for_new,
            )
        except ValidationError as exc:
            raise ValidationError(exc.messages[0]) from exc

        if tower_site is None:
            tower_site = IndusTowerSite.objects.create(
                partner=partner,
                indus_site_id=normalized_site_id,
                site_name=normalized_site_name,
                latitude=latitude,
                longitude=longitude,
            )
            return tower_site, True

        fields_to_update: list[str] = []
        try:
            ensure_site_name_update_confirmed(
                site_id=normalized_site_id,
                existing_name=tower_site.site_name,
                submitted_name=normalized_site_name,
                confirmed=confirm_site_name_update,
            )
        except SiteNameUpdateConfirmationRequired as exc:
            raise ValidationError(exc.messages[0]) from exc
        if normalized_site_name and tower_site.site_name != normalized_site_name:
            tower_site.site_name = normalized_site_name
            fields_to_update.append("site_name")
        if latitude is not None and tower_site.latitude != latitude:
            tower_site.latitude = latitude
            fields_to_update.append("latitude")
        if longitude is not None and tower_site.longitude != longitude:
            tower_site.longitude = longitude
            fields_to_update.append("longitude")
        if fields_to_update:
            fields_to_update.append("updated_at")
            tower_site.save(update_fields=fields_to_update)
        return tower_site, False

    def _manual_redirect_url(
        *,
        target_transporter_id: int | None = None,
        target_date: date | None = None,
        target_attendance_id: int | None = None,
        target_driver_id: int | None = None,
    ) -> str:
        params = {}
        if query:
            params["q"] = query
        if target_transporter_id is not None:
            params["transporter_id"] = str(target_transporter_id)
        elif transporter_id:
            params["transporter_id"] = transporter_id
        if vehicle_id:
            params["vehicle_id"] = vehicle_id
        if target_date is not None:
            params["date"] = target_date.isoformat()
        elif date_input:
            params["date"] = date_input
        if target_attendance_id is not None:
            params["manual_attendance_id"] = str(target_attendance_id)
        if target_driver_id is not None:
            params["manual_driver_id"] = str(target_driver_id)
        encoded = urlencode(params)
        base_url = reverse(return_to_name)
        return f"{base_url}?{encoded}" if encoded else base_url

    def _create_or_update_manual_day_trip(
        *,
        driver: Driver,
        vehicle: Vehicle,
        service: TransportService,
        target_date: date,
        start_km: int,
        end_km: int,
    ) -> Attendance:
        if end_km < start_km:
            raise ValidationError("Closing KM must be greater than or equal to opening KM.")
        if driver.transporter_id != vehicle.transporter_id:
            raise ValidationError("Driver and vehicle must belong to the same transporter.")
        if driver.transporter_id != service.transporter_id:
            raise ValidationError("Selected service must belong to the same transporter.")

        attendance = (
            Attendance.objects.select_related("service")
            .filter(
                driver=driver,
                date=target_date,
                vehicle=vehicle,
                service=service,
            )
            .order_by("-started_at", "-id")
            .first()
        )
        if attendance is not None and attendance.trips.filter(is_day_trip=False).exists():
            raise ValidationError(
                (
                    "This day record already has child trips. "
                    "Use the trips page for that service record."
                )
            )

        now = timezone.now()
        if attendance is None:
            attendance = Attendance.objects.create(
                driver=driver,
                vehicle=vehicle,
                date=target_date,
                status=Attendance.Status.ON_DUTY,
                service=service,
                service_name=service.name,
                service_purpose="Admin manual tower diesel backfill",
                start_km=start_km,
                end_km=end_km,
                odo_start_image=_admin_placeholder_odo_image(
                    f"{driver.id}-{vehicle.id}-{target_date.isoformat()}"
                ),
                latitude=Decimal("0.000000"),
                longitude=Decimal("0.000000"),
                started_at=now,
                ended_at=now,
            )
        else:
            fields_to_update = [
                "vehicle",
                "service",
                "service_name",
                "service_purpose",
                "start_km",
                "end_km",
                "status",
                "ended_at",
            ]
            attendance.vehicle = vehicle
            attendance.service = service
            attendance.service_name = service.name
            attendance.service_purpose = "Admin manual tower diesel backfill"
            attendance.start_km = start_km
            attendance.end_km = end_km
            attendance.status = Attendance.Status.ON_DUTY
            attendance.ended_at = now
            if not attendance.odo_start_image:
                attendance.odo_start_image = _admin_placeholder_odo_image(
                    f"{driver.id}-{vehicle.id}-{target_date.isoformat()}"
                )
                fields_to_update.append("odo_start_image")
            attendance.save(update_fields=fields_to_update)

        DriverDailyAttendanceMark.objects.update_or_create(
            driver=driver,
            transporter=driver.transporter,
            date=target_date,
            defaults={
                "status": DriverDailyAttendanceMark.Status.PRESENT,
                "marked_by": request.user,
            },
        )

        master_trip = (
            attendance.trips.filter(
                is_day_trip=True,
                parent_trip__isnull=True,
            )
            .order_by("-started_at", "-id")
            .first()
        )
        master_purpose = f"Admin manual day entry: {service.name}"
        if master_trip is None:
            Trip.objects.create(
                attendance=attendance,
                parent_trip=None,
                start_location="Day Start",
                destination="Day End",
                start_km=start_km,
                end_km=end_km,
                purpose=master_purpose,
                start_odo_image=attendance.odo_start_image,
                status=Trip.Status.CLOSED,
                is_day_trip=True,
                started_at=attendance.started_at,
                ended_at=attendance.ended_at or now,
            )
        else:
            master_trip.start_location = "Day Start"
            master_trip.destination = "Day End"
            master_trip.start_km = start_km
            master_trip.end_km = end_km
            master_trip.purpose = master_purpose
            if not master_trip.start_odo_image:
                master_trip.start_odo_image = attendance.odo_start_image
            master_trip.status = Trip.Status.CLOSED
            master_trip.started_at = attendance.started_at
            master_trip.ended_at = attendance.ended_at or now
            master_trip.save()

        return attendance

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).select_related("user").first()
        if transporter_id.isdigit()
        else None
    )

    if request.method == "POST":
        action = request.POST.get("form_action", "").strip()
        next_url = _safe_next_url(request, "/admin/diesel-sites/")

        if action == "prepare_manual_day_record":
            form_transporter_id = request.POST.get("transporter_id", "").strip() or transporter_id
            driver_id_raw = request.POST.get("driver_id", "").strip()
            vehicle_id_raw = request.POST.get("vehicle_id", "").strip()
            service_id_raw = request.POST.get("service_id", "").strip()
            trip_date_raw = request.POST.get("trip_date", "").strip()
            start_km_raw = request.POST.get("start_km", "").strip()
            end_km_raw = request.POST.get("end_km", "").strip()

            if not form_transporter_id.isdigit():
                messages.error(request, "Select a transporter first.")
                return redirect(next_url)
            if not all(
                value.isdigit()
                for value in [driver_id_raw, vehicle_id_raw, service_id_raw, start_km_raw, end_km_raw]
            ):
                messages.error(
                    request,
                    "Driver, vehicle, service, opening KM and closing KM are required.",
                )
                return redirect(
                    _manual_redirect_url(target_transporter_id=int(form_transporter_id))
                )
            try:
                target_date = date.fromisoformat(trip_date_raw)
            except ValueError:
                messages.error(request, "Trip date must be in YYYY-MM-DD format.")
                return redirect(
                    _manual_redirect_url(target_transporter_id=int(form_transporter_id))
                )

            transporter = get_object_or_404(Transporter, id=int(form_transporter_id))
            driver = get_object_or_404(
                Driver.objects.select_related("user", "transporter"),
                id=int(driver_id_raw),
                transporter=transporter,
            )
            vehicle = get_object_or_404(
                Vehicle.objects.select_related("transporter"),
                id=int(vehicle_id_raw),
                transporter=transporter,
                vehicle_type=Vehicle.Type.DIESEL_SERVICE,
            )
            service = get_object_or_404(
                TransportService.objects.filter(
                    id=int(service_id_raw),
                    transporter=transporter,
                )
            )

            try:
                attendance = _create_or_update_manual_day_trip(
                    driver=driver,
                    vehicle=vehicle,
                    service=service,
                    target_date=target_date,
                    start_km=int(start_km_raw),
                    end_km=int(end_km_raw),
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(
                    _manual_redirect_url(
                        target_transporter_id=transporter.id,
                        target_date=target_date,
                        target_driver_id=driver.id,
                    )
                )

            messages.success(
                request,
                (
                    f"Prepared day trip for {driver.user.username} on "
                    f"{target_date.isoformat()} with {vehicle.vehicle_number}."
                ),
            )
            return redirect(
                _manual_redirect_url(
                    target_transporter_id=transporter.id,
                    target_date=target_date,
                    target_attendance_id=attendance.id,
                    target_driver_id=driver.id,
                )
            )

        if action == "update_site_record":
            record_id_raw = request.POST.get("record_id", "").strip()
            if not record_id_raw.isdigit():
                messages.error(request, "Invalid diesel record selected for update.")
                return redirect(next_url)

            record = get_object_or_404(
                FuelRecord.objects.select_related("driver", "driver__user", "vehicle", "tower_site"),
                id=int(record_id_raw),
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            )

            indus_site_id = request.POST.get("indus_site_id", "").strip()
            site_name = request.POST.get("site_name", "").strip()
            purpose = request.POST.get("purpose", "").strip() or "Diesel Filling"
            tower_latitude_raw = request.POST.get("tower_latitude", "").strip()
            tower_longitude_raw = request.POST.get("tower_longitude", "").strip()
            confirm_site_name_update = (
                request.POST.get("confirm_site_name_update", "").strip().lower()
                in {"1", "true", "yes", "on"}
            )

            try:
                tower_latitude = _parse_optional_decimal(tower_latitude_raw, "Latitude")
                tower_longitude = _parse_optional_decimal(tower_longitude_raw, "Longitude")
                partner = record.partner or record.driver.transporter
                tower_site, created = _resolve_or_create_tower_site(
                    partner=partner,
                    indus_site_id=indus_site_id,
                    site_name=site_name,
                    latitude=tower_latitude,
                    longitude=tower_longitude,
                    confirm_site_name_update=confirm_site_name_update,
                    allow_blank_site_name_for_new=True,
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(next_url)

            record.tower_site = tower_site
            record.purpose = purpose
            # Legacy columns are cleared for new normalized model usage.
            record.indus_site_id = ""
            record.site_name = ""
            record.tower_latitude = None
            record.tower_longitude = None
            record.save(
                update_fields=[
                    "tower_site",
                    "purpose",
                    "indus_site_id",
                    "site_name",
                    "tower_latitude",
                    "tower_longitude",
                ]
            )
            messages.success(
                request,
                (
                    f"Updated record #{record.id} and "
                    f"{'created' if created else 'linked'} site {tower_site.indus_site_id}."
                ),
            )
            return redirect(next_url)

        if action == "create_manual_record":
            attendance_id_raw = request.POST.get("attendance_id", "").strip()
            indus_site_id = request.POST.get("indus_site_id", "").strip()
            site_name = request.POST.get("site_name", "").strip()
            purpose = request.POST.get("purpose", "").strip() or "Diesel Filling"
            fuel_filled_raw = request.POST.get("fuel_filled", "").strip()
            manual_photo = request.FILES.get("logbook_photo")
            confirm_site_name_update = (
                request.POST.get("confirm_site_name_update", "").strip().lower()
                in {"1", "true", "yes", "on"}
            )

            if not attendance_id_raw.isdigit():
                messages.error(request, "Prepare or select a day trip first.")
                return redirect(next_url)
            if not indus_site_id:
                messages.error(request, "Site ID is required.")
                return redirect(next_url)

            try:
                fuel_filled = Decimal(fuel_filled_raw)
            except InvalidOperation:
                messages.error(request, "Filled quantity must be a valid number.")
                return redirect(next_url)
            if fuel_filled <= 0:
                messages.error(request, "Filled quantity must be greater than zero.")
                return redirect(next_url)
            if fuel_filled.as_tuple().exponent < -2:
                messages.error(request, "Filled quantity can have at most 2 decimal places.")
                return redirect(next_url)

            attendance = get_object_or_404(
                Attendance.objects.select_related(
                    "driver",
                    "driver__user",
                    "driver__transporter",
                    "vehicle",
                    "service",
                ),
                id=int(attendance_id_raw),
            )
            if attendance.driver.transporter_id is None:
                messages.error(
                    request,
                    "Selected attendance is not linked to a transporter.",
                )
                return redirect(next_url)
            if attendance.end_km is None:
                messages.error(
                    request,
                    "Prepared day trip must include a closing KM before adding filling data.",
                )
                return redirect(next_url)

            try:
                tower_site, created = _resolve_or_create_tower_site(
                    partner=attendance.driver.transporter,
                    indus_site_id=indus_site_id,
                    site_name=site_name,
                    latitude=None,
                    longitude=None,
                    confirm_site_name_update=confirm_site_name_update,
                    allow_blank_site_name_for_new=True,
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(next_url)

            resolved_start_km = attendance.start_km
            resolved_end_km = max(attendance.end_km or attendance.start_km, resolved_start_km)

            try:
                record = FuelRecord.objects.create(
                    attendance=attendance,
                    driver=attendance.driver,
                    vehicle=attendance.vehicle,
                    partner=attendance.driver.transporter,
                    entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                    liters=fuel_filled,
                    fuel_filled=fuel_filled,
                    amount=Decimal("0.00"),
                    odometer_km=resolved_end_km,
                    tower_site=tower_site,
                    indus_site_id="",
                    site_name="",
                    purpose=purpose,
                    start_km=resolved_start_km,
                    end_km=resolved_end_km,
                    tower_latitude=None,
                    tower_longitude=None,
                    fill_date=attendance.date,
                    date=attendance.date,
                    logbook_photo=manual_photo,
                    ocr_raw_text="",
                    ocr_confidence=None,
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(next_url)

            messages.success(
                request,
                (
                    f"Manual tower diesel entry #{record.id} saved "
                    f"for {attendance.driver.user.username} ({tower_site.indus_site_id}). "
                    f"{'Created new site.' if created else 'Linked existing site.'}"
                ),
            )
            return redirect(
                _manual_redirect_url(
                    target_transporter_id=attendance.driver.transporter_id,
                    target_date=attendance.date,
                    target_attendance_id=attendance.id,
                    target_driver_id=attendance.driver_id,
                )
            )

        if action == "delete_site_record":
            record_id_raw = request.POST.get("record_id", "").strip()
            if not record_id_raw.isdigit():
                messages.error(request, "Invalid diesel record selected for delete.")
                return redirect(next_url)

            record = get_object_or_404(
                FuelRecord.objects.select_related("vehicle", "tower_site"),
                id=int(record_id_raw),
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            )
            resolved_site_id = (record.resolved_indus_site_id or "-").strip()
            resolved_site_name = (record.resolved_site_name or "-").strip()
            summary = (
                f"{(record.fill_date or record.date).isoformat()} | "
                f"{record.vehicle.vehicle_number} | "
                f"{resolved_site_id} {resolved_site_name}"
            )
            record.delete()
            messages.success(request, f"Diesel site record deleted: {summary}.")
            return redirect(next_url)

    records_qs = (
        FuelRecord.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
            "vehicle__transporter",
            "tower_site",
        )
        .filter(entry_type=FuelRecord.EntryType.TOWER_DIESEL)
        .order_by("-fill_date", "-created_at")
    )

    if query:
        records_qs = records_qs.filter(
            Q(indus_site_id__icontains=query)
            | Q(site_name__icontains=query)
            | Q(tower_site__indus_site_id__icontains=query)
            | Q(tower_site__site_name__icontains=query)
            | Q(purpose__icontains=query)
            | Q(driver__user__username__icontains=query)
            | Q(vehicle__vehicle_number__icontains=query)
        )

    if transporter_id.isdigit():
        records_qs = records_qs.filter(vehicle__transporter_id=int(transporter_id))

    diesel_vehicles = Vehicle.objects.select_related("transporter").filter(
        vehicle_type=Vehicle.Type.DIESEL_SERVICE
    ).order_by("vehicle_number")
    if transporter_id.isdigit():
        diesel_vehicles = diesel_vehicles.filter(transporter_id=int(transporter_id))

    if vehicle_id.isdigit():
        records_qs = records_qs.filter(vehicle_id=int(vehicle_id))

    if date_input:
        target_date = _parse_date_param(date_input, timezone.localdate())
        records_qs = records_qs.filter(fill_date=target_date)

    rows = list(records_qs[:500])

    edit_record = None
    if edit_id.isdigit():
        edit_record = next((item for item in rows if item.id == int(edit_id)), None)
        if edit_record is None:
            edit_record = (
                FuelRecord.objects.select_related("driver", "driver__user", "vehicle")
                .filter(
                    id=int(edit_id),
                    entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                )
                .first()
            )

    unique_site_keys = {
        (
            (item.resolved_indus_site_id or "").strip().upper(),
            (item.resolved_site_name or "").strip().lower(),
        )
        for item in rows
        if (item.resolved_indus_site_id or "").strip() or (item.resolved_site_name or "").strip()
    }

    drivers = Driver.objects.select_related("user", "transporter").order_by("user__username")
    services = TransportService.objects.select_related("transporter").order_by("name")
    if transporter_id.isdigit():
        drivers = drivers.filter(transporter_id=int(transporter_id))
        services = services.filter(transporter_id=int(transporter_id))
    else:
        drivers = drivers.none()
        services = services.none()

    prepared_attendances = (
        Attendance.objects.select_related(
            "driver",
            "driver__user",
            "vehicle",
            "service",
        )
        .filter(
            Q(vehicle__vehicle_type=Vehicle.Type.DIESEL_SERVICE)
            | Q(service__name__iexact="Diesel Filling Vehicle")
            | Q(service_name__iexact="Diesel Filling Vehicle")
        )
        .order_by("-date", "-started_at", "-id")
    )
    if transporter_id.isdigit():
        prepared_attendances = prepared_attendances.filter(
            vehicle__transporter_id=int(transporter_id)
        )
    else:
        prepared_attendances = prepared_attendances.none()
    if date_input:
        prepared_attendances = prepared_attendances.filter(
            date=_parse_date_param(date_input, timezone.localdate())
        )

    context = {
        "query": query,
        "date_input": date_input,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id,
        "diesel_vehicles": diesel_vehicles,
        "selected_vehicle_id": vehicle_id,
        "drivers": drivers[:400],
        "services": services[:200],
        "manual_driver_id": manual_driver_id,
        "manual_attendance_id": manual_attendance_id,
        "prepared_attendances": prepared_attendances[:120],
        "rows": rows,
        "edit_record": edit_record,
        "total_rows": len(rows),
        "unique_sites_count": len(unique_site_keys),
        "total_filled_qty": sum(float(item.fuel_filled or item.liters or 0) for item in rows),
    }
    return _render_admin(request, "admin/diesel_sites.html", context)


@admin_required
def admin_diesel_manual_entry(request: HttpRequest) -> HttpResponse:
    context = _build_admin_diesel_manual_context(request)
    return _render_admin(request, "admin/diesel_manual_entry.html", context)


@admin_required
def admin_diesel_site_lookup(request: HttpRequest) -> JsonResponse:
    transporter_id = request.GET.get("transporter_id", "").strip()
    site_id_raw = request.GET.get("indus_site_id", "").strip()

    if not transporter_id.isdigit():
        return JsonResponse({"detail": "Select a transporter first."}, status=400)

    try:
        site_id = validate_indus_site_id(site_id_raw)
    except ValidationError as exc:
        return JsonResponse({"detail": exc.messages[0]}, status=400)

    transporter = get_object_or_404(Transporter, id=int(transporter_id))
    site = (
        IndusTowerSite.objects.filter(
            partner=transporter,
            indus_site_id__iexact=site_id,
        )
        .order_by("id")
        .first()
    )
    if site is None:
        return JsonResponse(
            {
                "found": False,
                "indus_site_id": site_id,
                "site_name": "",
            },
            status=404,
        )

    return JsonResponse(
        {
            "found": True,
            "indus_site_id": site.indus_site_id,
            "site_name": site.site_name,
            "latitude": float(site.latitude) if site.latitude is not None else None,
            "longitude": float(site.longitude) if site.longitude is not None else None,
        }
    )


@admin_required
def admin_manual_vehicle_trip_entry(request: HttpRequest) -> HttpResponse:
    def _manual_trip_redirect_url(
        *,
        target_transporter_id: int | None = None,
        target_date: date | None = None,
        target_edit_attendance_id: int | None = None,
    ) -> str:
        params = {}
        if target_transporter_id is not None:
            params["transporter_id"] = str(target_transporter_id)
        if target_date is not None:
            params["date"] = target_date.isoformat()
        if target_edit_attendance_id is not None:
            params["edit_attendance_id"] = str(target_edit_attendance_id)
        encoded = urlencode(params)
        base_url = reverse("admin_manual_vehicle_trip_entry")
        return f"{base_url}?{encoded}" if encoded else base_url

    if request.method == "POST":
        action = request.POST.get("form_action", "").strip()
        if action == "save_manual_vehicle_trip":
            transporter_id_raw = request.POST.get("transporter_id", "").strip()
            attendance_id_raw = request.POST.get("attendance_id", "").strip()
            driver_id_raw = request.POST.get("driver_id", "").strip()
            vehicle_id_raw = request.POST.get("vehicle_id", "").strip()
            service_id_raw = request.POST.get("service_id", "").strip()
            trip_date_raw = request.POST.get("trip_date", "").strip()
            start_km_raw = request.POST.get("start_km", "").strip()
            end_km_raw = request.POST.get("end_km", "").strip()
            service_purpose = (
                request.POST.get("service_purpose", "").strip()
                or "Admin manual vehicle day update"
            )
            start_odo_image = request.FILES.get("start_odo_image")
            end_odo_image = request.FILES.get("end_odo_image")

            if not transporter_id_raw.isdigit():
                messages.error(request, "Select a transporter first.")
                return redirect("admin_manual_vehicle_trip_entry")
            if not all(
                value.isdigit()
                for value in [driver_id_raw, vehicle_id_raw, service_id_raw, start_km_raw, end_km_raw]
            ):
                messages.error(
                    request,
                    "Driver, vehicle, service, opening KM, and closing KM are required.",
                )
                return redirect(
                    _manual_trip_redirect_url(
                        target_transporter_id=int(transporter_id_raw)
                    )
                )
            try:
                target_date = date.fromisoformat(trip_date_raw)
            except ValueError:
                messages.error(request, "Trip date must be in YYYY-MM-DD format.")
                return redirect(
                    _manual_trip_redirect_url(
                        target_transporter_id=int(transporter_id_raw)
                    )
                )

            transporter = get_object_or_404(Transporter, id=int(transporter_id_raw))
            existing_attendance = None
            if attendance_id_raw:
                if not attendance_id_raw.isdigit():
                    messages.error(request, "Invalid day trip selected for update.")
                    return redirect(
                        _manual_trip_redirect_url(
                            target_transporter_id=transporter.id,
                            target_date=target_date,
                        )
                    )
                existing_attendance = get_object_or_404(
                    Attendance.objects.select_related(
                        "driver",
                        "driver__user",
                        "vehicle",
                        "service",
                    ),
                    id=int(attendance_id_raw),
                    vehicle__transporter=transporter,
                )

            driver = get_object_or_404(
                Driver.objects.select_related("user", "transporter"),
                id=int(driver_id_raw),
                transporter=transporter,
            )
            vehicle = get_object_or_404(
                Vehicle.objects.select_related("transporter"),
                id=int(vehicle_id_raw),
                transporter=transporter,
            )
            service = get_object_or_404(
                TransportService.objects.select_related("transporter"),
                id=int(service_id_raw),
                transporter=transporter,
            )

            try:
                attendance = _create_or_update_admin_day_trip(
                    driver=driver,
                    vehicle=vehicle,
                    service=service,
                    target_date=target_date,
                    start_km=int(start_km_raw),
                    end_km=int(end_km_raw),
                    service_purpose=service_purpose,
                    master_purpose=service_purpose or f"Admin manual day entry: {service.name}",
                    marked_by=request.user,
                    start_odo_image=start_odo_image,
                    end_odo_image=end_odo_image,
                    existing_attendance=existing_attendance,
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect(
                    _manual_trip_redirect_url(
                        target_transporter_id=transporter.id,
                        target_date=target_date,
                        target_edit_attendance_id=(
                            int(attendance_id_raw) if attendance_id_raw.isdigit() else None
                        ),
                    )
                )

            messages.success(
                request,
                (
                    f"Manual day trip saved for {driver.user.username} on "
                    f"{target_date.isoformat()} with {vehicle.vehicle_number}."
                ),
            )
            return redirect(
                _manual_trip_redirect_url(
                    target_transporter_id=transporter.id,
                    target_date=target_date,
                    target_edit_attendance_id=attendance.id,
                )
            )

    context = _build_admin_manual_vehicle_trip_context(request)
    return _render_admin(request, "admin/manual_vehicle_trip_entry.html", context)


@admin_required
def admin_monthly_reports(request: HttpRequest) -> HttpResponse:
    month, year = _parse_month_year(request)
    transporter_id = request.GET.get("transporter_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()
    service_id = request.GET.get("service_id", "").strip()
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    attendances = Attendance.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "vehicle__transporter",
        "service",
    ).prefetch_related(
        Prefetch(
            "trips",
            queryset=Trip.objects.filter(
                is_day_trip=False,
                end_km__isnull=False,
            ).only("id", "end_km", "attendance_id"),
            to_attr="_prefetched_closed_child_trips",
        )
    ).filter(date__month=month, date__year=year)

    if transporter_id.isdigit():
        attendances = attendances.filter(vehicle__transporter_id=int(transporter_id))

    if vehicle_id.isdigit():
        attendances = attendances.filter(vehicle_id=int(vehicle_id))

    if service_id.isdigit():
        attendances = attendances.filter(service_id=int(service_id))

    def _resolve_closing_km(attendance: Attendance) -> int:
        candidates = [attendance.start_km]
        if attendance.end_km is not None:
            candidates.append(attendance.end_km)
        for trip in getattr(attendance, "_prefetched_closed_child_trips", []):
            if trip.end_km is not None:
                candidates.append(trip.end_km)
        return max(candidates)

    grouped_rows: dict[tuple, dict] = {}
    for item in attendances.order_by(
        "date",
        "vehicle__vehicle_number",
        "service_name",
        "started_at",
    ):
        end_km = _resolve_closing_km(item)
        service_name = item.service_name or (item.service.name if item.service else "-")
        purpose = (item.service_purpose or "").strip()
        key = (
            item.date,
            item.vehicle.transporter.company_name,
            item.vehicle.vehicle_number,
            item.service_id,
            service_name,
        )
        bucket = grouped_rows.setdefault(
            key,
            {
                "date": item.date,
                "transporter_name": item.vehicle.transporter.company_name,
                "vehicle_number": item.vehicle.vehicle_number,
                "driver_names": set(),
                "service_name": service_name,
                "start_km": item.start_km,
                "end_km": end_km,
                "purposes": set(),
                "runs_count": 0,
            },
        )
        bucket["driver_names"].add(item.driver.user.username)
        bucket["start_km"] = min(bucket["start_km"], item.start_km)
        bucket["end_km"] = max(bucket["end_km"], end_km)
        if purpose:
            bucket["purposes"].add(purpose)
        bucket["runs_count"] += 1

    rows = []
    total_km = 0
    for bucket in grouped_rows.values():
        distance = max(bucket["end_km"] - bucket["start_km"], 0)
        total_km += distance
        rows.append(
            {
                "date": bucket["date"],
                "transporter_name": bucket["transporter_name"],
                "vehicle_number": bucket["vehicle_number"],
                "driver_name": ", ".join(sorted(bucket["driver_names"])),
                "service_name": bucket["service_name"],
                "start_km": bucket["start_km"],
                "end_km": bucket["end_km"],
                "total_km": distance,
                "purpose": " | ".join(sorted(bucket["purposes"])) if bucket["purposes"] else "-",
                "runs_count": bucket["runs_count"],
            }
        )
    rows.sort(
        key=lambda row: (
            row["date"],
            row["vehicle_number"],
            row["service_name"],
            row["driver_name"],
        )
    )

    summary_map: dict[str, dict] = {}
    for row in rows:
        bucket = summary_map.setdefault(
            row["vehicle_number"],
            {
                "vehicle_number": row["vehicle_number"],
                "days": 0,
                "total_km": 0,
                "transporter_name": row["transporter_name"],
            },
        )
        bucket["days"] += 1
        bucket["total_km"] += row["total_km"]

    service_summary_map: dict[str, dict] = {}
    for row in rows:
        service_key = row["service_name"] or "Unspecified Service"
        bucket = service_summary_map.setdefault(
            service_key,
            {
                "service_name": service_key,
                "days": 0,
                "total_km": 0,
                "vehicles": set(),
            },
        )
        bucket["days"] += 1
        bucket["total_km"] += row["total_km"]
        bucket["vehicles"].add(row["vehicle_number"])

    service_summary_rows = sorted(
        [
            {
                "service_name": item["service_name"],
                "days": item["days"],
                "total_km": item["total_km"],
                "vehicles_count": len(item["vehicles"]),
            }
            for item in service_summary_map.values()
        ],
        key=lambda row: (row["service_name"], row["total_km"]),
    )

    vehicle_rows = sorted(summary_map.values(), key=lambda row: row["vehicle_number"])
    vehicles_qs = Vehicle.objects.select_related("transporter").order_by("vehicle_number")
    services_qs = TransportService.objects.select_related("transporter").order_by("name")
    if transporter_id.isdigit():
        vehicles_qs = vehicles_qs.filter(transporter_id=int(transporter_id))
        services_qs = services_qs.filter(transporter_id=int(transporter_id))

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).first()
        if transporter_id.isdigit()
        else None
    )

    diesel_records = FuelRecord.objects.filter(
        entry_type=FuelRecord.EntryType.TOWER_DIESEL,
        fill_date__gte=first_day,
        fill_date__lte=last_day,
    )
    if transporter_id.isdigit():
        diesel_records = diesel_records.filter(vehicle__transporter_id=int(transporter_id))
    if vehicle_id.isdigit():
        diesel_records = diesel_records.filter(vehicle_id=int(vehicle_id))
    diesel_record_count = diesel_records.count()
    diesel_pdf_query = {
        "month": month,
        "year": year,
        **({"transporter_id": transporter_id} if transporter_id else {}),
        **({"vehicle_id": vehicle_id} if vehicle_id else {}),
    }

    context = {
        "month": month,
        "year": year,
        "selected_transporter_id": transporter_id,
        "selected_vehicle_id": vehicle_id,
        "selected_service_id": service_id,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "vehicles": vehicles_qs,
        "services": services_qs,
        "rows": rows,
        "total_days": len(rows),
        "total_km": total_km,
        "summary_rows": vehicle_rows,
        "service_summary_rows": service_summary_rows,
        "diesel_record_count": diesel_record_count,
        "diesel_pdf_url": (
            f"{reverse('admin_monthly_diesel_pdf')}?{urlencode(diesel_pdf_query)}"
            if diesel_record_count
            else ""
        ),
        "month_label": first_day.strftime("%B %Y"),
    }
    return _render_admin(request, "admin/monthly_reports.html", context)


@admin_required
def admin_monthly_diesel_pdf(request: HttpRequest) -> HttpResponse:
    if not REPORTLAB_AVAILABLE:
        return HttpResponse(
            "PDF dependency missing. Install reportlab on server.",
            status=500,
            content_type="text/plain",
        )

    month, year = _parse_month_year(request)
    transporter_id = request.GET.get("transporter_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    queryset = FuelRecord.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "attendance",
        "partner",
        "tower_site",
    ).filter(
        entry_type=FuelRecord.EntryType.TOWER_DIESEL,
        fill_date__gte=first_day,
        fill_date__lte=last_day,
    )
    if transporter_id.isdigit():
        queryset = queryset.filter(vehicle__transporter_id=int(transporter_id))
    if vehicle_id.isdigit():
        queryset = queryset.filter(vehicle_id=int(vehicle_id))

    queryset = queryset.order_by("fill_date", "vehicle__vehicle_number", "created_at")
    rows = _build_diesel_tripsheet_rows(queryset)
    total_days = sum(1 for item in rows if item["is_day_summary"])
    total_run_km = sum(int(item["run_km"]) for item in rows if item["is_day_summary"])
    payload = {
        "date_from": first_day.isoformat(),
        "date_to": last_day.isoformat(),
        "total_days": total_days,
        "total_fillings": len(rows),
        "total_run_km": total_run_km,
        "rows": rows,
    }

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
    elements = [
        Paragraph("Diesel Fill Trip Sheet", styles["Title"]),
        Paragraph(
            f"Date Range: {payload['date_from']} to {payload['date_to']}",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
    ]

    table_data, section_row_indexes = _build_diesel_pdf_table_data(payload["rows"])

    table = Table(
        table_data,
        colWidths=[14 * mm, 20 * mm, 24 * mm, 18 * mm, 18 * mm, 18 * mm, 28 * mm, 46 * mm, 64 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17395F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.3),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
                ("ALIGN", (0, 0), (5, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    for row_index in section_row_indexes:
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, row_index), (-1, row_index)),
                    ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#EAF3FF")),
                    ("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"),
                    ("ALIGN", (0, row_index), (-1, row_index), "LEFT"),
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
            ["Accountant", "IME Manager", "Zonal Head"],
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
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="diesel-fill-trip-sheet-{month:02d}-{year}.pdf"'
    )
    return response


@admin_required
def admin_audit_logs(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    logs = _audit_items(query)
    return _render_admin(request, "admin/audit_logs.html", {"query": query, "logs": logs})


@admin_required
def admin_export_report(request: HttpRequest, report_type: str) -> HttpResponse:
    report_type = report_type.lower()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{report_type}-report.csv"'
    writer = csv.writer(response)

    if report_type == "users":
        writer.writerow(["id", "username", "email", "phone", "role", "is_active"])
        for user in User.objects.order_by("id"):
            writer.writerow([user.id, user.username, user.email, user.phone, user.role, user.is_active])
        return response

    if report_type == "transporters":
        writer.writerow(["id", "company_name", "username", "phone", "address"])
        for transporter in Transporter.objects.select_related("user").order_by("company_name"):
            writer.writerow(
                [
                    transporter.id,
                    transporter.company_name,
                    transporter.user.username,
                    transporter.user.phone,
                    transporter.address,
                ]
            )
        return response

    if report_type == "vehicles":
        writer.writerow(
            ["id", "vehicle_number", "model", "status", "vehicle_type", "transporter"]
        )
        for vehicle in Vehicle.objects.select_related("transporter").order_by("vehicle_number"):
            writer.writerow(
                [
                    vehicle.id,
                    vehicle.vehicle_number,
                    vehicle.model,
                    vehicle.status,
                    vehicle.vehicle_type,
                    vehicle.transporter.company_name,
                ]
            )
        return response

    if report_type == "drivers":
        writer.writerow(["id", "username", "phone", "license_number", "transporter", "assigned_vehicle", "is_active"])
        for driver in Driver.objects.select_related("user", "transporter", "assigned_vehicle").order_by("user__username"):
            writer.writerow(
                [
                    driver.id,
                    driver.user.username,
                    driver.user.phone,
                    driver.license_number,
                    driver.transporter.company_name,
                    driver.assigned_vehicle.vehicle_number if driver.assigned_vehicle else "",
                    driver.is_active,
                ]
            )
        return response

    if report_type == "attendance":
        writer.writerow(["date", "driver", "vehicle", "status", "start_km", "end_km", "latitude", "longitude"])
        for row in Attendance.objects.select_related("driver", "driver__user", "vehicle").order_by("-date", "driver__user__username"):
            writer.writerow(
                [
                    row.date,
                    row.driver.user.username,
                    row.vehicle.vehicle_number,
                    row.status,
                    row.start_km,
                    row.end_km if row.end_km is not None else "",
                    row.latitude,
                    row.longitude,
                ]
            )
        return response

    if report_type == "trips":
        writer.writerow(["date", "driver", "vehicle", "start_location", "destination", "start_km", "end_km", "total_km", "purpose"])
        queryset = Trip.objects.select_related("attendance", "attendance__driver", "attendance__driver__user", "attendance__vehicle").order_by("-created_at")
        for row in queryset:
            writer.writerow(
                [
                    row.attendance.date,
                    row.attendance.driver.user.username,
                    row.attendance.vehicle.vehicle_number,
                    row.start_location,
                    row.destination,
                    row.start_km,
                    row.end_km,
                    row.total_km,
                    row.purpose,
                ]
            )
        return response

    if report_type == "fuel":
        writer.writerow(["date", "driver", "vehicle", "liters", "amount"])
        queryset = FuelRecord.objects.select_related("driver", "driver__user", "vehicle").order_by("-date", "-created_at")
        for row in queryset:
            writer.writerow([row.date, row.driver.user.username, row.vehicle.vehicle_number, row.liters, row.amount])
        return response

    writer.writerow(["message"])
    writer.writerow(["Unsupported report type."])
    return response


@admin_required
def profile(request: HttpRequest) -> HttpResponse:
    users = User.objects.all()
    audit_items = _audit_items()
    context = {
        "member_since": request.user.date_joined,
        "managed_users": users.count(),
        "active_users": users.filter(is_active=True).count(),
        "inactive_users": users.filter(is_active=False).count(),
        "total_transporters": Transporter.objects.count(),
        "total_vehicles": Vehicle.objects.count(),
        "total_drivers": Driver.objects.count(),
        "latest_audit": audit_items[0] if audit_items else None,
    }
    return _render_admin(request, "admin/profile.html", context)


@admin_required
def admin_settings(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        request.user.email = request.POST.get("email", "").strip()
        request.user.phone = request.POST.get("phone_number", "").strip()
        request.user.save(update_fields=["email", "phone"])

        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if any([current_password, new_password, confirm_password]):
            if not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
                return _render_admin(request, "admin/settings.html")
            if new_password != confirm_password:
                messages.error(request, "New password and confirm password do not match.")
                return _render_admin(request, "admin/settings.html")
            if len(new_password) < 8:
                messages.error(request, "New password must be at least 8 characters.")
                return _render_admin(request, "admin/settings.html")
            request.user.set_password(new_password)
            request.user.save(update_fields=["password"])
            update_session_auth_hash(request, request.user)

        messages.success(request, "Settings updated.")

    context = {"phone_number": request.user.phone}
    return _render_admin(request, "admin/settings.html", context)


def admin_forgot_password(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        messages.info(request, "Password reset mail backend is not configured yet.")
    return _render_admin(request, "admin/forgot_password.html")


def admin_reset_password(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        messages.info(request, "OTP reset flow is not configured yet.")
    return _render_admin(request, "admin/reset_password.html")


def admin_register(request: HttpRequest) -> HttpResponse:
    return _render_admin(request, "admin/register.html")


@admin_required
def lock_screen(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        password = request.POST.get("password", "")
        user = authenticate(request, username=request.user.username, password=password)
        if user and (user.is_superuser or user.role == User.Role.ADMIN):
            request.session["admin_locked"] = False
            return redirect("dashboard")
        messages.error(request, "Incorrect password.")
    else:
        request.session["admin_locked"] = True

    return _render_admin(request, "admin/lock_screen.html", {"locked_user": request.user})


@admin_required
def toggle_theme(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        current = request.session.get("admin_theme", "light")
        request.session["admin_theme"] = "dark" if current != "dark" else "light"
    return redirect(_safe_next_url(request, "/admin/"))
