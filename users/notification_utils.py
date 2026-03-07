from calendar import monthrange
from decimal import Decimal
from django.utils import timezone

from attendance.models import Attendance
from attendance.models import DriverDailyAttendanceMark
from drivers.models import Driver
from fuel.analytics import get_vehicle_fuel_status
from fuel.models import FuelRecord
from trips.models import Trip
from users.models import (
    AdminBroadcastNotification,
    AppRelease,
    DriverNotification,
    TransporterNotification,
    User,
    UserDeviceToken,
)
from users.push_service import send_push_to_user

OPEN_RUN_REMINDER_STAGES = [
    (
        300,
        "5h",
        "5-Hour Open Run Reminder",
        "has an open day run for 5 hours. Please ensure it is closed.",
        "Your day run has been open for 5 hours. Close it when duty ends.",
    ),
    (
        480,
        "8h",
        "8-Hour Open Run Reminder",
        "has an open day run for 8 hours. Please ensure it is closed immediately.",
        "Your day run has been open for 8 hours. Please close it now.",
    ),
]
FINAL_CLOSE_REMINDER_TIME = (23, 50)
FUEL_ALERT_THRESHOLDS = [Decimal("10.00"), Decimal("30.00"), Decimal("50.00")]


def _push_for_transporter_notification(notification):
    transporter_user = notification.transporter.user
    send_push_to_user(
        user=transporter_user,
        title=notification.title,
        body=notification.message,
        app_variant=UserDeviceToken.AppVariant.TRANSPORTER,
        data={
            "type": "TRANSPORTER_NOTIFICATION",
            "notification_id": notification.id,
            "notification_type": notification.notification_type,
        },
    )


def _push_for_driver_notification(notification):
    driver_user = notification.driver.user
    send_push_to_user(
        user=driver_user,
        title=notification.title,
        body=notification.message,
        app_variant=UserDeviceToken.AppVariant.DRIVER,
        data={
            "type": "DRIVER_NOTIFICATION",
            "notification_id": notification.id,
            "notification_type": notification.notification_type,
        },
    )


def send_admin_broadcast_push(broadcast):
    if broadcast.audience == AdminBroadcastNotification.Audience.DRIVER:
        users = User.objects.filter(role=User.Role.DRIVER, is_active=True)
    elif broadcast.audience == AdminBroadcastNotification.Audience.TRANSPORTER:
        users = User.objects.filter(role=User.Role.TRANSPORTER, is_active=True)
    else:
        users = User.objects.filter(
            role__in=[User.Role.DRIVER, User.Role.TRANSPORTER],
            is_active=True,
        )

    for user in users.iterator():
        app_variant = (
            UserDeviceToken.AppVariant.DRIVER
            if user.role == User.Role.DRIVER
            else UserDeviceToken.AppVariant.TRANSPORTER
        )
        send_push_to_user(
            user=user,
            title=broadcast.title,
            body=broadcast.message,
            app_variant=app_variant,
            data={
                "type": "SYSTEM_ALERT",
                "notification_type": "SYSTEM_ALERT",
                "broadcast_id": broadcast.id,
            },
        )


def create_app_release_update_notifications(*, release: AppRelease, force_push: bool = False):
    title = "Critical App Update Required" if release.force_update else "App Update Available"
    variant_label = release.get_app_variant_display()
    default_message = (
        release.message.strip()
        or f"{variant_label} version {release.version_name} is available for download."
    )
    now = timezone.now()

    if release.app_variant == AppRelease.AppVariant.DRIVER:
        users = User.objects.filter(role=User.Role.DRIVER, is_active=True).select_related(
            "driver_profile"
        )
        app_variant = UserDeviceToken.AppVariant.DRIVER
        for user in users:
            driver = getattr(user, "driver_profile", None)
            if driver is None:
                continue
            notification, created = DriverNotification.objects.get_or_create(
                event_key=f"app-release-driver:{release.id}:{driver.id}",
                defaults={
                    "driver": driver,
                    "notification_type": DriverNotification.Type.SYSTEM,
                    "title": title,
                    "message": default_message,
                },
            )
            if created or force_push:
                send_push_to_user(
                    user=user,
                    title=notification.title,
                    body=notification.message,
                    app_variant=app_variant,
                    data={
                        "type": "DRIVER_NOTIFICATION",
                        "notification_id": notification.id,
                        "notification_type": notification.notification_type,
                        "target": "APP_UPDATE",
                        "app_variant": "DRIVER",
                        "release_id": release.id,
                    },
                )
    else:
        users = User.objects.filter(
            role=User.Role.TRANSPORTER,
            is_active=True,
        ).select_related("transporter_profile")
        app_variant = UserDeviceToken.AppVariant.TRANSPORTER
        for user in users:
            transporter = getattr(user, "transporter_profile", None)
            if transporter is None:
                continue
            notification, created = TransporterNotification.objects.get_or_create(
                event_key=f"app-release-transporter:{release.id}:{transporter.id}",
                defaults={
                    "transporter": transporter,
                    "notification_type": TransporterNotification.Type.SYSTEM,
                    "title": title,
                    "message": default_message,
                },
            )
            if created or force_push:
                send_push_to_user(
                    user=user,
                    title=notification.title,
                    body=notification.message,
                    app_variant=app_variant,
                    data={
                        "type": "TRANSPORTER_NOTIFICATION",
                        "notification_id": notification.id,
                        "notification_type": notification.notification_type,
                        "target": "APP_UPDATE",
                        "app_variant": "TRANSPORTER",
                        "release_id": release.id,
                    },
                )

    AppRelease.objects.filter(pk=release.pk).update(push_sent_at=now)


def _create_notification(
    *,
    transporter,
    notification_type,
    title,
    message,
    driver=None,
    trip=None,
    event_key=None,
):
    if event_key:
        notification, created = TransporterNotification.objects.get_or_create(
            event_key=event_key,
            defaults={
                "transporter": transporter,
                "driver": driver,
                "trip": trip,
                "notification_type": notification_type,
                "title": title,
                "message": message,
            },
        )
        if created:
            _push_for_transporter_notification(notification)
        return notification

    notification = TransporterNotification.objects.create(
        transporter=transporter,
        driver=driver,
        trip=trip,
        notification_type=notification_type,
        title=title,
        message=message,
    )
    _push_for_transporter_notification(notification)
    return notification


def _create_driver_notification(
    *,
    driver,
    notification_type,
    title,
    message,
    trip=None,
    event_key=None,
):
    if event_key:
        notification, created = DriverNotification.objects.get_or_create(
            event_key=event_key,
            defaults={
                "driver": driver,
                "trip": trip,
                "notification_type": notification_type,
                "title": title,
                "message": message,
            },
        )
        if created:
            _push_for_driver_notification(notification)
        return notification

    notification = DriverNotification.objects.create(
        driver=driver,
        trip=trip,
        notification_type=notification_type,
        title=title,
        message=message,
    )
    _push_for_driver_notification(notification)
    return notification


def create_trip_started_notification(trip):
    transporter = trip.attendance.driver.transporter
    if transporter is None:
        return None
    driver = trip.attendance.driver
    started_time = timezone.localtime(trip.started_at).strftime("%I:%M %p")
    route = f"{trip.start_location} -> {trip.destination}"
    return _create_notification(
        transporter=transporter,
        driver=driver,
        trip=trip,
        notification_type=TransporterNotification.Type.TRIP_STARTED,
        title="Trip Started",
        message=f"{driver.user.username} started trip {route} at {started_time}.",
    )


def create_trip_closed_notification(trip):
    transporter = trip.attendance.driver.transporter
    if transporter is None:
        return None
    driver = trip.attendance.driver
    ended_at = trip.ended_at or timezone.now()
    closed_time = timezone.localtime(ended_at).strftime("%I:%M %p")
    route = f"{trip.start_location} -> {trip.destination}"
    return _create_notification(
        transporter=transporter,
        driver=driver,
        trip=trip,
        notification_type=TransporterNotification.Type.TRIP_CLOSED,
        title="Trip Closed",
        message=(
            f"{driver.user.username} closed trip {route} at {closed_time} "
            f"({trip.total_km} km)."
        ),
    )


def create_attendance_mark_updated_notification(*, mark, previous_status=None):
    driver = mark.driver
    status_label = mark.get_status_display()
    actor = mark.marked_by.username if mark.marked_by else "Transporter"
    previous = (
        DriverDailyAttendanceMark.Status(previous_status).label
        if previous_status in DriverDailyAttendanceMark.Status.values
        else None
    )

    if previous and previous != status_label:
        message = (
            f"{actor} changed your attendance for {mark.date.isoformat()} "
            f"from {previous} to {status_label}."
        )
    else:
        message = f"{actor} marked your attendance as {status_label} for {mark.date.isoformat()}."

    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.ATTENDANCE_MARK_UPDATED,
        title="Attendance Updated",
        message=message,
        event_key=f"attendance-mark:{driver.id}:{mark.date.isoformat()}:{mark.status}",
    )


def create_driver_allocation_welcome_notification(*, driver, transporter):
    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.WELCOME_ALLOCATED,
        title="Welcome to Transporter",
        message=(
            f"You are now allocated to {transporter.company_name}. "
            "You can start trips once attendance is marked present."
        ),
        event_key=(
            f"driver-allocation-welcome:{driver.id}:{transporter.id}:"
            f"{timezone.localdate().isoformat()}"
        ),
    )


def create_salary_paid_notification(*, payment):
    driver = payment.driver
    month_label = f"{payment.salary_month:02d}/{payment.salary_year}"
    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.SALARY_PAID,
        title="Salary Paid",
        message=(
            f"Your salary for {month_label} has been paid. "
            f"Net paid amount: {payment.net_paid_amount}."
        ),
        event_key=f"salary-paid:{payment.id}",
    )


def create_salary_advance_updated_notification(*, advance, action_label):
    driver = advance.driver
    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.ADVANCE_UPDATED,
        title="Salary Advance Updated",
        message=(
            f"{action_label} advance of {advance.amount} on "
            f"{advance.advance_date.isoformat()}."
        ),
        event_key=(
            f"salary-advance:{advance.id}:{action_label.lower().replace(' ', '-')}:"
            f"{advance.updated_at.timestamp()}"
        ),
    )


def create_diesel_module_toggled_notifications(*, transporter, enabled):
    state_text = "enabled" if enabled else "disabled"
    _create_notification(
        transporter=transporter,
        notification_type=TransporterNotification.Type.DIESEL_MODULE_TOGGLED,
        title="Diesel Module Updated",
        message=f"Admin has {state_text} diesel tracking for your transporter.",
        event_key=f"diesel-module:{transporter.id}:{enabled}:{timezone.now().timestamp()}",
    )

    for driver in transporter.drivers.select_related("user").all():
        _create_driver_notification(
            driver=driver,
            notification_type=DriverNotification.Type.DIESEL_MODULE_TOGGLED,
            title="Diesel Module Updated",
            message=f"Admin has {state_text} diesel tracking for your transporter.",
            event_key=f"diesel-module-driver:{driver.id}:{enabled}:{timezone.now().timestamp()}",
        )


def create_transporter_account_status_notification(
    *,
    transporter,
    enabled,
    actor_username,
):
    state_text = "enabled" if enabled else "disabled"
    return _create_notification(
        transporter=transporter,
        notification_type=TransporterNotification.Type.SYSTEM,
        title="Account Access Updated",
        message=(
            f"Admin {actor_username} has {state_text} your transporter account access."
        ),
        event_key=(
            f"transporter-account-status:{transporter.id}:{enabled}:"
            f"{timezone.now().timestamp()}"
        ),
    )


def create_transporter_force_password_reset_notification(
    *,
    transporter,
    actor_username,
):
    return _create_notification(
        transporter=transporter,
        notification_type=TransporterNotification.Type.SYSTEM,
        title="Password Reset Required",
        message=(
            f"Admin {actor_username} forced a password reset. "
            "Use Forgot Password with OTP to set a new password."
        ),
        event_key=(
            f"transporter-force-password-reset:{transporter.id}:"
            f"{timezone.now().timestamp()}"
        ),
    )


def create_driver_account_status_notification(
    *,
    driver,
    enabled,
    actor_username,
):
    state_text = "enabled" if enabled else "disabled"
    notification = _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.SYSTEM,
        title="Account Access Updated",
        message=(
            f"Admin {actor_username} has {state_text} your driver account access."
        ),
        event_key=(
            f"driver-account-status:{driver.id}:{enabled}:"
            f"{timezone.now().timestamp()}"
        ),
    )

    transporter = driver.transporter
    if transporter is not None:
        _create_notification(
            transporter=transporter,
            driver=driver,
            notification_type=TransporterNotification.Type.SYSTEM,
            title="Driver Access Updated",
            message=(
                f"Admin {actor_username} has {state_text} driver "
                f"{driver.user.username}'s account access."
            ),
            event_key=(
                f"driver-account-status-transporter:{driver.id}:{enabled}:"
                f"{timezone.now().timestamp()}"
            ),
        )

    return notification


def create_driver_force_password_reset_notification(
    *,
    driver,
    actor_username,
):
    notification = _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.SYSTEM,
        title="Password Reset Required",
        message=(
            f"Admin {actor_username} forced a password reset. "
            "Use Forgot Password with OTP to set a new password."
        ),
        event_key=(
            f"driver-force-password-reset:{driver.id}:"
            f"{timezone.now().timestamp()}"
        ),
    )

    transporter = driver.transporter
    if transporter is not None:
        _create_notification(
            transporter=transporter,
            driver=driver,
            notification_type=TransporterNotification.Type.SYSTEM,
            title="Driver Password Reset Initiated",
            message=(
                f"Admin {actor_username} forced a password reset for driver "
                f"{driver.user.username}."
            ),
            event_key=(
                f"driver-force-password-reset-transporter:{driver.id}:"
                f"{timezone.now().timestamp()}"
            ),
        )

    return notification


def create_driver_transporter_removed_notification(
    *,
    driver,
    previous_transporter,
    actor_username,
):
    notification = _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.SYSTEM,
        title="Transporter Allocation Removed",
        message=(
            f"{actor_username} removed your allocation from "
            f"{previous_transporter.company_name}."
        ),
        event_key=(
            f"driver-transporter-removed:{driver.id}:{previous_transporter.id}:"
            f"{timezone.now().timestamp()}"
        ),
    )

    _create_notification(
        transporter=previous_transporter,
        driver=driver,
        notification_type=TransporterNotification.Type.SYSTEM,
        title="Driver Allocation Removed",
        message=(
            f"{actor_username} removed driver "
            f"{driver.user.username} from your transporter."
        ),
        event_key=(
            f"driver-removed-from-transporter:{driver.id}:{previous_transporter.id}:"
            f"{timezone.now().timestamp()}"
        ),
    )
    return notification


def create_fuel_anomaly_notification(*, fuel_record, current_mileage, baseline_mileage):
    driver = fuel_record.driver
    transporter = driver.transporter
    if transporter is None:
        return None

    message = (
        f"Low mileage anomaly for {fuel_record.vehicle.vehicle_number}: "
        f"current {current_mileage:.2f} km/l, baseline {baseline_mileage:.2f} km/l."
    )
    _create_notification(
        transporter=transporter,
        driver=driver,
        notification_type=TransporterNotification.Type.FUEL_ANOMALY,
        title="Fuel Anomaly Alert",
        message=message,
        event_key=f"fuel-anomaly-transporter:{fuel_record.id}",
    )
    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.FUEL_ANOMALY,
        title="Fuel Anomaly Alert",
        message=message,
        event_key=f"fuel-anomaly-driver:{fuel_record.id}",
    )


def detect_and_notify_fuel_anomaly(fuel_record):
    if fuel_record.entry_type != FuelRecord.EntryType.VEHICLE_FILLING:
        return None
    if fuel_record.odometer_km is None or float(fuel_record.liters or 0) <= 0:
        return None

    previous = (
        FuelRecord.objects.filter(
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            vehicle=fuel_record.vehicle,
            odometer_km__isnull=False,
            created_at__lt=fuel_record.created_at,
        )
        .order_by("-created_at")
        .first()
    )
    if previous is None or previous.odometer_km is None:
        return None

    current_delta = fuel_record.odometer_km - previous.odometer_km
    if current_delta < 20:
        return None

    current_mileage = current_delta / float(fuel_record.liters)
    if current_mileage <= 0:
        return None

    history = list(
        FuelRecord.objects.filter(
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            vehicle=fuel_record.vehicle,
            odometer_km__isnull=False,
            created_at__lt=fuel_record.created_at,
        )
        .order_by("-created_at")[:5]
    )
    baseline_samples = []
    for index in range(len(history) - 1):
        newer = history[index]
        older = history[index + 1]
        if newer.odometer_km is None or older.odometer_km is None:
            continue
        km_delta = newer.odometer_km - older.odometer_km
        liters = float(newer.liters or 0)
        if km_delta < 20 or liters <= 0:
            continue
        baseline_samples.append(km_delta / liters)

    if not baseline_samples:
        return None

    baseline_mileage = sum(baseline_samples) / len(baseline_samples)
    is_anomaly = current_mileage < max(1.5, baseline_mileage * 0.6)
    if not is_anomaly:
        return None

    return create_fuel_anomaly_notification(
        fuel_record=fuel_record,
        current_mileage=current_mileage,
        baseline_mileage=baseline_mileage,
    )


def _monitored_vehicle_for_driver(driver):
    if driver.transporter_id is None:
        return None

    active_attendance = (
        Attendance.objects.select_related("vehicle")
        .filter(
            driver=driver,
            ended_at__isnull=True,
            vehicle__transporter_id=driver.transporter_id,
        )
        .order_by("-started_at")
        .first()
    )
    if active_attendance is not None:
        return active_attendance.vehicle

    if (
        driver.assigned_vehicle_id is not None
        and driver.assigned_vehicle is not None
        and driver.assigned_vehicle.transporter_id == driver.transporter_id
    ):
        active_driver_for_assigned = (
            Attendance.objects.select_related("driver", "driver__user")
            .filter(
                vehicle=driver.assigned_vehicle,
                ended_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )
        if (
            active_driver_for_assigned is None
            or active_driver_for_assigned.driver_id == driver.id
        ):
            return driver.assigned_vehicle

    latest_attendance = (
        Attendance.objects.select_related("vehicle")
        .filter(
            driver=driver,
            vehicle__transporter_id=driver.transporter_id,
        )
        .order_by("-date", "-ended_at", "-started_at", "-id")
        .first()
    )
    if latest_attendance is not None:
        active_driver_for_vehicle = (
            Attendance.objects.select_related("driver")
            .filter(
                vehicle=latest_attendance.vehicle,
                ended_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )
        if (
            active_driver_for_vehicle is None
            or active_driver_for_vehicle.driver_id == driver.id
        ):
            return latest_attendance.vehicle

    return None


def _fuel_alert_slot(now, *, last_fill_date):
    today = now.date()
    if now.hour >= 18:
        return "18", "6:00 PM", today
    if now.hour >= 9 and last_fill_date is not None and last_fill_date < today:
        return "09", "9:00 AM", today
    return None, None, today


def _fuel_alert_stage(percent_left):
    for threshold in FUEL_ALERT_THRESHOLDS:
        if percent_left <= threshold:
            return int(threshold)
    return None


def ensure_fuel_level_alerts_for_driver(driver, current_time=None):
    now = current_time or timezone.localtime()
    vehicle = _monitored_vehicle_for_driver(driver)
    if vehicle is None:
        return None

    snapshot = get_vehicle_fuel_status(vehicle)
    if snapshot is None:
        return None

    threshold = _fuel_alert_stage(snapshot.estimated_fuel_left_percent)
    due_tomorrow = (
        snapshot.estimated_days_left is not None
        and snapshot.estimated_days_left <= Decimal("1.0")
    )
    if threshold is None and not due_tomorrow:
        return None

    slot_key, slot_label, event_date = _fuel_alert_slot(
        now,
        last_fill_date=snapshot.last_fill_date,
    )
    if slot_key is None:
        return None

    severity_key = f"{threshold or '1d'}"
    event_key = (
        f"fuel-level:{vehicle.id}:{driver.id}:{slot_key}:"
        f"{event_date.isoformat()}:{severity_key}"
    )

    if threshold is not None and threshold <= 10:
        title = "Critical Fuel Alert"
    elif threshold is not None and threshold <= 30:
        title = "Low Fuel Alert"
    else:
        title = "Fuel Refill Reminder"

    message = (
        f"{slot_label} fuel check for {vehicle.vehicle_number}: "
        f"about {snapshot.estimated_fuel_left_liters} L left "
        f"({snapshot.estimated_fuel_left_percent}% of approx "
        f"{snapshot.estimated_tank_capacity_liters} L tank), around "
        f"{snapshot.estimated_km_left} km remaining at "
        f"{snapshot.average_mileage_km_per_liter} km/l."
    )
    if due_tomorrow:
        message = f"{message} Refill by tomorrow based on recent usage."

    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.SYSTEM,
        title=title,
        message=message,
        event_key=event_key,
    )


def ensure_start_day_reminder_for_transporter(transporter, current_time=None):
    now = current_time or timezone.localtime()
    if now.hour < 10:
        return None

    active_drivers = list(
        Driver.objects.select_related("user").filter(
            transporter=transporter,
            is_active=True,
            user__is_active=True,
        )
    )
    if not active_drivers:
        return None

    today = now.date()
    started_driver_ids = set(
        Attendance.objects.filter(
            driver__in=active_drivers,
            date=today,
        ).values_list("driver_id", flat=True)
    )
    missing_drivers = [driver for driver in active_drivers if driver.id not in started_driver_ids]
    if not missing_drivers:
        return None

    names = ", ".join(driver.user.username for driver in missing_drivers[:3])
    if len(missing_drivers) > 3:
        names = f"{names} and {len(missing_drivers) - 3} more"

    return _create_notification(
        transporter=transporter,
        notification_type=TransporterNotification.Type.START_DAY_REMINDER,
        title="10:00 AM Reminder",
        message=f"{len(missing_drivers)} drivers have not marked Start Day: {names}.",
        event_key=f"start-day-reminder:{transporter.id}:{today.isoformat()}",
    )


def ensure_start_day_missed_for_driver(driver, current_time=None):
    now = current_time or timezone.localtime()
    if now.hour < 10:
        return None

    today = now.date()
    if Attendance.objects.filter(driver=driver, date=today).exists():
        return None

    mark = DriverDailyAttendanceMark.objects.filter(
        driver=driver,
        transporter=driver.transporter,
        date=today,
    ).first()
    if mark is not None and mark.status in {
        DriverDailyAttendanceMark.Status.ABSENT,
        DriverDailyAttendanceMark.Status.LEAVE,
    }:
        return None

    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.START_DAY_MISSED,
        title="Start Day Reminder",
        message="You missed Start Day cutoff time. Mark Start Day to continue.",
        event_key=f"driver-start-day-missed:{driver.id}:{today.isoformat()}",
    )


def _elapsed_minutes(now, started_at):
    return int((now - started_at).total_seconds() // 60)


def _format_duration(minutes):
    hours = minutes // 60
    rem = minutes % 60
    if hours <= 0:
        return f"{rem} min"
    return f"{hours}h {rem}m"


def ensure_trip_overdue_for_transporter(transporter, current_time=None):
    now = current_time or timezone.now()
    open_trips = (
        Trip.objects.select_related("attendance", "attendance__driver", "attendance__driver__user")
        .filter(
            attendance__driver__transporter=transporter,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            parent_trip__isnull=True,
        )
        .order_by("started_at")
    )

    created_count = 0
    for trip in open_trips:
        elapsed_minutes = _elapsed_minutes(now, trip.started_at)
        driver = trip.attendance.driver
        duration_text = _format_duration(elapsed_minutes)
        for threshold_minutes, stage_key, title, transporter_template, _ in OPEN_RUN_REMINDER_STAGES:
            if elapsed_minutes < threshold_minutes:
                continue
            event_key = f"trip-overdue-transporter:{trip.id}:{stage_key}"
            if TransporterNotification.objects.filter(event_key=event_key).exists():
                continue
            _create_notification(
                transporter=transporter,
                driver=driver,
                trip=trip,
                notification_type=TransporterNotification.Type.TRIP_OVERDUE,
                title=title,
                message=(
                    f"{driver.user.username} {transporter_template} "
                    f"Current open duration: {duration_text}."
                ),
                event_key=event_key,
            )
            created_count += 1
    return created_count


def ensure_trip_overdue_for_driver(driver, current_time=None):
    now = current_time or timezone.now()
    open_trips = (
        Trip.objects.select_related("attendance", "attendance__driver")
        .filter(
            attendance__driver=driver,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            parent_trip__isnull=True,
        )
        .order_by("started_at")
    )

    created_count = 0
    for trip in open_trips:
        elapsed_minutes = _elapsed_minutes(now, trip.started_at)
        duration_text = _format_duration(elapsed_minutes)
        for threshold_minutes, stage_key, title, _, driver_template in OPEN_RUN_REMINDER_STAGES:
            if elapsed_minutes < threshold_minutes:
                continue
            event_key = f"trip-overdue-driver:{trip.id}:{stage_key}"
            if DriverNotification.objects.filter(event_key=event_key).exists():
                continue
            _create_driver_notification(
                driver=driver,
                trip=trip,
                notification_type=DriverNotification.Type.TRIP_OVERDUE,
                title=title,
                message=f"{driver_template} Current open duration: {duration_text}.",
                event_key=event_key,
            )
            created_count += 1
    return created_count


def ensure_open_trip_alerts_for_transporter(transporter, current_time=None):
    now = current_time or timezone.localtime()
    if (now.hour, now.minute) < FINAL_CLOSE_REMINDER_TIME:
        return 0

    today = now.date()
    open_trips = (
        Trip.objects.select_related("attendance", "attendance__driver", "attendance__driver__user")
        .filter(
            attendance__driver__transporter=transporter,
            attendance__date=today,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            parent_trip__isnull=True,
        )
        .order_by("started_at")
    )

    created_count = 0
    for trip in open_trips:
        driver = trip.attendance.driver
        started_time = timezone.localtime(trip.started_at).strftime("%I:%M %p")
        event_key = f"open-trip-alert:{trip.id}:{today.isoformat()}"
        if TransporterNotification.objects.filter(event_key=event_key).exists():
            continue
        _create_notification(
            transporter=transporter,
            driver=driver,
            trip=trip,
            notification_type=TransporterNotification.Type.OPEN_TRIP_ALERT,
            title="Final Close Reminder",
            message=(
                f"{driver.user.username} started duty at {started_time} "
                f"and it is still open near day end. Close the run before 11:59 PM."
            ),
            event_key=event_key,
        )
        created_count += 1
    return created_count


def ensure_day_close_reminders_for_driver(driver, current_time=None):
    now = current_time or timezone.localtime()
    open_day_trips = (
        Trip.objects.select_related("attendance")
        .filter(
            attendance__driver=driver,
            status=Trip.Status.OPEN,
            is_day_trip=True,
            parent_trip__isnull=True,
        )
        .order_by("started_at")
    )
    if not open_day_trips.exists():
        return 0

    if (now.hour, now.minute) < FINAL_CLOSE_REMINDER_TIME:
        return 0

    created_count = 0
    for trip in open_day_trips:
        event_key = f"driver-day-close-reminder:{trip.id}:{now.date().isoformat()}"
        if DriverNotification.objects.filter(event_key=event_key).exists():
            continue
        _create_driver_notification(
            driver=driver,
            trip=trip,
            notification_type=DriverNotification.Type.TRIP_OVERDUE,
            title="Final Close Reminder",
            message="Your day run is still open near midnight. Close it before 11:59 PM.",
            event_key=event_key,
        )
        created_count += 1
    return created_count


def ensure_month_end_reminder_for_transporter(transporter, current_time=None):
    now = current_time or timezone.localtime()
    today = now.date()
    if now.hour < 18:
        return None

    last_day = monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return None

    notification = _create_notification(
        transporter=transporter,
        notification_type=TransporterNotification.Type.MONTH_END_REMINDER,
        title="Month-End Reminder",
        message=(
            "Month is ending today. Generate trip sheet and fuel sheet "
            "before closing operations."
        ),
        event_key=f"month-end-transporter:{transporter.id}:{today.year}-{today.month}",
    )
    for driver in transporter.drivers.select_related("user").all():
        _create_driver_notification(
            driver=driver,
            notification_type=DriverNotification.Type.MONTH_END_REMINDER,
            title="Month-End Reminder",
            message="Month end reached. Ensure all trip and fuel entries are complete.",
            event_key=f"month-end-driver:{driver.id}:{today.year}-{today.month}",
        )
    return notification


def ensure_month_end_reminder_for_driver(driver, current_time=None):
    now = current_time or timezone.localtime()
    today = now.date()
    if now.hour < 18:
        return None

    last_day = monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return None

    return _create_driver_notification(
        driver=driver,
        notification_type=DriverNotification.Type.MONTH_END_REMINDER,
        title="Month-End Reminder",
        message="Month end reached. Ensure all trip and fuel entries are complete.",
        event_key=f"month-end-driver:{driver.id}:{today.year}-{today.month}",
    )


def ensure_time_based_transporter_notifications(transporter, current_time=None):
    ensure_start_day_reminder_for_transporter(transporter, current_time=current_time)
    ensure_open_trip_alerts_for_transporter(transporter, current_time=current_time)
    ensure_trip_overdue_for_transporter(transporter, current_time=current_time)
    ensure_month_end_reminder_for_transporter(transporter, current_time=current_time)


def ensure_time_based_driver_notifications(driver, current_time=None):
    ensure_start_day_missed_for_driver(driver, current_time=current_time)
    ensure_trip_overdue_for_driver(driver, current_time=current_time)
    ensure_day_close_reminders_for_driver(driver, current_time=current_time)
    ensure_fuel_level_alerts_for_driver(driver, current_time=current_time)
    ensure_month_end_reminder_for_driver(driver, current_time=current_time)
