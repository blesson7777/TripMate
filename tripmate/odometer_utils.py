from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OdometerPoint:
    value: int
    recorded_at: datetime
    source: str


def get_latest_vehicle_odometer_point(vehicle) -> OdometerPoint | None:
    from fuel.models import FuelRecord
    from attendance.models import Attendance
    from trips.models import Trip

    points: list[OdometerPoint] = []

    latest_attendance = (
        Attendance.objects.filter(vehicle=vehicle)
        .order_by("-date", "-ended_at", "-started_at", "-id")
        .first()
    )
    if latest_attendance is not None:
        attendance_value = latest_attendance.end_km
        if attendance_value is None:
            attendance_value = latest_attendance.start_km
        attendance_time = latest_attendance.ended_at or latest_attendance.started_at
        if attendance_value is not None and attendance_time is not None:
            points.append(
                OdometerPoint(
                    value=int(attendance_value),
                    recorded_at=attendance_time,
                    source="attendance",
                )
            )

    latest_trip = (
        Trip.objects.filter(attendance__vehicle=vehicle)
        .order_by("-ended_at", "-started_at", "-created_at", "-id")
        .first()
    )
    if latest_trip is not None:
        trip_value = latest_trip.end_km
        if trip_value is None:
            trip_value = latest_trip.start_km
        trip_time = latest_trip.ended_at or latest_trip.started_at or latest_trip.created_at
        if trip_value is not None and trip_time is not None:
            points.append(
                OdometerPoint(
                    value=int(trip_value),
                    recorded_at=trip_time,
                    source="trip",
                )
            )

    latest_fuel = (
        FuelRecord.objects.filter(vehicle=vehicle)
        .order_by("-fill_date", "-created_at", "-id")
        .first()
    )
    if latest_fuel is not None:
        fuel_value = latest_fuel.odometer_km
        if fuel_value is None:
            fuel_value = latest_fuel.end_km
        if fuel_value is None:
            fuel_value = latest_fuel.start_km
        fuel_time = latest_fuel.created_at
        if fuel_value is not None and fuel_time is not None:
            points.append(
                OdometerPoint(
                    value=int(fuel_value),
                    recorded_at=fuel_time,
                    source="fuel",
                )
            )

    if not points:
        return None

    points.sort(key=lambda item: (item.recorded_at, item.value))
    return points[-1]


def get_latest_vehicle_odometer(vehicle) -> int | None:
    point = get_latest_vehicle_odometer_point(vehicle)
    if point is None:
        return None
    return point.value
