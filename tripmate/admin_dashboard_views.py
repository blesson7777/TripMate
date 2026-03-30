from __future__ import annotations

from base64 import b64decode
from calendar import monthrange
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import shutil
import secrets
import socket
import subprocess
import sys
import tarfile
from types import SimpleNamespace
from urllib import request
from urllib.parse import urlencode
import uuid
import zipfile

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Max, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static as static_url
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from attendance.models import (
    Attendance,
    AttendanceLocationPoint,
    DriverDailyAttendanceMark,
    TransportService,
)
from diesel.models import (
    DieselDailyRoutePlan,
    DieselDailyRoutePlanStop,
    DieselRouteStartPoint,
    IndusTowerSite,
)
from diesel.site_utils import (
    SiteNameUpdateConfirmationRequired,
    ensure_site_name_update_confirmed,
    validate_indus_site_id,
    validate_site_name,
)
from diesel.route_planner import (
    format_route_legs,
    optimize_route_order,
    validate_lat_lon,
)
from diesel.views import (
    _build_diesel_pdf_table_data,
    _build_tripsheet_rows as _build_diesel_tripsheet_rows,
)
from drivers.models import Driver
from fuel.analytics import get_vehicle_fuel_status
from fuel.models import FuelRecord
from salary.email_utils import send_salary_balance_email_now
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from trips.models import Trip
from users.account_deletion import perform_account_deletion
from users.auth_events import log_forced_logout, revoke_user_sessions
from users.models import (
    AccountDeletionRequest,
    AdminBroadcastNotification,
    AuthSessionEvent,
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
from users.push_service import is_push_enabled
from users.services import send_password_reset_otp
from vehicles.models import Vehicle
from services.route_optimizer import (
    MAX_TOWERS_PER_REQUEST,
    RouteOptimizerError,
    optimize_route,
    optimize_route_path,
)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


PWA_APP_NAME = "TripMate Fleet Admin"
PWA_SHORT_NAME = "TripMate Admin"
PWA_DESCRIPTION = "Installable TripMate fleet operations dashboard for admins."
PWA_THEME_COLOR = "#17395F"
PWA_BACKGROUND_COLOR = "#F5F7FB"
PWA_CACHE_NAME = "tripmate-admin-v1"


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


def _admin_pwa_scope() -> str:
    return reverse("dashboard")


def _admin_pwa_core_assets() -> list[str]:
    return [
        reverse("admin_offline"),
        reverse("admin_pwa_manifest"),
        static_url("css/style.css"),
        static_url("css/dashboard.css"),
        static_url("js/dashboard-ux.js"),
        static_url("js/admin-pwa.js"),
        static_url("images/logo-dark.svg"),
        static_url("pwa/icon-192.png"),
        static_url("pwa/icon-512.png"),
        static_url("pwa/icon-maskable-192.png"),
        static_url("pwa/icon-maskable-512.png"),
    ]


def admin_pwa_manifest(request: HttpRequest) -> HttpResponse:
    admin_scope = _admin_pwa_scope()
    payload = {
        "id": admin_scope,
        "name": PWA_APP_NAME,
        "short_name": PWA_SHORT_NAME,
        "description": PWA_DESCRIPTION,
        "start_url": admin_scope,
        "scope": admin_scope,
        "display": "standalone",
        "background_color": PWA_BACKGROUND_COLOR,
        "theme_color": PWA_THEME_COLOR,
        "lang": "en",
        "categories": ["business", "productivity"],
        "prefer_related_applications": False,
        "icons": [
            {
                "src": static_url("pwa/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": static_url("pwa/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
            },
            {
                "src": static_url("pwa/icon-maskable-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": static_url("pwa/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    response = HttpResponse(
        json.dumps(payload),
        content_type="application/manifest+json",
    )
    response["Cache-Control"] = "no-cache"
    return response


def admin_service_worker(request: HttpRequest) -> HttpResponse:
    offline_url = reverse("admin_offline")
    core_assets = _admin_pwa_core_assets()
    script = f"""
const CACHE_NAME = {json.dumps(PWA_CACHE_NAME)};
const OFFLINE_URL = {json.dumps(offline_url)};
const APP_ASSETS = new Set({json.dumps(core_assets)});

self.addEventListener('install', (event) => {{
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(Array.from(APP_ASSETS)))
      .then(() => self.skipWaiting())
  );
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
}});

async function networkFirstPage(request) {{
  const cache = await caches.open(CACHE_NAME);
  try {{
    const response = await fetch(request);
    if (response && response.ok) {{
      cache.put(request, response.clone());
    }}
    return response;
  }} catch (error) {{
    const cachedResponse = await cache.match(request);
    return cachedResponse || cache.match(OFFLINE_URL);
  }}
}}

async function staleWhileRevalidate(request) {{
  const cache = await caches.open(CACHE_NAME);
  const cachedResponse = await cache.match(request, {{ ignoreSearch: true }});
  const networkResponse = fetch(request)
    .then((response) => {{
      if (response && (response.ok || response.type === 'opaque')) {{
        cache.put(request, response.clone());
      }}
      return response;
    }})
    .catch(() => cachedResponse);
  return cachedResponse || networkResponse;
}}

self.addEventListener('fetch', (event) => {{
  const request = event.request;
  if (request.method !== 'GET') {{
    return;
  }}

  const url = new URL(request.url);
  const isRuntimeAsset = ['style', 'script', 'font', 'image'].includes(request.destination);
  const isSameOriginAppAsset = (
    url.origin === self.location.origin
    && (
      url.pathname.startsWith('/static/')
      || APP_ASSETS.has(url.pathname)
    )
  );

  if (request.mode === 'navigate') {{
    event.respondWith(networkFirstPage(request));
    return;
  }}

  if (isSameOriginAppAsset || isRuntimeAsset) {{
    event.respondWith(staleWhileRevalidate(request));
  }}
}});
""".strip()
    response = HttpResponse(
        script,
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = _admin_pwa_scope()
    return response


def admin_offline(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "admin/offline.html",
        {
            "dashboard_url": reverse("dashboard"),
            "login_url": reverse("admin_login"),
        },
    )


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


_AUDIT_DETAILS_SEPARATOR = " ||| "


def _record_admin_audit(
    request: HttpRequest,
    *,
    action: str,
    target: object | None = None,
    details: str = "",
    action_flag: int = CHANGE,
) -> None:
    if not request.user.is_authenticated:
        return

    content_type_id = None
    object_id = None
    target_label = "-"
    if target is not None:
        content_type_id = ContentType.objects.get_for_model(target.__class__).pk
        object_id = str(getattr(target, "pk", ""))
        target_label = str(target)

    details_text = (details or "").replace(_AUDIT_DETAILS_SEPARATOR, " | ").strip()
    object_repr = target_label
    if details_text:
        object_repr = f"{target_label}{_AUDIT_DETAILS_SEPARATOR}{details_text}"

    LogEntry.objects.create(
        user_id=request.user.pk,
        content_type_id=content_type_id,
        object_id=object_id or None,
        object_repr=object_repr[:200],
        action_flag=action_flag,
        change_message=action,
    )


def _previous_month(value: date) -> tuple[int, int]:
    if value.month == 1:
        return 12, value.year - 1
    return value.month - 1, value.year


def _activate_app_release(release: AppRelease, *, send_push: bool = False) -> None:
    published_at = release.published_at or timezone.now()
    (
        AppRelease.objects.filter(app_variant=release.app_variant)
        .exclude(pk=release.pk)
        .update(is_active=False)
    )
    release.is_active = True
    release.published_at = published_at
    release.save(update_fields=["is_active", "published_at", "updated_at"])
    if send_push:
        create_app_release_update_notifications(release=release)


def _active_release_map() -> dict[str, AppRelease]:
    active_releases = (
        AppRelease.objects.filter(is_active=True)
        .order_by("app_variant", "-build_number", "-published_at", "-created_at")
    )
    mapping: dict[str, AppRelease] = {}
    for release in active_releases:
        mapping.setdefault(release.app_variant, release)
    return mapping


def _normalize_version_label(version: str, build_number: int | None) -> str:
    version_text = (version or "").strip()
    if build_number is None:
        return version_text or "Unknown"
    if version_text:
        return f"{version_text} ({build_number})"
    return str(build_number)


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
    entries = LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:200]
    query_lc = query.lower()
    items: list[SimpleNamespace] = []
    for entry in entries:
        action = entry.get_change_message() or entry.get_action_flag_display() or "Updated"
        raw_repr = entry.object_repr or ""
        target_label = "-"
        details = ""
        if _AUDIT_DETAILS_SEPARATOR in raw_repr:
            target_label, details = raw_repr.split(_AUDIT_DETAILS_SEPARATOR, 1)
        else:
            target_label = raw_repr or (
                entry.content_type.name.title() if entry.content_type else "-"
            )
        actor = entry.user
        haystack = (
            f"{action} {target_label} {details} "
            f"{actor.username if actor else ''} "
            f"{entry.content_type.name if entry.content_type else ''}"
        ).lower()
        if query_lc and query_lc not in haystack:
            continue
        items.append(
            SimpleNamespace(
                created_at=entry.action_time,
                actor=actor,
                action=action,
                target_label=target_label,
                target_model=(entry.content_type.name.title() if entry.content_type else "-"),
                details=details or "-",
            )
        )
    return items


BACKUP_ROOT = settings.BASE_DIR / "backups"
DB_BACKUP_ROOT = BACKUP_ROOT / "database"
MEDIA_BACKUP_ROOT = BACKUP_ROOT / "media"


def _format_bytes(size: int) -> str:
    value = float(max(size, 0))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{size} B"


def _directory_size(path) -> int:
    target = Path(path)
    if not target.exists():
        return 0
    total = 0
    for item in target.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _ensure_backup_directories() -> None:
    DB_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    MEDIA_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def _backup_metadata_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.name}.meta.json")


def _write_backup_metadata(file_path: Path, backup_type: str, extra: dict | None = None) -> dict:
    stat = file_path.stat()
    created_at = timezone.now()
    payload = {
        "backup_type": backup_type,
        "file_name": file_path.name,
        "file_path": str(file_path),
        "created_at": created_at.isoformat(),
        "size_bytes": stat.st_size,
        "size_human": _format_bytes(stat.st_size),
    }
    if extra:
        payload.update(extra)
    _backup_metadata_path(file_path).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def _load_backup_items() -> list[dict]:
    _ensure_backup_directories()
    items: list[dict] = []
    for root, backup_type in ((DB_BACKUP_ROOT, "database"), (MEDIA_BACKUP_ROOT, "media")):
        for item in root.iterdir():
            if not item.is_file() or item.name.endswith(".meta.json"):
                continue
            metadata_path = _backup_metadata_path(item)
            payload = None
            if metadata_path.exists():
                try:
                    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = None
            if payload is None:
                stat = item.stat()
                payload = {
                    "backup_type": backup_type,
                    "file_name": item.name,
                    "file_path": str(item),
                    "created_at": timezone.datetime.fromtimestamp(
                        stat.st_mtime,
                        tz=timezone.get_current_timezone(),
                    ).isoformat(),
                    "size_bytes": stat.st_size,
                    "size_human": _format_bytes(stat.st_size),
                }
            payload["size_human"] = payload.get("size_human") or _format_bytes(
                int(payload.get("size_bytes") or 0)
            )
            created_at_raw = str(payload.get("created_at") or "")
            try:
                created_at_value = timezone.datetime.fromisoformat(created_at_raw)
                if timezone.is_naive(created_at_value):
                    created_at_value = timezone.make_aware(
                        created_at_value,
                        timezone.get_current_timezone(),
                    )
                payload["created_at_sort"] = created_at_value.isoformat()
                payload["created_at_label"] = timezone.localtime(created_at_value).strftime(
                    "%d %b %Y, %I:%M %p"
                )
            except ValueError:
                payload["created_at_sort"] = created_at_raw
                payload["created_at_label"] = created_at_raw or "-"
            items.append(payload)
    items.sort(key=lambda row: row.get("created_at_sort", ""), reverse=True)
    return items


def _build_backup_metadata_payload() -> dict:
    items = _load_backup_items()
    latest_backup = items[0] if items else None
    return {
        "generated_at": timezone.now().isoformat(),
        "backup_root": str(BACKUP_ROOT),
        "total_backups": len(items),
        "latest_backup": latest_backup,
        "items": items,
    }


def _backup_root_for_type(backup_type: str) -> Path | None:
    normalized = (backup_type or "").strip().lower()
    if normalized == "database":
        return DB_BACKUP_ROOT
    if normalized == "media":
        return MEDIA_BACKUP_ROOT
    return None


def _resolve_backup_file(backup_type: str, file_name: str) -> Path:
    root = _backup_root_for_type(backup_type)
    safe_name = Path(file_name or "").name
    if root is None or not safe_name or safe_name != (file_name or ""):
        raise FileNotFoundError("Invalid backup file.")
    target = (root / safe_name).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents or not target.exists() or not target.is_file():
        raise FileNotFoundError("Backup file not found.")
    return target


def _create_database_backup() -> dict:
    _ensure_backup_directories()
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    output_path = DB_BACKUP_ROOT / f"tripmate-db-{timestamp}.dump"
    database = settings.DATABASES["default"]
    env = os.environ.copy()
    if database.get("PASSWORD"):
        env["PGPASSWORD"] = str(database["PASSWORD"])

    command = [
        "pg_dump",
        "--format=custom",
        f"--host={database.get('HOST') or 'localhost'}",
        f"--port={database.get('PORT') or '5432'}",
        f"--username={database.get('USER') or ''}",
        f"--file={output_path}",
        str(database.get("NAME") or ""),
    ]

    subprocess.run(command, check=True, env=env, capture_output=True, text=True)
    return _write_backup_metadata(
        output_path,
        "database",
        {
            "database_name": database.get("NAME"),
            "database_host": database.get("HOST") or "localhost",
            "database_port": database.get("PORT") or "5432",
            "format": "pg_dump_custom",
        },
    )


def _create_media_backup() -> dict:
    _ensure_backup_directories()
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    output_path = MEDIA_BACKUP_ROOT / f"tripmate-media-{timestamp}.tar.gz"
    media_root = Path(settings.MEDIA_ROOT)
    with tarfile.open(output_path, "w:gz") as archive:
        if media_root.exists():
            archive.add(media_root, arcname="media")
    media_files = sum(1 for path in media_root.rglob("*") if path.is_file()) if media_root.exists() else 0
    return _write_backup_metadata(
        output_path,
        "media",
        {
            "source_directory": str(media_root),
            "media_files": media_files,
            "format": "tar.gz",
        },
    )


def _check_database_health() -> dict:
    database = settings.DATABASES["default"]
    start = timezone.now()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
        duration_ms = int((timezone.now() - start).total_seconds() * 1000)
        return {
            "status": "Healthy",
            "status_class": "success",
            "detail": f"{database.get('ENGINE', '').split('.')[-1]} on {database.get('HOST') or 'localhost'}:{database.get('PORT') or '5432'}",
            "version": version,
            "latency_ms": duration_ms,
        }
    except Exception as exc:
        return {
            "status": "Unavailable",
            "status_class": "danger",
            "detail": str(exc),
            "version": "-",
            "latency_ms": None,
        }


def _check_email_health() -> dict:
    backend = settings.EMAIL_BACKEND
    host = settings.EMAIL_HOST
    port = settings.EMAIL_PORT
    if "smtp" not in backend.lower():
        return {
            "status": "Non-SMTP backend",
            "status_class": "secondary",
            "detail": backend,
            "host": host or "-",
            "port": port,
        }
    if not host:
        return {
            "status": "Not configured",
            "status_class": "warning",
            "detail": "EMAIL_HOST is missing.",
            "host": "-",
            "port": port,
        }
    try:
        with socket.create_connection((host, int(port)), timeout=5):
            reachable = True
    except OSError as exc:
        return {
            "status": "Unreachable",
            "status_class": "danger",
            "detail": str(exc),
            "host": host,
            "port": port,
        }
    return {
        "status": "Reachable" if reachable else "Unknown",
        "status_class": "success" if reachable else "warning",
        "detail": f"SMTP reachable. TLS={'on' if settings.EMAIL_USE_TLS else 'off'}",
        "host": host,
        "port": port,
    }


def _check_fcm_health() -> dict:
    service_account_file = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", "").strip()
    service_account_json = getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "").strip()
    project_id = getattr(settings, "FCM_PROJECT_ID", "").strip()
    server_key = getattr(settings, "FCM_SERVER_KEY", "").strip()
    push_enabled = is_push_enabled()
    if service_account_file or service_account_json:
        mode = "FCM v1"
        detail = f"Project ID: {project_id or 'missing'}"
    elif server_key:
        mode = "FCM legacy"
        detail = "Legacy server key configured."
    else:
        mode = "Disabled"
        detail = "No FCM credentials configured."
    return {
        "status": "Ready" if push_enabled else "Not configured",
        "status_class": "success" if push_enabled else "warning",
        "detail": detail,
        "mode": mode,
    }


def _build_storage_health() -> dict:
    usage = shutil.disk_usage(settings.BASE_DIR)
    total = usage.total
    used = usage.used
    free = usage.free
    return {
        "total_human": _format_bytes(total),
        "used_human": _format_bytes(used),
        "free_human": _format_bytes(free),
        "used_percent": round((used / total) * 100, 1) if total else 0,
        "media_human": _format_bytes(_directory_size(settings.MEDIA_ROOT)),
        "static_human": _format_bytes(_directory_size(settings.STATIC_ROOT)),
        "backup_human": _format_bytes(_directory_size(BACKUP_ROOT)),
    }


_SERVER_HEALTH_UNLOCK_SESSION_KEY = "server_health_unlocked_until"
_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY = "server_health_unlock_user_id"
_SERVER_HEALTH_LAST_OUTPUT_SESSION_KEY = "server_health_last_ops_output"
_SERVER_HEALTH_LAST_OUTPUT_TITLE_SESSION_KEY = "server_health_last_ops_output_title"


def _server_health_password_required() -> bool:
    return bool(
        getattr(settings, "SERVER_HEALTH_PASSWORD_HASH", "").strip()
        or getattr(settings, "SERVER_HEALTH_PASSWORD", "").strip()
    )


def _server_health_unlock_ttl_minutes() -> int:
    raw_value = getattr(settings, "SERVER_HEALTH_UNLOCK_TTL_MINUTES", 30)
    try:
        minutes = int(raw_value)
    except (TypeError, ValueError):
        minutes = 30
    return min(max(minutes, 1), 24 * 60)


def _server_health_unlock_until(request: HttpRequest) -> timezone.datetime | None:
    raw_value = request.session.get(_SERVER_HEALTH_UNLOCK_SESSION_KEY)
    if not raw_value:
        return None
    try:
        unlocked_until = timezone.datetime.fromisoformat(str(raw_value))
    except ValueError:
        request.session.pop(_SERVER_HEALTH_UNLOCK_SESSION_KEY, None)
        request.session.pop(_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY, None)
        return None
    if timezone.is_naive(unlocked_until):
        unlocked_until = timezone.make_aware(
            unlocked_until,
            timezone.get_current_timezone(),
        )
    return unlocked_until


def _server_health_is_unlocked(request: HttpRequest) -> bool:
    unlocked_until = _server_health_unlock_until(request)
    if unlocked_until is None:
        return False
    if request.session.get(_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY) != request.user.id:
        request.session.pop(_SERVER_HEALTH_UNLOCK_SESSION_KEY, None)
        request.session.pop(_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY, None)
        return False
    if timezone.now() >= unlocked_until:
        request.session.pop(_SERVER_HEALTH_UNLOCK_SESSION_KEY, None)
        request.session.pop(_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY, None)
        return False
    return True


def _server_health_set_unlocked(request: HttpRequest) -> timezone.datetime:
    unlocked_until = timezone.now() + timedelta(minutes=_server_health_unlock_ttl_minutes())
    request.session[_SERVER_HEALTH_UNLOCK_SESSION_KEY] = unlocked_until.isoformat()
    request.session[_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY] = request.user.id
    return unlocked_until


def _server_health_clear_unlock(request: HttpRequest) -> None:
    request.session.pop(_SERVER_HEALTH_UNLOCK_SESSION_KEY, None)
    request.session.pop(_SERVER_HEALTH_UNLOCK_USER_SESSION_KEY, None)


def _server_health_password_matches(submitted_password: str) -> bool:
    submitted_password = (submitted_password or "").strip()
    if not submitted_password:
        return False

    password_hash = getattr(settings, "SERVER_HEALTH_PASSWORD_HASH", "").strip()
    if password_hash:
        try:
            return check_password(submitted_password, password_hash)
        except Exception:
            return False

    password_plain = getattr(settings, "SERVER_HEALTH_PASSWORD", "").strip()
    if password_plain:
        return secrets.compare_digest(submitted_password, password_plain)

    return False


def server_health_unlock_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not _server_health_password_required():
            return view_func(request, *args, **kwargs)
        if _server_health_is_unlocked(request):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Unlock Server Health first to access this action.")
        return redirect("admin_server_health")

    return wrapper


def _trim_text(value: str, max_chars: int = 10000) -> str:
    value = value or ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n... (truncated)"


def _run_local_command(command: list[str], *, timeout_s: int = 15) -> dict:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "command": command,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Timed out after {timeout_s}s",
            "command": command,
        }


def _store_server_health_output(request: HttpRequest, title: str, result: dict) -> None:
    command_str = " ".join(str(part) for part in result.get("command") or [])
    exit_code = result.get("returncode")
    stdout_value = _trim_text(str(result.get("stdout") or ""))
    stderr_value = _trim_text(str(result.get("stderr") or ""))
    payload = [
        f"Time: {timezone.localtime(timezone.now()):%d %b %Y, %I:%M %p}",
        f"Command: {command_str}",
        f"Exit code: {exit_code}",
        "",
    ]
    if stdout_value.strip():
        payload.extend(["STDOUT:", stdout_value.strip(), ""])
    if stderr_value.strip():
        payload.extend(["STDERR:", stderr_value.strip(), ""])
    request.session[_SERVER_HEALTH_LAST_OUTPUT_TITLE_SESSION_KEY] = title
    request.session[_SERVER_HEALTH_LAST_OUTPUT_SESSION_KEY] = "\n".join(payload).strip()


def _systemctl_badge(state: str) -> str:
    state = (state or "").strip().lower()
    if state == "active":
        return "success"
    if state in {"inactive", "deactivating"}:
        return "secondary"
    if state in {"failed"}:
        return "danger"
    if state in {"activating", "reloading"}:
        return "warning"
    return "secondary"


def _enabled_badge(state: str) -> str:
    state = (state or "").strip().lower()
    if state == "enabled":
        return "success"
    if state in {"disabled", "static", "indirect"}:
        return "secondary"
    return "secondary"


def _build_service_status(service_name: str) -> dict:
    if not sys.platform.startswith("linux") or shutil.which("systemctl") is None:
        return {
            "service": service_name,
            "supported": False,
            "active": "unsupported",
            "active_badge": "secondary",
            "enabled": "unsupported",
            "enabled_badge": "secondary",
        }

    active_result = _run_local_command(["systemctl", "is-active", service_name], timeout_s=5)
    active_state = (active_result.get("stdout") or active_result.get("stderr") or "").strip() or "unknown"

    enabled_result = _run_local_command(["systemctl", "is-enabled", service_name], timeout_s=5)
    enabled_state = (enabled_result.get("stdout") or enabled_result.get("stderr") or "").strip() or "unknown"

    return {
        "service": service_name,
        "supported": True,
        "active": active_state,
        "active_badge": _systemctl_badge(active_state),
        "enabled": enabled_state,
        "enabled_badge": _enabled_badge(enabled_state),
    }


def _sudo_nopasswd_available() -> bool:
    if not sys.platform.startswith("linux") or shutil.which("sudo") is None:
        return False
    result = _run_local_command(["sudo", "-n", "true"], timeout_s=5)
    return bool(result.get("ok"))


def _schedule_systemd_action(unit_prefix: str, action_command: list[str], *, delay_seconds: int = 2) -> dict:
    unit_suffix = f"{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    unit_name = f"{unit_prefix}-{unit_suffix}"
    systemd_run_path = shutil.which("systemd-run")
    if not sys.platform.startswith("linux") or systemd_run_path is None:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "systemd-run is not available on this host.",
            "command": ["systemd-run"] + action_command,
        }

    return _run_local_command(
        [
            "sudo",
            "-n",
            systemd_run_path,
            "--quiet",
            f"--unit={unit_name}",
            f"--on-active={max(delay_seconds, 0)}s",
            *action_command,
        ],
        timeout_s=12,
    )


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
    attendance_today_count = attendance_today.count()
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
        "active_vehicle_pct": round((active_vehicles / total_vehicles) * 100) if total_vehicles else 0,
        "total_drivers": total_drivers,
        "active_drivers": active_drivers,
        "active_driver_pct": round((active_drivers / total_drivers) * 100) if total_drivers else 0,
        "attendance_today_count": attendance_today_count,
        "on_duty_count": on_duty_count,
        "on_duty_pct": round((on_duty_count / attendance_today_count) * 100) if attendance_today_count else 0,
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
        "session_revoked_at": target_user.session_revoked_at,
        "active_device_tokens": UserDeviceToken.objects.filter(user=target_user, is_active=True).count(),
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
    if not target_user.is_active:
        revoke_user_sessions(target_user)
        log_forced_logout(
            request,
            target_user,
            reason=f"Admin {request.user.username} disabled the account.",
        )

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
    _record_admin_audit(
        request,
        action="Updated user active status",
        target=target_user,
        details=f"Set active={target_user.is_active} for role {target_user.role}.",
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
    revoke_user_sessions(target_user)
    log_forced_logout(
        request,
        target_user,
        reason=f"Admin {request.user.username} forced password reset.",
    )
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
    _record_admin_audit(
        request,
        action="Forced password reset",
        target=target_user,
        details=f"OTP sent to {normalized_email}.",
    )
    return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))


@admin_required
def admin_force_user_logout(request: HttpRequest, user_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_users")

    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "You cannot force logout your own admin account.")
        return redirect(_safe_next_url(request, f"/admin/users/{target_user.id}/"))

    revoke_user_sessions(target_user)
    log_forced_logout(
        request,
        target_user,
        reason=f"Admin {request.user.username} forced logout from admin console.",
    )
    messages.success(
        request,
        f"Forced logout completed for '{target_user.username}'. Active sessions were revoked.",
    )
    _record_admin_audit(
        request,
        action="Forced logout",
        target=target_user,
        details="Revoked all refresh tokens and deactivated active device tokens.",
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

    _record_admin_audit(
        request,
        action="Deleted user",
        target=target_user,
        details=f"Deleted role {target_user.role} account.",
        action_flag=DELETION,
    )
    username = target_user.username
    target_user.delete()
    messages.success(request, f"User '{username}' deleted.")
    return redirect("admin_users")


@admin_required
def admin_account_deletion_requests(request: HttpRequest) -> HttpResponse:
    status_filter = str(request.GET.get("status", "")).strip().upper()
    source_filter = str(request.GET.get("source", "")).strip().upper()
    search = str(request.GET.get("q", "")).strip()

    deletion_requests = AccountDeletionRequest.objects.select_related(
        "user",
        "processed_by",
    ).order_by("-requested_at")

    if status_filter in AccountDeletionRequest.Status.values:
        deletion_requests = deletion_requests.filter(status=status_filter)
    else:
        status_filter = ""

    if source_filter in AccountDeletionRequest.Source.values:
        deletion_requests = deletion_requests.filter(source=source_filter)
    else:
        source_filter = ""

    if search:
        deletion_requests = deletion_requests.filter(
            Q(email__icontains=search)
            | Q(note__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__phone__icontains=search)
        )

    stats = AccountDeletionRequest.objects.aggregate(
        total=Count("id"),
        requested=Count(
            "id",
            filter=Q(status=AccountDeletionRequest.Status.REQUESTED),
        ),
        completed=Count(
            "id",
            filter=Q(status=AccountDeletionRequest.Status.COMPLETED),
        ),
        app=Count(
            "id",
            filter=Q(source=AccountDeletionRequest.Source.APP),
        ),
        web=Count(
            "id",
            filter=Q(source=AccountDeletionRequest.Source.WEB),
        ),
    )

    return _render_admin(
        request,
        "admin/account_deletion_requests.html",
        {
            "deletion_requests": deletion_requests[:250],
            "status_filter": status_filter,
            "source_filter": source_filter,
            "search_query": search,
            "stats": stats,
            "status_choices": AccountDeletionRequest.Status.choices,
            "source_choices": AccountDeletionRequest.Source.choices,
        },
    )


@admin_required
def admin_process_account_deletion_request(
    request: HttpRequest,
    request_id: int,
) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_account_deletion_requests")

    deletion_request = get_object_or_404(
        AccountDeletionRequest.objects.select_related("user"),
        id=request_id,
    )
    target_user = deletion_request.user
    if target_user is None:
        messages.error(
            request,
            "This deletion request has no linked user account to process.",
        )
        return redirect("admin_account_deletion_requests")
    if target_user == request.user:
        messages.error(request, "You cannot process deletion for your own admin account.")
        return redirect("admin_account_deletion_requests")
    if target_user.is_superuser:
        messages.error(request, "Deleting superuser accounts is blocked.")
        return redirect("admin_account_deletion_requests")

    if (
        deletion_request.status == AccountDeletionRequest.Status.COMPLETED
        and not target_user.is_active
    ):
        messages.info(request, "This account deletion has already been completed.")
        return redirect("admin_account_deletion_requests")

    revoked_at = revoke_user_sessions(target_user)
    log_forced_logout(
        request,
        target_user,
        reason=(
            f"Admin {request.user.username} processed account deletion request "
            f"#{deletion_request.id}."
        ),
    )
    perform_account_deletion(
        target_user,
        source=deletion_request.source,
        note=deletion_request.note,
        processed_at=revoked_at,
        processed_by=request.user,
        existing_request=deletion_request,
    )
    messages.success(
        request,
        f"Account deletion completed for request #{deletion_request.id}.",
    )
    _record_admin_audit(
        request,
        action="Processed account deletion",
        target=target_user,
        details=f"Processed deletion request #{deletion_request.id}.",
        action_flag=CHANGE,
    )
    return redirect("admin_account_deletion_requests")


@admin_required
def admin_delete_account_deletion_request(
    request: HttpRequest,
    request_id: int,
) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_account_deletion_requests")

    deletion_request = get_object_or_404(
        AccountDeletionRequest.objects.select_related("user"),
        id=request_id,
    )
    target = deletion_request.user
    request_email = deletion_request.email
    request_number = deletion_request.id
    deletion_request.delete()
    messages.success(
        request,
        f"Deletion request #{request_number} removed from the monitor.",
    )
    _record_admin_audit(
        request,
        action="Deleted account deletion request",
        target=target,
        details=f"Removed deletion request #{request_number} for {request_email}.",
        action_flag=DELETION,
    )
    return redirect("admin_account_deletion_requests")


@admin_required
def admin_transporters(request: HttpRequest) -> HttpResponse:
    create_form = {
        "username": "",
        "email": "",
        "phone": "",
        "company_name": "",
        "address": "",
    }

    

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
                    transporter = transporter_user.transporter_profile
                _record_admin_audit(
                    request,
                    action="Created transporter",
                    target=transporter,
                    details=f"Created transporter user '{username}'.",
                    action_flag=ADDITION,
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
            feature_name = request.POST.get("feature_name", "").strip()

            transporter = None
            if partner_id_raw.isdigit():
                transporter = Transporter.objects.filter(id=int(partner_id_raw)).first()

            if transporter is None:
                messages.error(request, "Selected transporter does not exist.")
                return redirect("admin_partner_features")

            if enabled_raw not in {"0", "1"}:
                messages.error(request, "Invalid feature toggle value.")
                return redirect("admin_partner_features")

            if feature_name not in {"diesel_module", "diesel_readings", "location_monitoring", "auto_mail"}:
                messages.error(request, "Invalid feature selected.")
                return redirect("admin_partner_features")

            enabled = enabled_raw == "1"

            if (
                feature_name == "diesel_readings"
                and enabled
                and not transporter.diesel_tracking_enabled
            ):
                messages.error(
                    request,
                    "Enable Diesel Module first before enabling Tower Readings.",
                )
                return redirect("admin_partner_features")

            # Detect current value
            if feature_name == "diesel_module":
                current_value = transporter.diesel_tracking_enabled
            elif feature_name == "diesel_readings":
                current_value = transporter.diesel_readings_enabled
            elif feature_name == "location_monitoring":
                current_value = transporter.location_tracking_enabled
            else:
                current_value = transporter.salary_auto_email_enabled

            if current_value != enabled:

                if feature_name == "diesel_module":
                    transporter.diesel_tracking_enabled = enabled
                    update_fields = ["diesel_tracking_enabled"]
                    if not enabled and transporter.diesel_readings_enabled:
                        transporter.diesel_readings_enabled = False
                        update_fields.append("diesel_readings_enabled")
                    transporter.save(update_fields=update_fields)

                elif feature_name == "diesel_readings":
                    transporter.diesel_readings_enabled = enabled
                    transporter.save(update_fields=["diesel_readings_enabled"])

                elif feature_name == "location_monitoring":
                    transporter.location_tracking_enabled = enabled
                    transporter.save(update_fields=["location_tracking_enabled"])

                else:
                    transporter.salary_auto_email_enabled = enabled
                    transporter.save(update_fields=["salary_auto_email_enabled"])

                FeatureToggleLog.objects.create(
                    admin=request.user,
                    partner=transporter,
                    feature_name=feature_name,
                    action=(
                        FeatureToggleLog.Action.ENABLED
                        if enabled
                        else FeatureToggleLog.Action.DISABLED
                    ),
                )

                if feature_name == "diesel_module":
                    create_diesel_module_toggled_notifications(
                        transporter=transporter,
                        enabled=enabled,
                    )

                feature_label_map = {
                    "diesel_module": "Diesel module",
                    "diesel_readings": "Tower readings",
                    "location_monitoring": "Location monitoring",
                    "auto_mail": "Salary auto mail",
                }

                feature_label = feature_label_map.get(feature_name, "Feature")

                messages.success(
                    request,
                    f"{feature_label} {'enabled' if enabled else 'disabled'} for {transporter.company_name}.",
                )

                _record_admin_audit(
                    request,
                    action="Toggled partner feature",
                    target=transporter,
                    details=f"{feature_name} set to {enabled}.",
                )

            else:
                feature_label_map = {
                    "diesel_module": "Diesel module",
                    "diesel_readings": "Tower readings",
                    "location_monitoring": "Location monitoring",
                    "auto_mail": "Salary auto mail",
                }

                feature_label = feature_label_map.get(feature_name, "Feature")

                messages.info(
                    request,
                    f"{feature_label} is already {'enabled' if enabled else 'disabled'} for {transporter.company_name}.",
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
def admin_partner_feature_detail(request: HttpRequest, partner_id: int) -> HttpResponse:
    transporter = (
        Transporter.objects.select_related("user")
        .filter(id=partner_id)
        .first()
    )
    if transporter is None:
        messages.error(request, "Selected transporter does not exist.")
        return redirect("admin_partner_features")

    if request.method == "POST":
        enabled_raw = request.POST.get("enabled", "").strip()
        feature_name = request.POST.get("feature_name", "").strip()

        if enabled_raw not in {"0", "1"}:
            messages.error(request, "Invalid feature toggle value.")
            return redirect("admin_partner_feature_detail", partner_id=transporter.id)

        if feature_name not in {"diesel_module", "diesel_readings", "location_monitoring", "auto_mail"}:
            messages.error(request, "Invalid feature selected.")
            return redirect("admin_partner_feature_detail", partner_id=transporter.id)

        enabled = enabled_raw == "1"

        if feature_name == "diesel_readings" and enabled and not transporter.diesel_tracking_enabled:
            messages.error(
                request,
                "Enable Diesel Module first before enabling Tower Readings.",
            )
            return redirect("admin_partner_feature_detail", partner_id=transporter.id)

        if feature_name == "diesel_module":
            current_value = transporter.diesel_tracking_enabled
        elif feature_name == "diesel_readings":
            current_value = transporter.diesel_readings_enabled
        elif feature_name == "location_monitoring":
            current_value = transporter.location_tracking_enabled
        else:
            current_value = transporter.salary_auto_email_enabled

        if current_value != enabled:
            if feature_name == "diesel_module":
                transporter.diesel_tracking_enabled = enabled
                update_fields = ["diesel_tracking_enabled"]
                if not enabled and transporter.diesel_readings_enabled:
                    transporter.diesel_readings_enabled = False
                    update_fields.append("diesel_readings_enabled")
                transporter.save(update_fields=update_fields)

            elif feature_name == "diesel_readings":
                transporter.diesel_readings_enabled = enabled
                transporter.save(update_fields=["diesel_readings_enabled"])

            elif feature_name == "location_monitoring":
                transporter.location_tracking_enabled = enabled
                transporter.save(update_fields=["location_tracking_enabled"])

            else:
                transporter.salary_auto_email_enabled = enabled
                transporter.save(update_fields=["salary_auto_email_enabled"])

            FeatureToggleLog.objects.create(
                admin=request.user,
                partner=transporter,
                feature_name=feature_name,
                action=(
                    FeatureToggleLog.Action.ENABLED
                    if enabled
                    else FeatureToggleLog.Action.DISABLED
                ),
            )

            if feature_name == "diesel_module":
                create_diesel_module_toggled_notifications(
                    transporter=transporter,
                    enabled=enabled,
                )

            feature_label_map = {
                "diesel_module": "Diesel module",
                "diesel_readings": "Tower readings",
                "location_monitoring": "Location monitoring",
                "auto_mail": "Salary auto mail",
            }
            feature_label = feature_label_map.get(feature_name, "Feature")

            messages.success(
                request,
                f"{feature_label} {'enabled' if enabled else 'disabled'} for {transporter.company_name}.",
            )

            _record_admin_audit(
                request,
                action="Toggled partner feature",
                target=transporter,
                details=f"{feature_name} set to {enabled}.",
            )
        else:
            feature_label_map = {
                "diesel_module": "Diesel module",
                "diesel_readings": "Tower readings",
                "location_monitoring": "Location monitoring",
                "auto_mail": "Salary auto mail",
            }
            feature_label = feature_label_map.get(feature_name, "Feature")
            messages.info(
                request,
                f"{feature_label} is already {'enabled' if enabled else 'disabled'} for {transporter.company_name}.",
            )

        return redirect("admin_partner_feature_detail", partner_id=transporter.id)

    recent_logs = (
        FeatureToggleLog.objects.select_related("admin", "partner")
        .filter(partner=transporter)
        .order_by("-created_at")[:25]
    )

    context = {
        "transporter": transporter,
        "recent_logs": recent_logs,
    }
    return _render_admin(request, "admin/partner_feature_detail.html", context)

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
            _record_admin_audit(
                request,
                action="Created broadcast notification",
                target=broadcast,
                details=f"Audience={audience}, active={is_active}, title='{title}'.",
                action_flag=ADDITION,
            )
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
            _record_admin_audit(
                request,
                action="Toggled broadcast notification",
                target=broadcast,
                details=f"Set active={broadcast.is_active}.",
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
            send_push = request.POST.get("send_push") == "1"

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
                _activate_app_release(release, send_push=send_push)
                if send_push:
                    messages.success(
                        request,
                        f"{release.get_app_variant_display()} release {release.version_name} published and pushed.",
                    )
                else:
                    messages.success(
                        request,
                        f"{release.get_app_variant_display()} release {release.version_name} published without push.",
                    )
            else:
                messages.success(
                    request,
                    f"{release.get_app_variant_display()} release {release.version_name} uploaded.",
                )
            _record_admin_audit(
                request,
                action="Created app release",
                target=release,
                details=(
                    f"Variant={release.app_variant}, build={release.build_number}, "
                    f"force_update={release.force_update}, published={publish_now}, "
                    f"send_push={send_push}."
                ),
                action_flag=ADDITION,
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
                _activate_app_release(release, send_push=False)
                messages.success(
                    request,
                    f"{release.get_app_variant_display()} release {release.version_name} is now active without push.",
                )
                _record_admin_audit(
                    request,
                    action="Activated app release",
                    target=release,
                    details=(
                        f"Set active release for {release.app_variant} "
                        f"build {release.build_number} without push."
                    ),
                )
                return redirect("admin_app_releases")

            if form_action == "push_release":
                create_app_release_update_notifications(release=release, force_push=True)
                messages.success(
                    request,
                    f"Update push sent again for {release.get_app_variant_display()} {release.version_name}.",
                )
                _record_admin_audit(
                    request,
                    action="Re-pushed app release notification",
                    target=release,
                    details=f"Forced push for {release.app_variant} build {release.build_number}.",
                )
                return redirect("admin_app_releases")

            _record_admin_audit(
                request,
                action="Deleted app release",
                target=release,
                details=f"Removed {release.app_variant} build {release.build_number}.",
                action_flag=DELETION,
            )
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
def admin_app_version_usage(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    selected_variant = request.GET.get("app_variant", "").strip().upper()
    outdated_only = request.GET.get("outdated") == "1"

    queryset = UserDeviceToken.objects.select_related("user").filter(is_active=True)
    if selected_variant in {
        UserDeviceToken.AppVariant.DRIVER,
        UserDeviceToken.AppVariant.TRANSPORTER,
    }:
        queryset = queryset.filter(app_variant=selected_variant)
    else:
        queryset = queryset.exclude(app_variant=UserDeviceToken.AppVariant.GENERIC)

    if query:
        queryset = queryset.filter(
            Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(token__icontains=query)
        )

    active_releases = _active_release_map()
    rows = []
    current_count = 0
    outdated_count = 0
    unknown_count = 0

    for device in queryset.order_by("app_variant", "user__username", "-last_seen_at"):
        active_release = active_releases.get(device.app_variant)
        is_unknown = device.app_build_number is None
        is_outdated = bool(
            active_release is not None
            and (
                device.app_build_number is None
                or device.app_build_number < active_release.build_number
            )
        )
        is_current = bool(
            active_release is not None
            and device.app_build_number is not None
            and device.app_build_number >= active_release.build_number
        )

        if outdated_only and not is_outdated:
            continue

        if is_unknown:
            unknown_count += 1
        if is_outdated:
            outdated_count += 1
        elif is_current:
            current_count += 1

        rows.append(
            {
                "device": device,
                "user": device.user,
                "active_release": active_release,
                "device_version_label": _normalize_version_label(
                    device.app_version,
                    device.app_build_number,
                ),
                "active_release_label": (
                    _normalize_version_label(
                        active_release.version_name,
                        active_release.build_number,
                    )
                    if active_release is not None
                    else "No active release"
                ),
                "is_unknown": is_unknown,
                "is_outdated": is_outdated,
                "is_current": is_current,
            }
        )

    context = {
        "query": query,
        "selected_variant": selected_variant,
        "outdated_only": outdated_only,
        "variant_choices": [
            (UserDeviceToken.AppVariant.DRIVER, "Driver"),
            (UserDeviceToken.AppVariant.TRANSPORTER, "Transporter"),
        ],
        "rows": rows,
        "current_count": current_count,
        "outdated_count": outdated_count,
        "unknown_count": unknown_count,
        "driver_active_release": active_releases.get(AppRelease.AppVariant.DRIVER),
        "transporter_active_release": active_releases.get(AppRelease.AppVariant.TRANSPORTER),
    }
    return _render_admin(request, "admin/app_version_usage.html", context)


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
        _record_admin_audit(
            request,
            action="Updated vehicle type",
            target=vehicle,
            details=f"Set vehicle_type={vehicle.vehicle_type}.",
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
        _record_admin_audit(
            request,
            action="Updated vehicle tank capacity",
            target=vehicle,
            details=f"Set tank_capacity_liters={vehicle.tank_capacity_liters}.",
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
                vehicle = Vehicle.objects.create(
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
                _record_admin_audit(
                    request,
                    action="Created vehicle",
                    target=vehicle,
                    details=(
                        f"Created under transporter '{transporter.company_name}' "
                        f"with type {vehicle.vehicle_type}."
                    ),
                    action_flag=ADDITION,
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
        _record_admin_audit(
            request,
            action="Removed driver from transporter",
            target=driver,
            details=(
                f"Removed from '{previous_transporter.company_name}'. "
                f"Cleared vehicle={had_vehicle}, default_service={had_service}."
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
            _record_admin_audit(
                request,
                action="Sent driver salary email",
                target=driver,
                details=f"Sent salary email for {month:02d}/{year}.",
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
                    driver = Driver.objects.create(
                        user=driver_user,
                        transporter=transporter,
                        license_number=license_number,
                        assigned_vehicle=assigned_vehicle,
                        is_active=is_active,
                    )
                _record_admin_audit(
                    request,
                    action="Created driver",
                    target=driver,
                    details=(
                        f"Created under transporter '{transporter.company_name}' "
                        f"with assigned vehicle '{assigned_vehicle.vehicle_number if assigned_vehicle else '-'}'."
                    ),
                    action_flag=ADDITION,
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
        _record_admin_audit(
            request,
            action="Forced absent and purged attendance",
            target=target_driver,
            details=(
                f"Date={mark_date.isoformat()}, deleted_attendance={attendance_count}, "
                f"deleted_trips={day_trip_count}."
            ),
        )
        return redirect(redirect_url)

    if request.method == "POST" and request.POST.get("form_action") == "bulk_mark_present":
        driver_id_raw = request.POST.get("driver_id", "").strip()
        from_date_raw = request.POST.get("from_date", "").strip()
        to_date_raw = request.POST.get("to_date", "").strip()
        adjust_joined = request.POST.get("adjust_joined") == "1"
        override_locked = request.POST.get("override_locked") == "1"

        redirect_params = {
            "date": request.POST.get("date", "").strip() or today.isoformat(),
            "transporter_id": request.POST.get("transporter_id", "").strip(),
            "status": request.POST.get("status", "").strip(),
            "driver_id": driver_id_raw,
            "month": request.POST.get("month", "").strip(),
            "year": request.POST.get("year", "").strip(),
            "mark_date": from_date_raw,
        }
        redirect_query = urlencode(
            {key: value for key, value in redirect_params.items() if value}
        )
        redirect_url = reverse("admin_attendance")
        if redirect_query:
            redirect_url = f"{redirect_url}?{redirect_query}"

        if not driver_id_raw.isdigit():
            messages.error(request, "Select a valid driver before backfilling attendance.")
            return redirect(redirect_url)

        target_driver = (
            Driver.objects.select_related("user", "transporter")
            .filter(id=int(driver_id_raw))
            .first()
        )
        if target_driver is None:
            messages.error(request, "Selected driver does not exist.")
            return redirect(redirect_url)

        if target_driver.transporter is None:
            messages.error(request, "Selected driver is not assigned to a transporter.")
            return redirect(redirect_url)

        try:
            from_date = date.fromisoformat(from_date_raw)
        except ValueError:
            messages.error(request, "Invalid from date.")
            return redirect(redirect_url)

        if to_date_raw:
            try:
                to_date = date.fromisoformat(to_date_raw)
            except ValueError:
                messages.error(request, "Invalid to date.")
                return redirect(redirect_url)
        else:
            to_date = today

        if to_date > today:
            to_date = today
        if from_date > to_date:
            messages.error(request, "From date must be on or before to date.")
            return redirect(redirect_url)

        joined_date = target_driver.joined_transporter_date
        joined_updated = False

        created_count = 0
        updated_count = 0
        skipped_attendance_count = 0
        skipped_locked_count = 0

        attendance_dates = set(
            Attendance.objects.filter(
                driver=target_driver,
                date__gte=from_date,
                date__lte=to_date,
            )
            .values_list("date", flat=True)
            .distinct()
        )

        existing_marks = {
            item.date: item.status
            for item in DriverDailyAttendanceMark.objects.filter(
                driver=target_driver,
                transporter=target_driver.transporter,
                date__gte=from_date,
                date__lte=to_date,
            ).only("date", "status")
        }

        with transaction.atomic():
            if adjust_joined and joined_date is not None and from_date < joined_date:
                joined_at = timezone.make_aware(
                    datetime.combine(from_date, datetime.min.time()),
                    timezone.get_current_timezone(),
                )
                target_driver.joined_transporter_at = joined_at
                target_driver.save(update_fields=["joined_transporter_at"])
                joined_updated = True

            total_days = (to_date - from_date).days + 1
            for day_offset in range(total_days):
                target_date = from_date + timedelta(days=day_offset)
                if target_date in attendance_dates:
                    skipped_attendance_count += 1
                    continue

                current_status = existing_marks.get(target_date)
                if (
                    current_status
                    in {
                        DriverDailyAttendanceMark.Status.ABSENT,
                        DriverDailyAttendanceMark.Status.LEAVE,
                    }
                    and not override_locked
                ):
                    skipped_locked_count += 1
                    continue

                mark, created = DriverDailyAttendanceMark.objects.update_or_create(
                    driver=target_driver,
                    transporter=target_driver.transporter,
                    date=target_date,
                    defaults={
                        "status": DriverDailyAttendanceMark.Status.PRESENT,
                        "marked_by": request.user,
                    },
                )
                if created:
                    created_count += 1
                elif current_status != mark.status:
                    updated_count += 1

        summary_parts = []
        if created_count:
            summary_parts.append(f"created {created_count}")
        if updated_count:
            summary_parts.append(f"updated {updated_count}")
        if skipped_attendance_count:
            summary_parts.append(f"skipped {skipped_attendance_count} day(s) with run data")
        if skipped_locked_count:
            summary_parts.append(f"skipped {skipped_locked_count} locked day(s)")
        if joined_updated:
            summary_parts.append("updated join date")

        messages.success(
            request,
            (
                f"Backfilled attendance marks for '{target_driver.user.username}' from "
                f"{from_date.isoformat()} to {to_date.isoformat()} "
                f"({', '.join(summary_parts) if summary_parts else 'no changes'})."
            ),
        )
        _record_admin_audit(
            request,
            action="Backfilled driver attendance",
            target=target_driver,
            details=(
                f"from={from_date.isoformat()}, to={to_date.isoformat()}, created={created_count}, "
                f"updated={updated_count}, skipped_attendance={skipped_attendance_count}, "
                f"skipped_locked={skipped_locked_count}, joined_updated={joined_updated}."
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
        _record_admin_audit(
            request,
            action="Marked driver attendance",
            target=target_driver,
            details=f"Date={mark_date.isoformat()}, status={mark.status}.",
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


def _build_admin_driver_location_sessions(
    date_filter: date, transporter_id: str, driver_id: str
) -> tuple[list[dict], list[dict], set[int]]:
    attendances = Attendance.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "vehicle__transporter",
    ).prefetch_related(
        Prefetch(
            "location_points",
            queryset=AttendanceLocationPoint.objects.order_by("recorded_at", "id"),
            to_attr="_prefetched_location_points",
        )
    ).filter(date=date_filter)

    if transporter_id.isdigit():
        attendances = attendances.filter(vehicle__transporter_id=int(transporter_id))
    if driver_id.isdigit():
        attendances = attendances.filter(driver_id=int(driver_id))

    map_points: list[dict] = []
    session_rows: list[dict] = []
    driver_ids_with_locations: set[int] = set()

    for attendance in attendances.order_by("started_at", "id"):
        driver_name = attendance.driver.user.username
        vehicle_number = attendance.vehicle.vehicle_number
        transporter_name = attendance.vehicle.transporter.company_name
        service_name = attendance.service_name or "Unspecified Service"
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
            route_points.append(
                {
                    "latitude": point_lat,
                    "longitude": point_lon,
                }
            )
            driver_ids_with_locations.add(attendance.driver_id)
            point_recorded_at = timezone.localtime(point.recorded_at) if point.recorded_at else None
            point_time_label = point_recorded_at.strftime("%I:%M:%S %p") if point_recorded_at else "-"
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

        start_coordinates = route_points[0] if route_points else {
            "latitude": float(attendance.latitude),
            "longitude": float(attendance.longitude),
        }
        end_coordinates = route_points[-1] if route_points else None

        session_rows.append(
            {
                "attendance_id": attendance.id,
                "driver_name": driver_name,
                "transporter_name": transporter_name,
                "vehicle_number": vehicle_number,
                "service_name": service_name,
                "purpose": attendance.service_purpose or "-",
                "status_label": "Open" if attendance.ended_at is None else "Closed",
                "started_at_label": started_at_label,
                "ended_at_label": ended_at_label,
                "start_km": attendance.start_km,
                "end_km": attendance.end_km,
                "total_km": attendance.total_km if attendance.end_km is not None else 0,
                "start_latitude": start_coordinates["latitude"],
                "start_longitude": start_coordinates["longitude"],
                "end_latitude": end_coordinates["latitude"] if end_coordinates else None,
                "end_longitude": end_coordinates["longitude"] if end_coordinates else None,
                "has_end_coordinates": bool(end_coordinates),
                "route_points": route_points,
                "point_count": len(route_points),
                "last_seen_label": (
                    timezone.localtime(prefetched_points[-1].recorded_at).strftime("%I:%M:%S %p")
                    if prefetched_points
                    else "-"
                ),
            }
        )

    return map_points, session_rows, driver_ids_with_locations


@admin_required
def admin_driver_locations(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    date_filter = _parse_date_param(request.GET.get("date"), today)
    transporter_id = request.GET.get("transporter_id", "").strip()
    driver_id = request.GET.get("driver_id", "").strip()

    transporters = Transporter.objects.select_related("user").order_by("company_name")
    driver_options = Driver.objects.select_related("user", "transporter").filter(
        transporter__isnull=False
    )
    if transporter_id.isdigit():
        driver_options = driver_options.filter(transporter_id=int(transporter_id))
    driver_options = driver_options.order_by("user__username")

    map_points, session_rows, driver_ids_with_locations = _build_admin_driver_location_sessions(
        date_filter=date_filter,
        transporter_id=transporter_id,
        driver_id=driver_id,
    )

    selected_driver = None
    if driver_id.isdigit():
        selected_driver = driver_options.filter(id=int(driver_id)).first()
        if selected_driver is None:
            selected_driver = (
                Driver.objects.select_related("user", "transporter").filter(id=int(driver_id)).first()
            )

    context = {
        "transporters": transporters,
        "driver_options": driver_options[:400],
        "selected_transporter_id": transporter_id,
        "selected_driver_id": driver_id,
        "selected_driver": selected_driver,
        "date_filter": date_filter,
        "session_rows": session_rows,
        "map_points": map_points,
        "total_sessions": len(session_rows),
        "total_markers": len(map_points),
        "drivers_with_locations_count": len(driver_ids_with_locations),
    }
    return _render_admin(request, "admin/driver_locations.html", context)


@admin_required
def admin_driver_locations_data(request: HttpRequest) -> JsonResponse:
    today = timezone.localdate()
    date_filter = _parse_date_param(request.GET.get("date"), today)
    transporter_id = request.GET.get("transporter_id", "").strip()
    driver_id = request.GET.get("driver_id", "").strip()

    map_points, session_rows, driver_ids_with_locations = _build_admin_driver_location_sessions(
        date_filter=date_filter,
        transporter_id=transporter_id,
        driver_id=driver_id,
    )

    session_rows_payload = [
        {
            "attendance_id": row.get("attendance_id"),
            "status_label": row.get("status_label"),
            "start_km": row.get("start_km"),
            "end_km": row.get("end_km"),
            "total_km": row.get("total_km"),
            "point_count": row.get("point_count"),
            "last_seen_label": row.get("last_seen_label"),
        }
        for row in session_rows
    ]

    return JsonResponse(
        {
            "date": date_filter.isoformat(),
            "generated_at": timezone.localtime(timezone.now()).isoformat(),
            "map_points": map_points,
            "session_rows": session_rows_payload,
            "total_sessions": len(session_rows),
            "total_markers": len(map_points),
            "drivers_with_locations_count": len(driver_ids_with_locations),
        }
    )


@admin_required
def admin_auth_monitor(request: HttpRequest) -> HttpResponse:
    now = timezone.now()
    query = request.GET.get("q", "").strip()
    event_type = request.GET.get("event_type", "").strip()
    app_variant = request.GET.get("app_variant", "").strip().upper()
    try:
        days = int(request.GET.get("days", "7") or "7")
    except ValueError:
        days = 7
    days = max(1, min(days, 30))
    cutoff = now - timedelta(days=days)

    events = AuthSessionEvent.objects.select_related("user").filter(created_at__gte=cutoff)
    token_rows = OutstandingToken.objects.select_related("user").filter(created_at__gte=cutoff)

    if query:
        events = events.filter(
            Q(username__icontains=query)
            | Q(user__username__icontains=query)
            | Q(reason__icontains=query)
            | Q(path__icontains=query)
        )
        token_rows = token_rows.filter(user__username__icontains=query)

    if event_type:
        events = events.filter(event_type=event_type)
    if app_variant:
        events = events.filter(app_variant=app_variant)

    events = events.order_by("-created_at")
    unexpected_events = list(
        events.filter(
            event_type__in=[
                AuthSessionEvent.EventType.TOKEN_EXPIRED,
                AuthSessionEvent.EventType.TOKEN_INVALID,
            ]
        )[:80]
    )
    normal_logout_events = list(
        events.filter(event_type=AuthSessionEvent.EventType.LOGOUT_NORMAL)[:80]
    )
    forced_logout_events = list(
        events.filter(event_type=AuthSessionEvent.EventType.LOGOUT_FORCED)[:80]
    )
    login_events = list(
        events.filter(event_type=AuthSessionEvent.EventType.LOGIN_SUCCESS)[:80]
    )

    token_rows = list(token_rows.order_by("-created_at")[:120])
    for row in token_rows:
        row.is_blacklisted = BlacklistedToken.objects.filter(token=row).exists()

    selected_user = User.objects.filter(username__iexact=query).first() if query else None
    diagnosis = None
    if selected_user is not None:
        user_tokens = list(
            OutstandingToken.objects.filter(user=selected_user).order_by("-created_at")[:10]
        )
        for row in user_tokens:
            row.is_blacklisted = BlacklistedToken.objects.filter(token=row).exists()
        if len(user_tokens) >= 2:
            latest = user_tokens[0]
            previous = user_tokens[1]
            gap = latest.created_at - previous.created_at
            access_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
            matched_expiry = gap >= access_lifetime
            diagnosis = SimpleNamespace(
                selected_user=selected_user,
                latest_token=latest,
                previous_token=previous,
                gap=gap,
                matched_expiry=matched_expiry,
                message=(
                    "Latest re-login gap aligns with the configured access-token lifetime."
                    if matched_expiry
                    else "Latest re-login gap does not cleanly align with access-token expiry."
                ),
                token_rows=user_tokens,
            )
        else:
            diagnosis = SimpleNamespace(
                selected_user=selected_user,
                latest_token=user_tokens[0] if user_tokens else None,
                previous_token=None,
                gap=None,
                matched_expiry=False,
                message="Not enough login-token history to compare re-login gaps.",
                token_rows=user_tokens,
            )

    context = {
        "query": query,
        "selected_event_type": event_type,
        "selected_app_variant": app_variant,
        "selected_days": days,
        "unexpected_count": len(unexpected_events),
        "normal_logout_count": len(normal_logout_events),
        "forced_logout_count": len(forced_logout_events),
        "login_success_count": len(login_events),
        "active_device_tokens_count": UserDeviceToken.objects.filter(is_active=True).count(),
        "unexpected_events": unexpected_events,
        "normal_logout_events": normal_logout_events,
        "forced_logout_events": forced_logout_events,
        "login_events": login_events,
        "token_rows": token_rows,
        "diagnosis": diagnosis,
        "access_token_lifetime": settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
        "refresh_token_lifetime": settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
        "rotate_refresh_tokens": settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS", False),
        "blacklist_after_rotation": settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION", False),
        "auth_event_types": AuthSessionEvent.EventType.choices,
        "auth_app_variants": AuthSessionEvent.AppVariant.choices,
    }
    return _render_admin(request, "admin/auth_monitor.html", context)


@admin_required
def admin_run_exceptions(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    now = timezone.now()
    transporter_id = request.GET.get("transporter_id", "").strip()
    driver_id = request.GET.get("driver_id", "").strip()

    transporters = Transporter.objects.select_related("user").order_by("company_name")
    driver_options = Driver.objects.select_related("user", "transporter").filter(
        transporter__isnull=False
    )
    if transporter_id.isdigit():
        driver_options = driver_options.filter(transporter_id=int(transporter_id))
    driver_options = driver_options.order_by("user__username")

    open_sessions = Attendance.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "vehicle__transporter",
        "service",
    ).filter(ended_at__isnull=True)

    if transporter_id.isdigit():
        open_sessions = open_sessions.filter(vehicle__transporter_id=int(transporter_id))
    if driver_id.isdigit():
        open_sessions = open_sessions.filter(driver_id=int(driver_id))

    overnight_sessions = list(
        open_sessions.filter(date__lt=today).order_by("date", "started_at")[:120]
    )
    long_running_sessions = list(
        open_sessions.filter(started_at__lte=now - timedelta(hours=5)).order_by("started_at")[:120]
    )

    driver_conflict_ids = list(
        open_sessions.values("driver_id").annotate(session_count=Count("id")).filter(session_count__gt=1)
    )
    vehicle_conflict_ids = list(
        open_sessions.values("vehicle_id").annotate(session_count=Count("id")).filter(session_count__gt=1)
    )
    driver_conflict_rows = list(
        open_sessions.filter(driver_id__in=[item["driver_id"] for item in driver_conflict_ids]).order_by(
            "driver__user__username",
            "started_at",
        )
    )
    vehicle_conflict_rows = list(
        open_sessions.filter(vehicle_id__in=[item["vehicle_id"] for item in vehicle_conflict_ids]).order_by(
            "vehicle__vehicle_number",
            "started_at",
        )
    )

    open_child_trips = Trip.objects.select_related(
        "attendance",
        "attendance__driver",
        "attendance__driver__user",
        "attendance__vehicle",
        "attendance__vehicle__transporter",
    ).filter(status=Trip.Status.OPEN, is_day_trip=False)
    if transporter_id.isdigit():
        open_child_trips = open_child_trips.filter(attendance__vehicle__transporter_id=int(transporter_id))
    if driver_id.isdigit():
        open_child_trips = open_child_trips.filter(attendance__driver_id=int(driver_id))
    open_child_trips = list(open_child_trips.order_by("attendance__date", "started_at")[:120])

    mark_queryset = DriverDailyAttendanceMark.objects.select_related(
        "driver",
        "driver__user",
        "transporter",
    ).filter(status__in=[DriverDailyAttendanceMark.Status.ABSENT, DriverDailyAttendanceMark.Status.LEAVE])
    if transporter_id.isdigit():
        mark_queryset = mark_queryset.filter(transporter_id=int(transporter_id))
    if driver_id.isdigit():
        mark_queryset = mark_queryset.filter(driver_id=int(driver_id))
    mark_map = {
        (mark.driver_id, mark.transporter_id, mark.date): mark
        for mark in mark_queryset
    }

    mark_conflicts = []
    for attendance in open_sessions.order_by("date", "started_at"):
        transporter_pk = attendance.vehicle.transporter_id
        mark = mark_map.get((attendance.driver_id, transporter_pk, attendance.date))
        if mark is None:
            continue
        mark_conflicts.append(
            SimpleNamespace(
                attendance=attendance,
                mark=mark,
                conflict_label=f"{mark.get_status_display()} mark conflicts with open session",
            )
        )

    context = {
        "transporters": transporters,
        "driver_options": driver_options[:400],
        "selected_transporter_id": transporter_id,
        "selected_driver_id": driver_id,
        "open_sessions_count": open_sessions.count(),
        "overnight_sessions": overnight_sessions,
        "long_running_sessions": long_running_sessions,
        "driver_conflict_rows": driver_conflict_rows,
        "driver_conflict_count": len(driver_conflict_ids),
        "vehicle_conflict_rows": vehicle_conflict_rows,
        "vehicle_conflict_count": len(vehicle_conflict_ids),
        "open_child_trips": open_child_trips,
        "mark_conflicts": mark_conflicts,
    }
    return _render_admin(request, "admin/run_exceptions.html", context)


@admin_required
@server_health_unlock_required
def admin_backup_metadata_download(request: HttpRequest) -> HttpResponse:
    payload = _build_backup_metadata_payload()
    response = HttpResponse(
        json.dumps(payload, indent=2),
        content_type="application/json",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="tripmate-backup-metadata-{timezone.now().strftime("%Y%m%d-%H%M%S")}.json"'
    )
    return response


@admin_required
@server_health_unlock_required
def admin_backup_file_download(
    request: HttpRequest,
    backup_type: str,
    file_name: str,
) -> HttpResponse:
    file_path = _resolve_backup_file(backup_type, file_name)
    _record_admin_audit(
        request,
        action="Downloaded backup file",
        details=f"{backup_type}:{file_path.name}",
    )
    return FileResponse(
        file_path.open("rb"),
        as_attachment=True,
        filename=file_path.name,
    )


@admin_required
@server_health_unlock_required
def admin_backup_file_delete(
    request: HttpRequest,
    backup_type: str,
    file_name: str,
) -> HttpResponse:
    if request.method != "POST":
        return redirect("admin_server_health")

    file_path = _resolve_backup_file(backup_type, file_name)
    metadata_path = _backup_metadata_path(file_path)
    if metadata_path.exists():
        metadata_path.unlink(missing_ok=True)
    file_path.unlink(missing_ok=True)
    messages.success(request, f"Deleted backup {file_path.name}.")
    _record_admin_audit(
        request,
        action="Deleted backup file",
        details=f"{backup_type}:{file_path.name}",
        action_flag=DELETION,
    )
    return redirect("admin_server_health")


@admin_required
def admin_server_health(request: HttpRequest) -> HttpResponse:
    password_required = _server_health_password_required()
    action = request.POST.get("form_action", "").strip() if request.method == "POST" else ""

    if password_required and not _server_health_is_unlocked(request):
        if request.method == "POST" and action == "unlock_server_health":
            submitted_password = request.POST.get("server_health_password", "")
            if _server_health_password_matches(submitted_password):
                _server_health_set_unlocked(request)
                unlock_minutes = _server_health_unlock_ttl_minutes()
                messages.success(request, f"Server Health unlocked for {unlock_minutes} minutes.")
                _record_admin_audit(
                    request,
                    action="Unlocked Server Health",
                    details=f"TTL={unlock_minutes} minutes",
                )
                return redirect("admin_server_health")

            messages.error(request, "Invalid Server Health password.")
            _record_admin_audit(
                request,
                action="Server Health unlock failed",
                details="Invalid password",
            )

        context = {
            "unlock_ttl_minutes": _server_health_unlock_ttl_minutes(),
        }
        return _render_admin(request, "admin/server_health_unlock.html", context)

    if request.method == "POST":
        if action == "lock_server_health":
            _server_health_clear_unlock(request)
            messages.success(request, "Server Health locked.")
            _record_admin_audit(request, action="Locked Server Health")
            return redirect("admin_server_health")

        try:
            if action == "create_db_backup":
                metadata = _create_database_backup()
                messages.success(
                    request,
                    f"Database backup created: {metadata['file_name']} ({metadata['size_human']}).",
                )
                _record_admin_audit(
                    request,
                    action="Created database backup",
                    details=metadata["file_name"],
                    action_flag=ADDITION,
                )
                return redirect("admin_server_health")

            if action == "create_media_backup":
                metadata = _create_media_backup()
                messages.success(
                    request,
                    f"Media backup created: {metadata['file_name']} ({metadata['size_human']}).",
                )
                _record_admin_audit(
                    request,
                    action="Created media backup",
                    details=metadata["file_name"],
                    action_flag=ADDITION,
                )
                return redirect("admin_server_health")
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            messages.error(request, f"Backup failed: {message}")
            return redirect("admin_server_health")
        except FileNotFoundError as exc:
            messages.error(request, f"Backup tool not found: {exc}")
            return redirect("admin_server_health")
        except Exception as exc:
            messages.error(request, f"Backup failed: {exc}")
            return redirect("admin_server_health")

        if action == "restart_tripmate_service":
            result = _schedule_systemd_action(
                "tripmate-admin-restart-tripmate",
                ["/bin/systemctl", "restart", "tripmate"],
                delay_seconds=2,
            )
            _store_server_health_output(request, "Restart TripMate Service", result)
            if result.get("ok"):
                messages.success(
                    request,
                    "TripMate restart scheduled (2s). Refresh the page after a few seconds.",
                )
                _record_admin_audit(
                    request,
                    action="Scheduled TripMate restart",
                    details="delay=2s",
                    action_flag=CHANGE,
                )
            else:
                messages.error(request, f"Could not schedule restart: {result.get('stderr') or 'Unknown error'}")
            return redirect("admin_server_health")

        if action == "reload_nginx":
            test_result = _run_local_command(["sudo", "-n", "nginx", "-t"], timeout_s=15)
            if not test_result.get("ok"):
                _store_server_health_output(request, "Nginx Config Test (Failed)", test_result)
                messages.error(request, "Nginx config test failed. See output below.")
                return redirect("admin_server_health")

            reload_result = _run_local_command(["sudo", "-n", "systemctl", "reload", "nginx"], timeout_s=15)
            _store_server_health_output(request, "Reload Nginx", reload_result)
            if reload_result.get("ok"):
                messages.success(request, "Nginx reloaded successfully.")
                _record_admin_audit(request, action="Reloaded nginx", action_flag=CHANGE)
            else:
                messages.error(request, f"Nginx reload failed: {reload_result.get('stderr') or 'Unknown error'}")
            return redirect("admin_server_health")

        if action == "restart_nginx":
            result = _run_local_command(["sudo", "-n", "systemctl", "restart", "nginx"], timeout_s=20)
            _store_server_health_output(request, "Restart Nginx", result)
            if result.get("ok"):
                messages.success(request, "Nginx restarted successfully.")
                _record_admin_audit(request, action="Restarted nginx", action_flag=CHANGE)
            else:
                messages.error(request, f"Nginx restart failed: {result.get('stderr') or 'Unknown error'}")
            return redirect("admin_server_health")

        if action == "show_tripmate_status":
            result = _run_local_command(
                ["systemctl", "status", "tripmate", "--no-pager", "--lines=120"],
                timeout_s=15,
            )
            _store_server_health_output(request, "TripMate Service Status", result)
            return redirect("admin_server_health")

        if action == "show_nginx_status":
            result = _run_local_command(
                ["systemctl", "status", "nginx", "--no-pager", "--lines=120"],
                timeout_s=15,
            )
            _store_server_health_output(request, "Nginx Service Status", result)
            return redirect("admin_server_health")

        if action == "show_tripmate_logs":
            result = _run_local_command(
                ["sudo", "-n", "journalctl", "-u", "tripmate", "-n", "200", "--no-pager"],
                timeout_s=20,
            )
            _store_server_health_output(request, "TripMate Logs (Last 200 lines)", result)
            return redirect("admin_server_health")

        if action == "show_nginx_logs":
            result = _run_local_command(
                ["sudo", "-n", "journalctl", "-u", "nginx", "-n", "200", "--no-pager"],
                timeout_s=20,
            )
            _store_server_health_output(request, "Nginx Logs (Last 200 lines)", result)
            return redirect("admin_server_health")

        messages.error(request, "Unknown action.")
        return redirect("admin_server_health")

    backup_items = _load_backup_items()
    latest_backup = backup_items[0] if backup_items else None
    service_status = {
        "sudo_ok": _sudo_nopasswd_available(),
        "tripmate": _build_service_status("tripmate"),
        "nginx": _build_service_status("nginx"),
    }
    unlocked_until = _server_health_unlock_until(request) if password_required else None
    minutes_left = None
    if unlocked_until is not None:
        remaining_seconds = int((unlocked_until - timezone.now()).total_seconds())
        minutes_left = max(0, (remaining_seconds + 59) // 60)

    context = {
        "server_health_password_required": password_required,
        "server_health_unlocked_until": unlocked_until,
        "server_health_minutes_left": minutes_left,
        "database_health": _check_database_health(),
        "email_health": _check_email_health(),
        "fcm_health": _check_fcm_health(),
        "storage_health": _build_storage_health(),
        "service_status": service_status,
        "ops_output_title": request.session.pop(_SERVER_HEALTH_LAST_OUTPUT_TITLE_SESSION_KEY, ""),
        "ops_output": request.session.pop(_SERVER_HEALTH_LAST_OUTPUT_SESSION_KEY, ""),
        "backup_items": backup_items[:24],
        "latest_backup": latest_backup,
        "backup_root": str(BACKUP_ROOT),
    }
    return _render_admin(request, "admin/server_health.html", context)


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
    _record_admin_audit(
        request,
        action="Updated trip session",
        target=trip,
        details=(
            f"Action={action_label}, driver='{attendance.driver.user.username}', "
            f"vehicle='{attendance.vehicle.vehicle_number}', km={start_km}->{end_km}."
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
        _record_admin_audit(
            request,
            action="Deleted trip record",
            target=trip,
            details=trip_label,
            action_flag=DELETION,
        )
        trip.delete()
        if (
            attendance.ended_at is not None
            and attendance.status != Attendance.Status.NO_TRIP
            and not attendance.trips.filter(is_day_trip=False).exists()
        ):
            attendance.status = Attendance.Status.NO_TRIP
            attendance.service = None
            attendance.service_name = "Unspecified Service"
            attendance.service_purpose = ""
            attendance.end_km = None
            attendance.odo_end_image = None
            attendance.end_latitude = None
            attendance.end_longitude = None
            attendance.save(
                update_fields=[
                    "status",
                    "service",
                    "service_name",
                    "service_purpose",
                    "end_km",
                    "odo_end_image",
                    "end_latitude",
                    "end_longitude",
                ]
            )

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
    _record_admin_audit(
        request,
        action="Deleted vehicle fuel record",
        target=record,
        details=record_label,
        action_flag=DELETION,
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
            key,
            {
                "date": row_date,
                "vehicle_number": item.vehicle.vehicle_number,
                "start_km": (
                    attendance_start_km
                    if attendance_start_km is not None
                    else (item.start_km or 0)
                ),
                "end_km": (
                    attendance_end_km
                    if attendance_end_km is not None
                    else (item.end_km or 0)
                ),
                "sort_started_at": started_at,
                "records": [],
            },
        )
        bucket["sort_started_at"] = min(bucket["sort_started_at"], started_at)

        start_candidates = [
            value
            for value in [attendance_start_km, item.start_km]
            if value is not None
        ]
        if start_candidates:
            bucket["start_km"] = min([bucket["start_km"], *start_candidates])

        end_candidates = [
            value
            for value in [attendance_end_km, item.end_km]
            if value is not None
        ]
        if end_candidates:
            bucket["end_km"] = max([bucket["end_km"], *end_candidates])
        bucket["records"].append(item)

    sorted_groups = sorted(
        grouped.values(),
        key=lambda group: (group["date"], group["sort_started_at"], group["vehicle_number"]),
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
                    "vehicle_number": "",
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
                row.get("vehicle_number") or "",
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
            28 * mm,
            20 * mm,
            20 * mm,
            18 * mm,
            24 * mm,
            50 * mm,
            18 * mm,
            59 * mm,
        ],
        repeatRows=1,
    )

    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17395F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
        ("ALIGN", (0, 0), (6, -1), "CENTER"),
        ("ALIGN", (8, 1), (8, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    table_row_cursor = 1
    for row in rows:
        if row.get("is_day_summary"):
            table_styles.extend(
                [
                    ("BACKGROUND", (0, table_row_cursor), (-1, table_row_cursor), colors.HexColor("#EDF4FB")),
                    ("FONTNAME", (0, table_row_cursor), (5, table_row_cursor), "Helvetica-Bold"),
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

    transporter_id_raw = request.GET.get("transporter_id", "").strip()
    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id_raw)).select_related("user").first()
        if transporter_id_raw.isdigit()
        else None
    )
    if transporter_id_raw and selected_transporter is None:
        messages.error(request, "Selected transporter does not exist.")
        return redirect("admin_diesel_tripsheet")

    vehicle_id_raw = request.GET.get("vehicle_id", "").strip()
    diesel_vehicles = (
        Vehicle.objects.select_related("transporter")
        .filter(fuel_records__entry_type=FuelRecord.EntryType.TOWER_DIESEL)
        .distinct()
        .order_by("vehicle_number")
    )
    if selected_transporter is not None:
        diesel_vehicles = diesel_vehicles.filter(transporter=selected_transporter)

    selected_vehicle = None
    if vehicle_id_raw.isdigit():
        selected_vehicle = diesel_vehicles.filter(id=int(vehicle_id_raw)).first()
        if selected_vehicle is None:
            messages.error(request, "Selected diesel service vehicle does not exist.")
            return redirect("admin_diesel_tripsheet")

    records_qs = (
        FuelRecord.objects.select_related(
            "attendance",
            "driver",
            "driver__user",
            "vehicle",
            "vehicle__transporter",
        )
        .filter(
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            fill_date__gte=date_from,
            fill_date__lte=date_to,
        )
        .order_by("fill_date", "vehicle__vehicle_number", "driver__user__username", "created_at")
    )
    if selected_transporter is not None:
        records_qs = records_qs.filter(vehicle__transporter=selected_transporter)
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
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id_raw,
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
    download = request.GET.get("download", "").strip().lower()
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

    target_date = None
    if date_input:
        target_date = _parse_date_param(date_input, timezone.localdate())
        records_qs = records_qs.filter(fill_date=target_date)

    if download in {"csv", "zip", "photos"}:
        if target_date is None:
            messages.error(request, "Select a date to download the diesel logbook.")
            redirect_params = {}
            if query:
                redirect_params["q"] = query
            if transporter_id:
                redirect_params["transporter_id"] = transporter_id
            if vehicle_id:
                redirect_params["vehicle_id"] = vehicle_id
            redirect_url = reverse("admin_diesel_sites")
            if redirect_params:
                redirect_url = f"{redirect_url}?{urlencode(redirect_params)}"
            return redirect(redirect_url)

        export_qs = records_qs.order_by(
            "vehicle__vehicle_number",
            "driver__user__username",
            "created_at",
            "id",
        )
        headers = [
            "record_id",
            "fill_date",
            "transporter",
            "vehicle",
            "driver",
            "driver_phone",
            "start_km",
            "end_km",
            "run_km",
            "site_id",
            "site_name",
            "filled_qty",
            "purpose",
            "latitude",
            "longitude",
            "created_at",
            "logbook_photo_url",
            "logbook_photo_zip_path",
        ]

        def _export_row(record: FuelRecord, *, zip_photo_path: str = "") -> list[object]:
            photo_url = record.logbook_photo.url if record.logbook_photo else ""
            absolute_photo_url = request.build_absolute_uri(photo_url) if photo_url else ""
            return [
                record.id,
                (record.fill_date or record.date).isoformat(),
                record.vehicle.transporter.company_name,
                record.vehicle.vehicle_number,
                record.driver.user.username,
                getattr(record.driver.user, "phone", "") or "",
                record.start_km if record.start_km is not None else "",
                record.end_km if record.end_km is not None else "",
                record.run_km if record.run_km is not None else "",
                (record.resolved_indus_site_id or "").strip(),
                (record.resolved_site_name or "").strip(),
                float(record.fuel_filled or record.liters or 0),
                (record.purpose or "").strip(),
                float(record.resolved_tower_latitude) if record.resolved_tower_latitude is not None else "",
                float(record.resolved_tower_longitude) if record.resolved_tower_longitude is not None else "",
                timezone.localtime(record.created_at).isoformat() if record.created_at else "",
                absolute_photo_url,
                zip_photo_path,
            ]

        if download == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="diesel-logbook-{target_date.isoformat()}.csv"'
            )
            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow(headers)
            for record in export_qs.iterator(chunk_size=2000):
                writer.writerow(_export_row(record))
            return response

        if download == "photos":
            buffer = BytesIO()
            zip_filename = f"diesel-logbook-photos-{target_date.isoformat()}.zip"
            missing_photos: list[str] = []
            processed_records = 0
            added_photos = 0

            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                for record in export_qs.iterator(chunk_size=500):
                    processed_records += 1
                    if not record.logbook_photo:
                        missing_photos.append(
                            f"#{record.id} {record.vehicle.vehicle_number} {record.driver.user.username} (no photo)"
                        )
                        continue

                    extension = (
                        os.path.splitext(record.logbook_photo.name or "")[1].lower() or ".jpg"
                    )
                    vehicle_part = "".join(
                        ch if ch.isalnum() else "_" for ch in (record.vehicle.vehicle_number or "")
                    ).strip("_")
                    site_part = "".join(
                        ch if ch.isalnum() else "_" for ch in (record.resolved_indus_site_id or "")
                    ).strip("_")
                    zip_photo_path = (
                        f"logbook_photos/{target_date.isoformat()}/"
                        f"{vehicle_part or 'vehicle'}_{site_part or 'site'}_{record.id}{extension}"
                    )
                    try:
                        with record.logbook_photo.open("rb") as src, zip_file.open(
                            zip_photo_path, "w"
                        ) as dst:
                            shutil.copyfileobj(src, dst)
                        added_photos += 1
                    except Exception as exc:
                        missing_photos.append(f"#{record.id} {record.logbook_photo.name}: {exc}")

                if processed_records == 0:
                    zip_file.writestr(
                        "no_records.txt",
                        (
                            f"No tower diesel records found for {target_date.isoformat()} "
                            "with the selected filters.\n"
                        ).encode("utf-8"),
                    )
                elif added_photos == 0:
                    zip_file.writestr(
                        "no_photos.txt",
                        (
                            f"Found {processed_records} records for {target_date.isoformat()}, "
                            "but none had logbook photos.\n"
                        ).encode("utf-8"),
                    )
                if missing_photos:
                    zip_file.writestr(
                        "missing_photos.txt",
                        ("\n".join(missing_photos) + "\n").encode("utf-8"),
                    )

            response = HttpResponse(buffer.getvalue(), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
            return response

        buffer = BytesIO()
        zip_filename = f"diesel-logbook-{target_date.isoformat()}.zip"
        csv_name = f"diesel-logbook-{target_date.isoformat()}.csv"
        missing_photos: list[str] = []

        csv_buffer = StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow(headers)

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for record in export_qs.iterator(chunk_size=500):
                zip_photo_path = ""
                if record.logbook_photo:
                    extension = os.path.splitext(record.logbook_photo.name or "")[1].lower() or ".jpg"
                    vehicle_part = "".join(
                        ch if ch.isalnum() else "_" for ch in (record.vehicle.vehicle_number or "")
                    ).strip("_")
                    site_part = "".join(
                        ch if ch.isalnum() else "_" for ch in (record.resolved_indus_site_id or "")
                    ).strip("_")
                    zip_photo_path = (
                        f"logbook_photos/{target_date.isoformat()}/"
                        f"{vehicle_part or 'vehicle'}_{site_part or 'site'}_{record.id}{extension}"
                    )

                csv_writer.writerow(_export_row(record, zip_photo_path=zip_photo_path))

                if record.logbook_photo and zip_photo_path:
                    try:
                        with record.logbook_photo.open("rb") as src, zip_file.open(
                            zip_photo_path, "w"
                        ) as dst:
                            shutil.copyfileobj(src, dst)
                    except Exception as exc:
                        missing_photos.append(f"#{record.id} {record.logbook_photo.name}: {exc}")

            zip_file.writestr(csv_name, csv_buffer.getvalue().encode("utf-8-sig"))
            if missing_photos:
                zip_file.writestr(
                    "missing_photos.txt",
                    ("\n".join(missing_photos) + "\n").encode("utf-8"),
                )

        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
        return response

    rows = list(records_qs[:500])
    for row in rows:
        try:
            row.logbook_photo_exists = bool(row.logbook_photo) and row.logbook_photo.storage.exists(
                row.logbook_photo.name
            )
        except Exception:
            row.logbook_photo_exists = False

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
def admin_diesel_route_planner(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    transporter_id = request.GET.get("transporter_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()
    date_input = request.GET.get("date", "").strip()
    start_lat_input = request.GET.get("start_lat", "").strip()
    start_lng_input = request.GET.get("start_lng", "").strip()
    return_to_start = (request.GET.get("return_to_start") or "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }

    target_date = _parse_date_param(date_input, today)
    if not date_input:
        date_input = target_date.isoformat()

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).first() if transporter_id.isdigit() else None
    )

    diesel_vehicles = Vehicle.objects.select_related("transporter").filter(
        vehicle_type=Vehicle.Type.DIESEL_SERVICE
    )
    if transporter_id.isdigit():
        diesel_vehicles = diesel_vehicles.filter(transporter_id=int(transporter_id))
    else:
        diesel_vehicles = diesel_vehicles.none()
    diesel_vehicles = diesel_vehicles.order_by("vehicle_number")

    selected_vehicle = None
    if vehicle_id.isdigit():
        selected_vehicle = diesel_vehicles.filter(id=int(vehicle_id)).first()
        if selected_vehicle is None:
            selected_vehicle = (
                Vehicle.objects.select_related("transporter")
                .filter(id=int(vehicle_id), vehicle_type=Vehicle.Type.DIESEL_SERVICE)
                .first()
            )

    start_coordinate: tuple[float, float] | None = None
    if start_lat_input and start_lng_input:
        try:
            parsed_lat = float(Decimal(start_lat_input))
            parsed_lng = float(Decimal(start_lng_input))
            validate_lat_lon(parsed_lat, parsed_lng)
            start_coordinate = (parsed_lat, parsed_lng)
        except (InvalidOperation, ValueError) as exc:
            messages.error(request, f"Invalid start coordinates: {exc}")

    total_records = 0
    total_sites = 0
    total_qty = 0.0
    missing_sites: list[dict] = []
    route_rows: list[dict] = []
    map_payload: dict | None = None
    estimated_km: float | None = None
    recorded_km: int | None = None

    can_compute = transporter_id.isdigit() or vehicle_id.isdigit()
    if can_compute:
        records_qs = (
            FuelRecord.objects.select_related("vehicle", "vehicle__transporter", "tower_site")
            .filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                fill_date=target_date,
            )
            .order_by("id")
        )
        if transporter_id.isdigit():
            records_qs = records_qs.filter(vehicle__transporter_id=int(transporter_id))
        if vehicle_id.isdigit():
            records_qs = records_qs.filter(vehicle_id=int(vehicle_id))

        stops_by_key: dict[tuple[str, str], dict] = {}
        min_start_km: int | None = None
        max_end_km: int | None = None

        for record in records_qs.iterator(chunk_size=800):
            total_records += 1
            qty_value = record.fuel_filled if record.fuel_filled is not None else record.liters
            qty = float(qty_value or 0)
            total_qty += qty

            site_id = (record.resolved_indus_site_id or "").strip()
            site_name = (record.resolved_site_name or "").strip()
            key = ((site_id or "").upper(), (site_name or "").lower())
            stop = stops_by_key.get(key)
            if stop is None:
                stop = {
                    "site_id": site_id,
                    "site_name": site_name,
                    "qty": 0.0,
                    "latitude": None,
                    "longitude": None,
                    "record_count": 0,
                }
                stops_by_key[key] = stop

            stop["qty"] += qty
            stop["record_count"] += 1

            lat_value = record.resolved_tower_latitude
            lon_value = record.resolved_tower_longitude
            if stop["latitude"] is None and lat_value is not None and lon_value is not None:
                stop["latitude"] = float(lat_value)
                stop["longitude"] = float(lon_value)

            if record.start_km is not None:
                min_start_km = (
                    record.start_km if min_start_km is None else min(min_start_km, record.start_km)
                )
            if record.end_km is not None:
                max_end_km = record.end_km if max_end_km is None else max(max_end_km, record.end_km)

        stops = list(stops_by_key.values())
        total_sites = len(stops)

        stops_with_coords = [
            stop for stop in stops if stop.get("latitude") is not None and stop.get("longitude") is not None
        ]
        missing_sites = [
            stop for stop in stops if stop.get("latitude") is None or stop.get("longitude") is None
        ]

        if min_start_km is not None and max_end_km is not None and max_end_km >= min_start_km:
            recorded_km = max_end_km - min_start_km

        if stops_with_coords:
            stops_with_coords.sort(
                key=lambda item: (
                    (item.get("site_id") or "zzzzzzzz").upper(),
                    (item.get("site_name") or "").lower(),
                )
            )
            coords = [(item["latitude"], item["longitude"]) for item in stops_with_coords]
            optimized = optimize_route_order(
                coords,
                start=start_coordinate,
                return_to_start=return_to_start,
                max_swaps=4000 if len(coords) <= 120 else 2500,
            )
            estimated_km = float(optimized.total_km)
            legs = format_route_legs(
                coords,
                optimized.order,
                start=start_coordinate,
                return_to_start=return_to_start,
            )

            for leg in legs:
                if leg.get("is_return_leg"):
                    route_rows.append(
                        {
                            "seq": leg["seq"],
                            "site_id": "RETURN",
                            "site_name": "Return",
                            "qty": "",
                            "latitude": leg["latitude"],
                            "longitude": leg["longitude"],
                            "leg_km": leg["leg_km"],
                            "cumulative_km": leg["cumulative_km"],
                            "record_count": "",
                            "is_return_leg": True,
                        }
                    )
                    continue

                stop = stops_with_coords[int(leg["idx"])]
                route_rows.append(
                    {
                        "seq": leg["seq"],
                        "site_id": stop.get("site_id") or "",
                        "site_name": stop.get("site_name") or "",
                        "qty": float(stop.get("qty") or 0),
                        "latitude": stop.get("latitude"),
                        "longitude": stop.get("longitude"),
                        "leg_km": leg["leg_km"],
                        "cumulative_km": leg["cumulative_km"],
                        "record_count": stop.get("record_count") or 0,
                        "is_return_leg": False,
                    }
                )

            map_payload = {
                "stops": [
                    {
                        "seq": row["seq"],
                        "site_id": row["site_id"],
                        "site_name": row["site_name"],
                        "qty": row["qty"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                        "is_return_leg": bool(row.get("is_return_leg")),
                    }
                    for row in route_rows
                ],
                "start": (
                    {"latitude": start_coordinate[0], "longitude": start_coordinate[1]}
                    if start_coordinate is not None
                    else None
                ),
                "return_to_start": return_to_start,
                "target_date": target_date.isoformat(),
            }

    context = {
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id,
        "diesel_vehicles": diesel_vehicles,
        "selected_vehicle": selected_vehicle,
        "selected_vehicle_id": vehicle_id,
        "date_input": date_input,
        "target_date": target_date,
        "start_lat_input": start_lat_input,
        "start_lng_input": start_lng_input,
        "return_to_start": return_to_start,
        "can_compute": can_compute,
        "total_records": total_records,
        "total_sites": total_sites,
        "missing_sites": missing_sites,
        "missing_sites_count": len(missing_sites),
        "total_qty": total_qty,
        "estimated_km": estimated_km,
        "recorded_km": recorded_km,
        "route_rows": route_rows,
        "map_payload": map_payload,
    }
    return _render_admin(request, "admin/diesel_route_planner.html", context)


@admin_required
def admin_diesel_daily_plan_vehicle_options(request: HttpRequest) -> JsonResponse:
    transporter_id = (request.GET.get("transporter_id") or "").strip()
    selected_vehicle_id = (request.GET.get("selected_vehicle_id") or "").strip()

    if not transporter_id.isdigit():
        return JsonResponse({"count": 0, "items": []})

    transporter = get_object_or_404(Transporter, id=int(transporter_id))
    vehicles = list(
        Vehicle.objects.select_related("transporter")
        .filter(transporter=transporter)
        .order_by("vehicle_number")
    )

    selected_id = int(selected_vehicle_id) if selected_vehicle_id.isdigit() else None
    items = [
        {
            "id": vehicle.id,
            "vehicle_number": vehicle.vehicle_number,
            "model": vehicle.model,
            "status": vehicle.get_status_display(),
            "vehicle_type": vehicle.get_vehicle_type_display(),
            "selected": selected_id == vehicle.id,
        }
        for vehicle in vehicles
    ]
    return JsonResponse({"count": len(items), "items": items})


@admin_required
def admin_diesel_daily_plan_driver_options(request: HttpRequest) -> JsonResponse:
    transporter_id = (request.GET.get("transporter_id") or "").strip()
    selected_driver_id = (request.GET.get("selected_driver_id") or "").strip()

    if not transporter_id.isdigit():
        return JsonResponse({"count": 0, "items": []})

    transporter = get_object_or_404(Transporter, id=int(transporter_id))
    drivers = list(
        Driver.objects.select_related("user", "assigned_vehicle")
        .filter(transporter=transporter)
        .order_by("user__username")
    )

    selected_id = int(selected_driver_id) if selected_driver_id.isdigit() else None
    items = [
        {
            "id": driver.id,
            "username": driver.user.username,
            "phone": driver.user.phone or "",
            "assigned_vehicle_id": driver.assigned_vehicle_id,
            "assigned_vehicle_number": (
                driver.assigned_vehicle.vehicle_number
                if driver.assigned_vehicle_id and driver.assigned_vehicle is not None
                else ""
            ),
            "selected": selected_id == driver.id,
        }
        for driver in drivers
    ]
    return JsonResponse({"count": len(items), "items": items})


@admin_required
def admin_diesel_daily_plan_site_search(request: HttpRequest) -> JsonResponse:
    transporter_id = (request.GET.get("transporter_id") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        limit = 20
    limit = max(1, min(limit, 50))

    if not transporter_id.isdigit() or not search_query:
        return JsonResponse({"count": 0, "items": []})

    transporter = get_object_or_404(Transporter, id=int(transporter_id))
    sites = list(
        IndusTowerSite.objects.filter(partner=transporter)
        .filter(Q(indus_site_id__icontains=search_query) | Q(site_name__icontains=search_query))
        .order_by("site_name", "indus_site_id")[:limit]
    )
    items = [
        {
            "id": site.id,
            "indus_site_id": site.indus_site_id,
            "site_name": site.site_name or "",
            "latitude": float(site.latitude) if site.latitude is not None else None,
            "longitude": float(site.longitude) if site.longitude is not None else None,
        }
        for site in sites
    ]
    return JsonResponse({"count": len(items), "items": items})


@admin_required
def admin_diesel_daily_route_plan(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    transporter_id = request.GET.get("transporter_id", "").strip()
    driver_id = request.GET.get("driver_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()
    date_input = request.GET.get("date", "").strip()
    download = (request.GET.get("download") or "").strip().lower()
    return_to_start = (request.GET.get("return_to_start") or "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }

    target_date = _parse_date_param(date_input, today)
    if not date_input:
        date_input = target_date.isoformat()

    def _plan_redirect_url(
        *,
        target_transporter_id: str | None = None,
        target_driver_id: str | None = None,
        target_vehicle_id: str | None = None,
    ):
        params = {"date": target_date.isoformat()}
        effective_transporter_id = target_transporter_id if target_transporter_id is not None else transporter_id
        effective_driver_id = target_driver_id if target_driver_id is not None else driver_id
        effective_vehicle_id = target_vehicle_id if target_vehicle_id is not None else vehicle_id
        if effective_transporter_id:
            params["transporter_id"] = effective_transporter_id
        if effective_driver_id:
            params["driver_id"] = effective_driver_id
        if effective_vehicle_id:
            params["vehicle_id"] = effective_vehicle_id
        if return_to_start:
            params["return_to_start"] = "1"
        encoded = urlencode(params)
        return f"{reverse('admin_diesel_daily_route_plan')}?{encoded}" if encoded else reverse(
            "admin_diesel_daily_route_plan"
        )

    selected_transporter = (
        Transporter.objects.filter(id=int(transporter_id)).first() if transporter_id.isdigit() else None
    )
    selected_driver = (
        Driver.objects.select_related("user", "transporter", "assigned_vehicle")
        .filter(id=int(driver_id))
        .first()
        if driver_id.isdigit()
        else None
    )

    if selected_driver is not None and selected_transporter is None and selected_driver.transporter_id is not None:
        selected_transporter = selected_driver.transporter
        transporter_id = str(selected_driver.transporter_id)

    diesel_vehicles = Vehicle.objects.select_related("transporter")
    if transporter_id.isdigit():
        diesel_vehicles = diesel_vehicles.filter(transporter_id=int(transporter_id))
    else:
        diesel_vehicles = diesel_vehicles.none()
    diesel_vehicles = diesel_vehicles.order_by("vehicle_number")

    selected_vehicle = None
    if vehicle_id.isdigit():
        selected_vehicle = diesel_vehicles.filter(id=int(vehicle_id)).first()
        if selected_vehicle is None:
            selected_vehicle = (
                Vehicle.objects.select_related("transporter")
                .filter(id=int(vehicle_id))
                .first()
            )

    if selected_vehicle is not None and selected_transporter is None:
        selected_transporter = selected_vehicle.transporter
        transporter_id = str(selected_vehicle.transporter_id)

    if (
        selected_driver is not None
        and selected_vehicle is None
        and selected_driver.assigned_vehicle_id is not None
    ):
        selected_vehicle = selected_driver.assigned_vehicle
        vehicle_id = str(selected_driver.assigned_vehicle_id)

    start_point = None
    if selected_transporter is not None:
        start_point = DieselRouteStartPoint.objects.filter(transporter=selected_transporter).first()

    transporter_drivers = Driver.objects.none()
    if selected_transporter is not None:
        transporter_drivers = Driver.objects.select_related("user", "assigned_vehicle").filter(
            transporter=selected_transporter
        )

    if selected_driver is not None and selected_transporter is not None:
        if selected_driver.transporter_id != selected_transporter.id:
            selected_driver = None
            driver_id = ""

    if request.method == "POST":
        action = (request.POST.get("form_action") or "").strip()

        if action == "save_start_point":
            if selected_transporter is None:
                messages.error(request, "Select a transporter first.")
                return redirect(_plan_redirect_url())
            start_name = (request.POST.get("start_name") or "").strip() or "Depot"
            start_lat_raw = (request.POST.get("start_latitude") or "").strip()
            start_lon_raw = (request.POST.get("start_longitude") or "").strip()
            try:
                start_lat = float(Decimal(start_lat_raw))
                start_lon = float(Decimal(start_lon_raw))
                validate_lat_lon(start_lat, start_lon)
            except (InvalidOperation, ValueError) as exc:
                messages.error(request, f"Invalid start coordinates: {exc}")
                return redirect(_plan_redirect_url())

            DieselRouteStartPoint.objects.update_or_create(
                transporter=selected_transporter,
                defaults={
                    "name": start_name,
                    "latitude": Decimal(str(start_lat)),
                    "longitude": Decimal(str(start_lon)),
                },
            )
            messages.success(request, "Start point saved.")
            return redirect(_plan_redirect_url())

        if selected_vehicle is None:
            messages.error(request, "Select a vehicle to create a daily plan.")
            return redirect(_plan_redirect_url())

        if selected_transporter is None:
            messages.error(request, "Select a transporter first.")
            return redirect(_plan_redirect_url())

        if selected_vehicle.transporter_id != selected_transporter.id:
            messages.error(request, "Selected vehicle does not belong to selected transporter.")
            return redirect(_plan_redirect_url())
        if selected_driver is not None and selected_driver.transporter_id != selected_transporter.id:
            messages.error(request, "Selected driver does not belong to selected transporter.")
            return redirect(_plan_redirect_url())

        plan, _created = DieselDailyRoutePlan.objects.get_or_create(
            vehicle=selected_vehicle,
            plan_date=target_date,
            defaults={
                "transporter": selected_transporter,
                "created_by": request.user,
            },
        )

        if action == "replace_plan_stops":
            plan.stops.all().delete()
            messages.success(request, "Plan stops cleared.")
            return redirect(_plan_redirect_url())

        if action == "delete_stop":
            stop_id = (request.POST.get("stop_id") or "").strip()
            if stop_id.isdigit():
                DieselDailyRoutePlanStop.objects.filter(plan=plan, id=int(stop_id)).delete()
                messages.success(request, "Stop removed.")
            return redirect(_plan_redirect_url())

        if action == "add_manual_stop":
            site_id_raw = (request.POST.get("manual_site_id") or "").strip()
            qty_raw = (request.POST.get("manual_planned_qty") or "").strip()
            notes = (request.POST.get("manual_notes") or "").strip()

            if not site_id_raw:
                messages.error(request, "Search and select a tower site first.")
                return redirect(_plan_redirect_url())

            try:
                site_id_value = validate_indus_site_id(site_id_raw)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect(_plan_redirect_url())

            try:
                planned_qty = Decimal(qty_raw)
            except (InvalidOperation, TypeError):
                messages.error(request, "Enter a valid quantity to add the stop.")
                return redirect(_plan_redirect_url())
            if planned_qty < 0:
                messages.error(request, "Planned quantity cannot be negative.")
                return redirect(_plan_redirect_url())

            tower_site = (
                IndusTowerSite.objects.filter(
                    partner=selected_transporter,
                    indus_site_id__iexact=site_id_value,
                )
                .order_by("id")
                .first()
            )
            if tower_site is None:
                messages.error(request, "Selected site was not found for this transporter.")
                return redirect(_plan_redirect_url())

            existing_stop = (
                DieselDailyRoutePlanStop.objects.filter(
                    plan=plan,
                )
                .filter(
                    Q(tower_site=tower_site) | Q(indus_site_id__iexact=site_id_value)
                )
                .order_by("sequence", "id")
                .first()
            )
            if existing_stop is not None:
                existing_stop.planned_qty = planned_qty
                existing_stop.site_name = tower_site.site_name or existing_stop.site_name
                existing_stop.latitude = tower_site.latitude
                existing_stop.longitude = tower_site.longitude
                existing_stop.notes = notes
                existing_stop.save(
                    update_fields=[
                        "planned_qty",
                        "site_name",
                        "latitude",
                        "longitude",
                        "notes",
                        "updated_at",
                    ]
                )
                messages.success(request, "Planned stop updated.")
                return redirect(_plan_redirect_url())

            next_sequence = (
                plan.stops.aggregate(max_seq=Coalesce(Max("sequence"), 0)).get("max_seq") or 0
            ) + 1
            DieselDailyRoutePlanStop.objects.create(
                plan=plan,
                sequence=next_sequence,
                tower_site=tower_site,
                indus_site_id=site_id_value,
                site_name=tower_site.site_name or "",
                latitude=tower_site.latitude,
                longitude=tower_site.longitude,
                planned_qty=planned_qty,
                notes=notes,
            )
            messages.success(request, "Tower site added to the plan.")
            return redirect(_plan_redirect_url())

        if action in {"import_plan_file", "add_bulk_text"}:
            replace_existing = (request.POST.get("replace_existing") or "").strip() in {"1", "true", "on", "yes"}
            if replace_existing:
                plan.stops.all().delete()

            parsed_rows: list[dict] = []

            def _normalize_header(value: str) -> str:
                return "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "")).strip("_")

            def _row_from_simple_columns(data_row: list[object]) -> dict[str, str]:
                values = ["" if value is None else str(value).strip() for value in data_row]
                return {
                    "indus_site_id": values[0] if len(values) >= 1 else "",
                    "planned_qty": values[1] if len(values) >= 2 else "",
                    "site_name": values[2] if len(values) >= 3 else "",
                    "latitude": values[3] if len(values) >= 4 else "",
                    "longitude": values[4] if len(values) >= 5 else "",
                    "notes": values[5] if len(values) >= 6 else "",
                }

            if action == "add_bulk_text":
                bulk_text = (request.POST.get("bulk_sites") or "").strip()
                if not bulk_text:
                    messages.error(request, "Paste site list first.")
                    return redirect(_plan_redirect_url())

                for raw_line in bulk_text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = [item.strip() for item in line.replace("\t", ",").split(",") if item.strip()]
                    parsed_rows.append(
                        {
                            "indus_site_id": parts[0],
                            "planned_qty": parts[1] if len(parts) >= 2 else "",
                            "site_name": parts[2] if len(parts) >= 3 else "",
                            "latitude": parts[3] if len(parts) >= 4 else "",
                            "longitude": parts[4] if len(parts) >= 5 else "",
                            "notes": parts[5] if len(parts) >= 6 else "",
                        }
                    )
            else:
                uploaded = request.FILES.get("plan_file")
                if uploaded is None:
                    messages.error(request, "Select a CSV/Excel file to import.")
                    return redirect(_plan_redirect_url())

                filename = (uploaded.name or "").lower()
                file_bytes = uploaded.read()
                supported_headers = {
                    "indus_site_id",
                    "site_id",
                    "tower_site_id",
                    "planned_qty",
                    "qty",
                    "quantity",
                    "liters",
                    "fuel_filled",
                    "site_name",
                    "name",
                    "latitude",
                    "lat",
                    "longitude",
                    "lng",
                    "lon",
                    "notes",
                    "remark",
                    "remarks",
                }

                if filename.endswith(".csv"):
                    text = file_bytes.decode("utf-8-sig", errors="replace")
                    raw_rows = list(csv.reader(StringIO(text)))
                    if not raw_rows:
                        messages.error(request, "CSV file is empty.")
                        return redirect(_plan_redirect_url())
                    first_row_headers = [_normalize_header(str(item or "")) for item in raw_rows[0]]
                    has_header_row = any(header in supported_headers for header in first_row_headers)
                    if has_header_row:
                        reader = csv.DictReader(StringIO(text))
                        for row in reader:
                            normalized = {_normalize_header(k): (v or "").strip() for k, v in (row or {}).items()}
                            parsed_rows.append(normalized)
                    else:
                        for data_row in raw_rows:
                            if not any(item is not None and str(item).strip() for item in data_row):
                                continue
                            parsed_rows.append(_row_from_simple_columns(list(data_row)))
                elif filename.endswith(".xlsx"):
                    try:
                        import openpyxl  # type: ignore
                    except Exception:
                        openpyxl = None
                    if openpyxl is None:
                        messages.error(request, "Excel import requires openpyxl. Deploy with updated requirements.")
                        return redirect(_plan_redirect_url())
                    wb = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
                    ws = wb.active
                    rows = list(ws.iter_rows(values_only=True))
                    if not rows:
                        messages.error(request, "Excel file is empty.")
                        return redirect(_plan_redirect_url())
                    headers = [_normalize_header(str(item or "")) for item in rows[0]]
                    has_header_row = any(header in supported_headers for header in headers)
                    data_rows = rows[1:] if has_header_row else rows
                    if has_header_row:
                        for data_row in data_rows:
                            if not any(item is not None and str(item).strip() for item in data_row):
                                continue
                            normalized = {}
                            for idx, header in enumerate(headers):
                                if not header:
                                    continue
                                value = data_row[idx] if idx < len(data_row) else None
                                normalized[header] = "" if value is None else str(value).strip()
                            parsed_rows.append(normalized)
                    else:
                        for data_row in data_rows:
                            if not any(item is not None and str(item).strip() for item in data_row):
                                continue
                            parsed_rows.append(_row_from_simple_columns(list(data_row)))
                else:
                    messages.error(request, "Unsupported file type. Upload .csv or .xlsx.")
                    return redirect(_plan_redirect_url())

            def _get_first(row: dict, keys: list[str]) -> str:
                for key in keys:
                    value = (row.get(key) or "").strip()
                    if value:
                        return value
                return ""

            def _parse_optional_decimal(value: str):
                if not value:
                    return None
                try:
                    return Decimal(value)
                except InvalidOperation:
                    return None

            aggregated: dict[str, dict] = {}
            errors = 0
            zero_qty_count = 0
            for row in parsed_rows:
                site_raw = _get_first(row, ["indus_site_id", "site_id", "tower_site_id"])
                qty_raw = _get_first(row, ["planned_qty", "qty", "quantity", "liters", "fuel_filled"])
                if not site_raw and not qty_raw:
                    continue
                if not site_raw:
                    errors += 1
                    continue
                try:
                    normalized_site_id = validate_indus_site_id(site_raw)
                except ValidationError:
                    errors += 1
                    continue
                if qty_raw:
                    try:
                        qty = Decimal(qty_raw)
                    except InvalidOperation:
                        errors += 1
                        continue
                    if qty < 0:
                        errors += 1
                        continue
                else:
                    qty = Decimal("0.00")
                    zero_qty_count += 1

                site_name = _get_first(row, ["site_name", "name"])
                latitude = _parse_optional_decimal(_get_first(row, ["latitude", "lat"]))
                longitude = _parse_optional_decimal(_get_first(row, ["longitude", "lng", "lon"]))
                notes = _get_first(row, ["notes", "remark", "remarks"])

                key = normalized_site_id.upper()
                existing = aggregated.get(key)
                if existing is None:
                    aggregated[key] = {
                        "indus_site_id": normalized_site_id,
                        "planned_qty": qty,
                        "site_name": site_name,
                        "latitude": latitude,
                        "longitude": longitude,
                        "notes": notes,
                    }
                else:
                    existing["planned_qty"] += qty
                    if site_name and not existing.get("site_name"):
                        existing["site_name"] = site_name
                    if latitude is not None and existing.get("latitude") is None:
                        existing["latitude"] = latitude
                    if longitude is not None and existing.get("longitude") is None:
                        existing["longitude"] = longitude
                    if notes and not existing.get("notes"):
                        existing["notes"] = notes

            if not aggregated:
                messages.error(request, "No valid rows found in file.")
                return redirect(_plan_redirect_url())

            current_max = plan.stops.aggregate(max_seq=Coalesce(Max("sequence"), 0)).get("max_seq") or 0
            to_create: list[DieselDailyRoutePlanStop] = []
            for payload in aggregated.values():
                current_max += 1
                site_id_value = payload["indus_site_id"]
                tower_site = (
                    IndusTowerSite.objects.filter(
                        partner=selected_transporter,
                        indus_site_id__iexact=site_id_value,
                    )
                    .order_by("id")
                    .first()
                )
                to_create.append(
                    DieselDailyRoutePlanStop(
                        plan=plan,
                        sequence=current_max,
                        tower_site=tower_site,
                        indus_site_id=site_id_value,
                        site_name=payload.get("site_name") or "",
                        latitude=payload.get("latitude"),
                        longitude=payload.get("longitude"),
                        planned_qty=payload["planned_qty"],
                        notes=payload.get("notes") or "",
                    )
                )

            DieselDailyRoutePlanStop.objects.bulk_create(to_create, batch_size=400)
            messages.success(request, f"Imported {len(to_create)} site(s).")
            if zero_qty_count:
                messages.info(
                    request,
                    f"{zero_qty_count} site(s) were added without quantity, so planned qty was saved as 0.00.",
                )
            if errors:
                messages.warning(request, f"Skipped {errors} invalid row(s).")
            return redirect(_plan_redirect_url())

        if action == "optimize_and_save":
            ordered_stops = list(
                plan.stops.select_related("tower_site").order_by("sequence", "id")
            )
            with_coords = []
            without_coords = []
            for stop in ordered_stops:
                lat_value = stop.resolved_latitude
                lon_value = stop.resolved_longitude
                if lat_value is None or lon_value is None:
                    without_coords.append(stop)
                else:
                    with_coords.append(stop)

            if len(with_coords) < 2:
                messages.error(request, "Need at least 2 sites with coordinates to optimize.")
                return redirect(_plan_redirect_url())

            start_coordinate = None
            if start_point is not None:
                start_coordinate = (float(start_point.latitude), float(start_point.longitude))

            coords = [(float(item.resolved_latitude), float(item.resolved_longitude)) for item in with_coords]
            ordered_with_coords = None

            if start_coordinate is not None and len(coords) <= MAX_TOWERS_PER_REQUEST:
                try:
                    optimized = optimize_route_path(
                        start=start_coordinate,
                        towers=coords,
                        return_to_start=return_to_start,
                    )
                    optimized_order = [
                        index - 1 for index in optimized["route"] if index != 0
                    ]
                    ordered_with_coords = [with_coords[idx] for idx in optimized_order]
                    if optimized.get("used_fallback"):
                        messages.warning(
                            request,
                            "Smart road route planning was unavailable, so the system used a local fallback order.",
                        )
                    else:
                        messages.success(
                            request,
                            "Optimized route order saved with smart road route planning.",
                        )
                except (RouteOptimizerError, ValueError) as exc:
                    messages.warning(
                        request,
                        f"Smart route planning unavailable ({exc}). Used local route order instead.",
                    )

            if ordered_with_coords is None:
                optimized = optimize_route_order(
                    coords,
                    start=start_coordinate,
                    return_to_start=return_to_start,
                    max_swaps=4000 if len(coords) <= 120 else 2500,
                )
                ordered_with_coords = [with_coords[idx] for idx in optimized.order]
                messages.success(request, "Optimized route order saved.")

            new_sequence = 1
            for stop in ordered_with_coords + without_coords:
                stop.sequence = new_sequence
                new_sequence += 1

            DieselDailyRoutePlanStop.objects.bulk_update(
                ordered_with_coords + without_coords,
                ["sequence"],
                batch_size=400,
            )
            return redirect(_plan_redirect_url())

    plan = None
    stops = []
    if selected_vehicle is not None:
        plan = (
            DieselDailyRoutePlan.objects.select_related("vehicle", "transporter")
            .filter(vehicle=selected_vehicle, plan_date=target_date)
            .first()
        )
        if plan is not None and plan.transporter_id != selected_vehicle.transporter_id:
            plan = None
        if plan is not None:
            stops = list(plan.stops.select_related("tower_site").order_by("sequence", "id"))

    if download in {"template", "csv"}:
        if download == "template" or plan is None:
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="diesel-daily-plan-template.csv"'
            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow(["indus_site_id", "planned_qty", "site_name", "latitude", "longitude", "notes"])
            writer.writerow(["1234567", "40.0", "Site A", "9.971500", "76.298200", ""])
            return response

        response = HttpResponse(content_type="text/csv")
        filename = (
            f"diesel-daily-plan-{plan.vehicle.vehicle_number}-{plan.plan_date.isoformat()}.csv"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["seq", "indus_site_id", "site_name", "planned_qty", "latitude", "longitude", "notes"])
        for stop in stops:
            writer.writerow(
                [
                    stop.sequence,
                    (stop.resolved_indus_site_id or "").strip(),
                    (stop.resolved_site_name or "").strip(),
                    stop.planned_qty,
                    stop.resolved_latitude or "",
                    stop.resolved_longitude or "",
                    (stop.notes or "").strip(),
                ]
            )
        return response

    missing_count = 0
    included_stops: list[DieselDailyRoutePlanStop] = []
    for stop in stops:
        lat_value = stop.resolved_latitude
        lon_value = stop.resolved_longitude
        if lat_value is None or lon_value is None:
            missing_count += 1
        else:
            included_stops.append(stop)

    start_coordinate_payload = None
    start_coordinate = None
    if start_point is not None:
        start_coordinate = (float(start_point.latitude), float(start_point.longitude))
        start_coordinate_payload = {
            "name": start_point.name,
            "latitude": float(start_point.latitude),
            "longitude": float(start_point.longitude),
        }

    estimated_km = None
    route_rows: list[dict] = []
    map_payload = None
    if included_stops:
        coords = [(float(item.resolved_latitude), float(item.resolved_longitude)) for item in included_stops]
        order = list(range(len(coords)))
        legs = format_route_legs(coords, order, start=start_coordinate, return_to_start=return_to_start)
        estimated_km = float(legs[-1]["cumulative_km"]) if legs else 0.0
        if return_to_start and legs and legs[-1].get("is_return_leg"):
            estimated_km = float(legs[-1]["cumulative_km"])

        for leg in legs:
            if leg.get("is_return_leg"):
                route_rows.append(
                    {
                        "seq": leg["seq"],
                        "site_id": "RETURN",
                        "site_name": "Return",
                        "qty": "",
                        "latitude": leg["latitude"],
                        "longitude": leg["longitude"],
                        "leg_km": leg["leg_km"],
                        "cumulative_km": leg["cumulative_km"],
                        "is_return_leg": True,
                    }
                )
                continue
            stop = included_stops[int(leg["idx"])]
            route_rows.append(
                {
                    "seq": stop.sequence,
                    "site_id": (stop.resolved_indus_site_id or "").strip(),
                    "site_name": (stop.resolved_site_name or "").strip(),
                    "qty": float(stop.planned_qty),
                    "latitude": float(stop.resolved_latitude),
                    "longitude": float(stop.resolved_longitude),
                    "leg_km": leg["leg_km"],
                    "cumulative_km": leg["cumulative_km"],
                    "is_return_leg": False,
                }
            )

        map_payload = {
            "stops": [
                {
                    "seq": row["seq"],
                    "site_id": row["site_id"],
                    "site_name": row["site_name"],
                    "qty": row["qty"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "is_return_leg": bool(row.get("is_return_leg")),
                }
                for row in route_rows
            ],
            "start": (
                {"latitude": start_coordinate[0], "longitude": start_coordinate[1]}
                if start_coordinate is not None
                else None
            ),
            "return_to_start": return_to_start,
            "target_date": target_date.isoformat(),
        }

    context = {
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter": selected_transporter,
        "selected_transporter_id": transporter_id,
        "selected_driver": selected_driver,
        "selected_driver_id": driver_id,
        "transporter_drivers": transporter_drivers,
        "diesel_vehicles": diesel_vehicles,
        "selected_vehicle": selected_vehicle,
        "selected_vehicle_id": vehicle_id,
        "date_input": date_input,
        "target_date": target_date,
        "plan": plan,
        "stops": stops,
        "stops_count": len(stops),
        "missing_coords_count": missing_count,
        "start_point": start_point,
        "start_coordinate_payload": start_coordinate_payload,
        "return_to_start": return_to_start,
        "estimated_km": estimated_km,
        "route_rows": route_rows,
        "map_payload": map_payload,
    }
    return _render_admin(request, "admin/diesel_daily_route_plan.html", context)


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
    ).filter(
        date__month=month,
        date__year=year,
        status=Attendance.Status.ON_DUTY,
    )

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
    actor_names = {item.actor.username for item in logs if item.actor}
    context = {
        "query": query,
        "logs": logs,
        "log_count": len(logs),
        "actor_count": len(actor_names),
        "latest_log": logs[0] if logs else None,
    }
    return _render_admin(request, "admin/audit_logs.html", context)


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
