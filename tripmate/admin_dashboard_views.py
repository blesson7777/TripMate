from __future__ import annotations

import csv
from datetime import date, timedelta
from functools import wraps
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from attendance.models import Attendance
from drivers.models import Driver
from fuel.models import FuelRecord
from trips.models import Trip
from users.models import Transporter, User
from vehicles.models import Vehicle


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
            "trips": Trip.objects.filter(attendance__driver__transporter=transporter_profile).count(),
            "fuel_records": FuelRecord.objects.filter(driver__transporter=transporter_profile).count(),
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
    messages.info(
        request,
        f"Password reset dispatch is not configured yet for '{target_user.username}'.",
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
def admin_vehicles(request: HttpRequest) -> HttpResponse:
    create_form = {
        "transporter_id": "",
        "vehicle_number": "",
        "model": "",
        "status": Vehicle.Status.ACTIVE,
    }

    if request.method == "POST" and request.POST.get("form_action") == "create_vehicle":
        transporter_id_raw = request.POST.get("transporter_id", "").strip()
        vehicle_number = request.POST.get("vehicle_number", "").strip()
        model = request.POST.get("model", "").strip()
        status_value = request.POST.get("status", Vehicle.Status.ACTIVE).strip()

        create_form = {
            "transporter_id": transporter_id_raw,
            "vehicle_number": vehicle_number,
            "model": model,
            "status": status_value,
        }

        transporter = None
        if transporter_id_raw.isdigit():
            transporter = Transporter.objects.filter(id=int(transporter_id_raw)).first()

        valid_statuses = {choice[0] for choice in Vehicle.Status.choices}

        if not transporter:
            messages.error(request, "Select a valid transporter.")
        elif not vehicle_number or not model:
            messages.error(request, "Vehicle number and model are required.")
        elif status_value not in valid_statuses:
            messages.error(request, "Invalid vehicle status.")
        else:
            try:
                Vehicle.objects.create(
                    transporter=transporter,
                    vehicle_number=vehicle_number,
                    model=model,
                    status=status_value,
                )
                messages.success(request, f"Vehicle '{vehicle_number}' created successfully.")
                return redirect("admin_vehicles")
            except IntegrityError:
                messages.error(
                    request,
                    "Vehicle number already exists for the selected transporter.",
                )

    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    status_filter = request.GET.get("status", "").strip()

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

    context = {
        "query": query,
        "vehicles": vehicles.order_by("vehicle_number")[:400],
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "selected_status": status_filter,
        "status_choices": Vehicle.Status.choices,
        "total_vehicles": Vehicle.objects.count(),
        "active_vehicles": Vehicle.objects.filter(status=Vehicle.Status.ACTIVE).count(),
        "maintenance_vehicles": Vehicle.objects.filter(status=Vehicle.Status.MAINTENANCE).count(),
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
    }
    return _render_admin(request, "admin/drivers.html", context)


@admin_required
def admin_attendance(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    date_filter = _parse_date_param(request.GET.get("date"), today)
    transporter_id = request.GET.get("transporter_id", "").strip()
    status_filter = request.GET.get("status", "").strip()

    attendances = Attendance.objects.select_related(
        "driver", "driver__user", "vehicle", "vehicle__transporter"
    ).prefetch_related("trips")

    attendances = attendances.filter(date=date_filter)

    if transporter_id.isdigit():
        attendances = attendances.filter(driver__transporter_id=int(transporter_id))

    if status_filter in {choice[0] for choice in Attendance.Status.choices}:
        attendances = attendances.filter(status=status_filter)

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

    context = {
        "date_filter": date_filter,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "selected_status": status_filter,
        "status_choices": Attendance.Status.choices,
        "attendance_rows": attendance_rows,
        "total_rows": len(attendance_rows),
    }
    return _render_admin(request, "admin/attendance.html", context)


@admin_required
def admin_trips(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_filter = _parse_date_param(request.GET.get("date"), timezone.localdate())

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
        trips = trips.filter(attendance__driver__transporter_id=int(transporter_id))

    if request.GET.get("date"):
        trips = trips.filter(attendance__date=date_filter)

    trip_rows = list(trips.order_by("-created_at")[:500])

    context = {
        "query": query,
        "date_filter": request.GET.get("date", ""),
        "trips": trip_rows,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "total_km": sum(item.total_km for item in trip_rows),
    }
    return _render_admin(request, "admin/trips.html", context)


@admin_required
def admin_fuel_records(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    transporter_id = request.GET.get("transporter_id", "").strip()
    date_filter = _parse_date_param(request.GET.get("date"), timezone.localdate())

    fuel_records = FuelRecord.objects.select_related(
        "driver", "driver__user", "vehicle", "attendance", "vehicle__transporter"
    )

    if query:
        fuel_records = fuel_records.filter(
            Q(driver__user__username__icontains=query)
            | Q(vehicle__vehicle_number__icontains=query)
        )

    if transporter_id.isdigit():
        fuel_records = fuel_records.filter(driver__transporter_id=int(transporter_id))

    if request.GET.get("date"):
        fuel_records = fuel_records.filter(date=date_filter)

    rows = list(fuel_records.order_by("-date", "-created_at")[:500])
    total_amount = sum(float(item.amount) for item in rows)

    context = {
        "query": query,
        "date_filter": request.GET.get("date", ""),
        "fuel_records": rows,
        "transporters": Transporter.objects.order_by("company_name"),
        "selected_transporter_id": transporter_id,
        "total_amount": total_amount,
    }
    return _render_admin(request, "admin/fuel_records.html", context)


@admin_required
def admin_monthly_reports(request: HttpRequest) -> HttpResponse:
    month, year = _parse_month_year(request)
    transporter_id = request.GET.get("transporter_id", "").strip()
    vehicle_id = request.GET.get("vehicle_id", "").strip()

    attendances = Attendance.objects.select_related(
        "driver",
        "driver__user",
        "vehicle",
        "vehicle__transporter",
    ).filter(date__month=month, date__year=year)

    if transporter_id.isdigit():
        attendances = attendances.filter(vehicle__transporter_id=int(transporter_id))

    if vehicle_id.isdigit():
        attendances = attendances.filter(vehicle_id=int(vehicle_id))

    rows = []
    total_km = 0
    for item in attendances.order_by("date", "vehicle__vehicle_number"):
        end_km = item.end_km if item.end_km is not None else item.start_km
        distance = max(end_km - item.start_km, 0)
        total_km += distance
        rows.append(
            {
                "date": item.date,
                "vehicle_number": item.vehicle.vehicle_number,
                "driver_name": item.driver.user.username,
                "start_km": item.start_km,
                "end_km": end_km,
                "total_km": distance,
            }
        )

    summary_map: dict[str, dict] = {}
    for row in rows:
        bucket = summary_map.setdefault(
            row["vehicle_number"],
            {"vehicle_number": row["vehicle_number"], "days": 0, "total_km": 0},
        )
        bucket["days"] += 1
        bucket["total_km"] += row["total_km"]

    context = {
        "month": month,
        "year": year,
        "selected_transporter_id": transporter_id,
        "selected_vehicle_id": vehicle_id,
        "transporters": Transporter.objects.order_by("company_name"),
        "vehicles": Vehicle.objects.select_related("transporter").order_by("vehicle_number"),
        "rows": rows,
        "total_days": len(rows),
        "total_km": total_km,
        "summary_rows": sorted(summary_map.values(), key=lambda row: row["vehicle_number"]),
    }
    return _render_admin(request, "admin/monthly_reports.html", context)


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
        writer.writerow(["id", "vehicle_number", "model", "status", "transporter"])
        for vehicle in Vehicle.objects.select_related("transporter").order_by("vehicle_number"):
            writer.writerow(
                [vehicle.id, vehicle.vehicle_number, vehicle.model, vehicle.status, vehicle.transporter.company_name]
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
