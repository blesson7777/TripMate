from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from attendance.models import Attendance, DriverDailyAttendanceMark
from salary.models import DriverSalaryAdvance
from salary.models import DriverSalaryPayment

TWOPLACES = Decimal("0.01")


def get_salary_month_bounds(*, month: int, year: int) -> tuple[date, date]:
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    return first_day, last_day


def get_salary_due_date(*, month: int, year: int) -> date:
    if month == 12:
        return date(year + 1, 1, 5)
    return date(year, month + 1, 5)


def can_pay_salary_for_month(*, month: int, year: int, today: date | None = None) -> bool:
    today = today or timezone.localdate()
    month_end = get_salary_month_bounds(month=month, year=year)[1]
    return today > month_end


def _is_payable_weekly_off_day(*, current_date: date, joined_date: date | None) -> bool:
    if current_date.weekday() != 6:
        return False
    if joined_date is None:
        return True
    week_start = current_date - timedelta(days=current_date.weekday())
    return joined_date <= week_start


def _build_day_maps(*, drivers, transporter, month: int, year: int):
    month_start, month_end = get_salary_month_bounds(month=month, year=year)
    driver_ids = [driver.id for driver in drivers]

    worked_dates_map = {driver_id: set() for driver_id in driver_ids}
    for driver_id, work_date in (
        Attendance.objects.filter(
            driver_id__in=driver_ids,
            date__gte=month_start,
            date__lte=month_end,
        )
        .values_list("driver_id", "date")
        .distinct()
    ):
        worked_dates_map.setdefault(driver_id, set()).add(work_date)

    marks_map = {driver_id: {} for driver_id in driver_ids}
    for driver_id, mark_date, mark_status in DriverDailyAttendanceMark.objects.filter(
        driver_id__in=driver_ids,
        transporter=transporter,
        date__gte=month_start,
        date__lte=month_end,
    ).values_list("driver_id", "date", "status"):
        marks_map.setdefault(driver_id, {})[mark_date] = mark_status

    return month_start, month_end, worked_dates_map, marks_map


def calculate_salary_summary_for_driver(
    *,
    driver,
    month: int,
    year: int,
    cl_count: int = 0,
    payment: DriverSalaryPayment | None = None,
    today: date | None = None,
    worked_dates_map=None,
    marks_map=None,
    advances_map=None,
):
    today = today or timezone.localdate()
    cl_count = max(int(cl_count or 0), 0)
    month_start, month_end = get_salary_month_bounds(month=month, year=year)
    total_days = monthrange(year, month)[1]
    joined_date = driver.joined_transporter_date

    if worked_dates_map is None or marks_map is None:
        _, _, worked_dates_by_driver, marks_by_driver = _build_day_maps(
            drivers=[driver],
            transporter=driver.transporter,
            month=month,
            year=year,
        )
        worked_dates = worked_dates_by_driver.get(driver.id, set())
        marks_by_date = marks_by_driver.get(driver.id, {})
    else:
        worked_dates = worked_dates_map.get(driver.id, set())
        marks_by_date = marks_map.get(driver.id, {})

    present_days = 0
    no_duty_days = 0
    weekly_off_days = 0
    unpaid_weekly_off_days = 0
    leave_days = 0
    absent_days = 0
    future_days = 0

    for day_number in range(1, total_days + 1):
        current_date = date(year, month, day_number)
        if current_date > today:
            future_days += 1
            continue
        if joined_date is not None and current_date < joined_date:
            continue

        if current_date in worked_dates:
            present_days += 1
            continue

        if current_date.weekday() == 6:
            if _is_payable_weekly_off_day(
                current_date=current_date,
                joined_date=joined_date,
            ):
                weekly_off_days += 1
            else:
                unpaid_weekly_off_days += 1
            continue

        mark_status = marks_by_date.get(current_date)
        if mark_status == DriverDailyAttendanceMark.Status.LEAVE:
            leave_days += 1
        elif mark_status == DriverDailyAttendanceMark.Status.ABSENT:
            absent_days += 1
        elif mark_status == DriverDailyAttendanceMark.Status.PRESENT:
            no_duty_days += 1
        else:
            no_duty_days += 1

    paid_leave_days = min(cl_count, leave_days)
    unpaid_leave_days = max(leave_days - paid_leave_days, 0)
    payable_days = present_days + no_duty_days + weekly_off_days + paid_leave_days

    monthly_salary = Decimal(driver.monthly_salary or 0).quantize(TWOPLACES)
    per_day_salary = (
        (monthly_salary / Decimal(total_days)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if total_days
        else Decimal("0.00")
    )
    payable_amount = (
        (per_day_salary * Decimal(payable_days)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    )

    due_date = get_salary_due_date(month=month, year=year)
    payment_record = payment
    if advances_map is None:
        advance_total = Decimal(
            DriverSalaryAdvance.objects.filter(
                driver=driver,
                advance_date__gte=month_start,
                advance_date__lte=month_end,
                settled_payment__isnull=True,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        advance_total = advance_total.quantize(TWOPLACES)
    else:
        advance_total = advances_map.get(driver.id, Decimal("0.00")).quantize(TWOPLACES)

    if payment_record is not None:
        advance_total = Decimal(payment_record.advance_amount).quantize(TWOPLACES)

    net_payable_amount = max(payable_amount - advance_total, Decimal("0.00")).quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )

    return {
        "driver_id": driver.id,
        "driver_name": driver.user.username,
        "driver_phone": driver.user.phone,
        "month": month,
        "year": year,
        "month_start": month_start,
        "month_end": month_end,
        "joined_transporter_date": joined_date,
        "salary_due_date": due_date,
        "can_pay": can_pay_salary_for_month(month=month, year=year, today=today),
        "total_days_in_month": total_days,
        "future_days": future_days,
        "present_days": present_days,
        "no_duty_days": no_duty_days,
        "weekly_off_days": weekly_off_days,
        "unpaid_weekly_off_days": unpaid_weekly_off_days,
        "leave_days": leave_days,
        "cl_count": cl_count,
        "paid_leave_days": paid_leave_days,
        "unpaid_leave_days": unpaid_leave_days,
        "absent_days": absent_days,
        "paid_days": payable_days,
        "monthly_salary": monthly_salary,
        "per_day_salary": per_day_salary,
        "payable_amount": payable_amount,
        "advance_amount": advance_total,
        "net_payable_amount": net_payable_amount,
        "payment_status": "PAID" if payment_record else "PENDING",
        "is_paid": payment_record is not None,
        "paid_at": payment_record.paid_at if payment_record else None,
        "paid_by_username": payment_record.paid_by.username if payment_record and payment_record.paid_by else None,
        "payment_id": payment_record.id if payment_record else None,
        "notes": payment_record.notes if payment_record else "",
    }


def calculate_salary_month_for_transporter(*, transporter, month: int, year: int, today: date | None = None):
    today = today or timezone.localdate()
    drivers = list(
        transporter.drivers.select_related("user").filter(is_active=True).order_by("user__username")
    )
    month_start, month_end, worked_dates_map, marks_map = _build_day_maps(
        drivers=drivers,
        transporter=transporter,
        month=month,
        year=year,
    )
    payments_map = {
        item.driver_id: item
        for item in DriverSalaryPayment.objects.select_related("paid_by").filter(
            transporter=transporter,
            salary_month=month,
            salary_year=year,
        )
    }
    advances_map = {}
    for item in DriverSalaryAdvance.objects.filter(
        transporter=transporter,
        settled_payment__isnull=True,
        advance_date__gte=month_start,
        advance_date__lte=month_end,
    ).values("driver_id").annotate(total=Sum("amount")):
        advances_map[item["driver_id"]] = Decimal(item["total"] or 0)

    rows = []
    for driver in drivers:
        payment = payments_map.get(driver.id)
        rows.append(
            calculate_salary_summary_for_driver(
                driver=driver,
                month=month,
                year=year,
                cl_count=payment.cl_count if payment else 0,
                payment=payment,
                today=today,
                worked_dates_map=worked_dates_map,
                marks_map=marks_map,
                advances_map=advances_map,
            )
        )

    return {
        "month": month,
        "year": year,
        "month_start": month_start,
        "month_end": month_end,
        "salary_due_date": get_salary_due_date(month=month, year=year),
        "rows": rows,
        "total_drivers": len(rows),
        "paid_count": sum(1 for row in rows if row["is_paid"]),
        "pending_count": sum(1 for row in rows if not row["is_paid"] and row["can_pay"]),
        "total_payable_amount": sum(
            (row["net_payable_amount"] for row in rows),
            Decimal("0.00"),
        ).quantize(TWOPLACES),
        "total_paid_amount": sum(
            (row["net_payable_amount"] for row in rows if row["is_paid"]),
            Decimal("0.00"),
        ).quantize(TWOPLACES),
    }
