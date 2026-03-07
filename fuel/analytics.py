from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from attendance.models import Attendance
from fuel.models import FuelRecord
from tripmate.odometer_utils import get_latest_vehicle_odometer_point

TWO_DP = Decimal("0.01")
ONE_DP = Decimal("0.1")
ZERO = Decimal("0.00")


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantize(value: Decimal, pattern: Decimal = TWO_DP) -> Decimal:
    return value.quantize(pattern, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VehicleFuelStatus:
    average_mileage_km_per_liter: Decimal
    estimated_tank_capacity_liters: Decimal
    tank_capacity_source: str
    estimated_fuel_after_last_fill_liters: Decimal
    estimated_fuel_left_liters: Decimal
    estimated_fuel_left_percent: Decimal
    estimated_km_left: int
    km_since_last_fill: int
    latest_odometer_km: int | None
    last_fill_odometer_km: int | None
    last_fill_date: timezone.datetime.date | None
    last_fill_liters: Decimal | None
    estimated_days_left: Decimal | None
    recent_daily_average_km: Decimal | None


def _vehicle_fill_records(vehicle):
    return list(
        FuelRecord.objects.filter(
            vehicle=vehicle,
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
            odometer_km__isnull=False,
        )
        .order_by("date", "created_at", "id")
        .only("id", "vehicle_id", "date", "created_at", "liters", "odometer_km")
    )


def _valid_mileage_samples(records):
    samples = []
    for index in range(1, len(records)):
        previous = records[index - 1]
        current = records[index]
        if previous.odometer_km is None or current.odometer_km is None:
            continue
        delta_km = current.odometer_km - previous.odometer_km
        liters = _decimal(current.liters or 0)
        if delta_km <= 0 or liters <= 0:
            continue
        samples.append(
            {
                "previous": previous,
                "current": current,
                "delta_km": delta_km,
                "liters": liters,
                "mileage": _decimal(delta_km) / liters,
            }
        )
    return samples


def calculate_vehicle_average_mileage(vehicle, sample_limit: int = 5) -> Decimal | None:
    samples = _valid_mileage_samples(_vehicle_fill_records(vehicle))
    if not samples:
        return None
    if sample_limit > 0:
        samples = samples[-sample_limit:]
    average = sum((item["mileage"] for item in samples), ZERO) / _decimal(len(samples))
    if average <= 0:
        return None
    return _quantize(average)


def _estimate_capacity_from_history(records, average_mileage: Decimal) -> Decimal | None:
    if not records:
        return None

    max_fill = max((_decimal(record.liters or 0) for record in records), default=ZERO)
    if max_fill <= 0:
        return None
    if average_mileage <= 0:
        return _quantize(max_fill)

    capacity = max_fill
    for _ in range(4):
        derived_max = capacity
        remaining_after_fill = ZERO
        previous = None

        for record in records:
            liters = _decimal(record.liters or 0)
            if previous is None or previous.odometer_km is None or record.odometer_km is None:
                remaining_before_fill = ZERO
            else:
                delta_km = max(record.odometer_km - previous.odometer_km, 0)
                consumed = _decimal(delta_km) / average_mileage if average_mileage > 0 else ZERO
                remaining_before_fill = max(remaining_after_fill - consumed, ZERO)

            unclamped_after_fill = remaining_before_fill + liters
            if unclamped_after_fill > derived_max:
                derived_max = unclamped_after_fill
            remaining_after_fill = min(capacity, unclamped_after_fill)
            previous = record

        if derived_max <= capacity:
            break
        capacity = derived_max

    return _quantize(capacity)


def _resolved_tank_capacity(vehicle, records, average_mileage: Decimal):
    manual_capacity = getattr(vehicle, "tank_capacity_liters", None)
    max_fill = max((_decimal(record.liters or 0) for record in records), default=ZERO)
    if manual_capacity is not None:
        capacity = max(_decimal(manual_capacity), max_fill)
        if capacity > 0:
            return _quantize(capacity), "manual"

    estimated = _estimate_capacity_from_history(records, average_mileage)
    if estimated is None or estimated <= 0:
        return None, None
    return estimated, "estimated"


def _estimate_recent_daily_average_km(vehicle, window_days: int = 14) -> Decimal | None:
    start_date = timezone.localdate() - timedelta(days=window_days - 1)
    attendances = (
        Attendance.objects.filter(
            vehicle=vehicle,
            date__gte=start_date,
            end_km__isnull=False,
        )
        .only("date", "start_km", "end_km")
        .order_by("-date", "-ended_at", "-started_at", "-id")
    )
    km_by_date: dict = {}
    for attendance in attendances:
        total_km = max((attendance.end_km or attendance.start_km) - attendance.start_km, 0)
        if total_km <= 0:
            continue
        km_by_date[attendance.date] = km_by_date.get(attendance.date, 0) + total_km

    if not km_by_date:
        return None

    total_km = sum(km_by_date.values())
    average = _decimal(total_km) / _decimal(len(km_by_date))
    if average <= 0:
        return None
    return _quantize(average)


def get_vehicle_fuel_status(vehicle) -> VehicleFuelStatus | None:
    records = _vehicle_fill_records(vehicle)
    if len(records) < 2:
        return None

    average_mileage = calculate_vehicle_average_mileage(vehicle)
    if average_mileage is None or average_mileage <= 0:
        return None

    capacity, capacity_source = _resolved_tank_capacity(vehicle, records, average_mileage)
    if capacity is None or capacity <= 0:
        return None

    remaining_after_fill = ZERO
    previous = None
    for record in records:
        liters = _decimal(record.liters or 0)
        if previous is None or previous.odometer_km is None or record.odometer_km is None:
            remaining_before_fill = ZERO
        else:
            delta_km = max(record.odometer_km - previous.odometer_km, 0)
            consumed = _decimal(delta_km) / average_mileage
            remaining_before_fill = max(remaining_after_fill - consumed, ZERO)
        remaining_after_fill = min(capacity, remaining_before_fill + liters)
        previous = record

    last_fill = records[-1]
    last_fill_odometer = int(last_fill.odometer_km or 0)
    latest_point = get_latest_vehicle_odometer_point(vehicle)
    latest_odometer = last_fill_odometer
    if latest_point is not None and latest_point.value is not None:
        latest_odometer = max(int(latest_point.value), last_fill_odometer)

    km_since_last_fill = max(latest_odometer - last_fill_odometer, 0)
    consumed_since_last_fill = _decimal(km_since_last_fill) / average_mileage
    remaining_now = max(remaining_after_fill - consumed_since_last_fill, ZERO)

    percent_left = ZERO
    if capacity > 0:
        percent_left = min((_decimal(100) * remaining_now / capacity), _decimal(100))

    km_left = int(
        max(remaining_now * average_mileage, ZERO).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )
    recent_daily_average = _estimate_recent_daily_average_km(vehicle)
    estimated_days_left = None
    if recent_daily_average is not None and recent_daily_average > 0:
        estimated_days_left = _quantize(
            _decimal(km_left) / recent_daily_average,
            ONE_DP,
        )

    return VehicleFuelStatus(
        average_mileage_km_per_liter=_quantize(average_mileage),
        estimated_tank_capacity_liters=_quantize(capacity),
        tank_capacity_source=capacity_source or "estimated",
        estimated_fuel_after_last_fill_liters=_quantize(remaining_after_fill),
        estimated_fuel_left_liters=_quantize(remaining_now),
        estimated_fuel_left_percent=_quantize(percent_left),
        estimated_km_left=km_left,
        km_since_last_fill=km_since_last_fill,
        latest_odometer_km=latest_odometer,
        last_fill_odometer_km=last_fill_odometer,
        last_fill_date=last_fill.date,
        last_fill_liters=_quantize(_decimal(last_fill.liters or 0)),
        estimated_days_left=estimated_days_left,
        recent_daily_average_km=recent_daily_average,
    )
