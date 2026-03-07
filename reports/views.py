from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from fuel.models import FuelRecord
from reports.serializers import FuelMonthlySummarySerializer, MonthlyReportSerializer
from trips.models import Trip
from users.permissions import IsAdminOrTransporterRole

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except Exception:  # pragma: no cover - environment without reportlab
    REPORTLAB_AVAILABLE = False

User = get_user_model()


def _parse_month_year_or_error(request):
    today = timezone.localdate()
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
    return month, year, None


def _scoped_attendance_queryset_or_error(request, month, year):
    attendances = Attendance.objects.filter(
        date__year=year,
        date__month=month,
    ).select_related("vehicle", "driver", "driver__user")
    user = request.user

    if user.role == User.Role.TRANSPORTER:
        if not hasattr(user, "transporter_profile"):
            return None, Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        attendances = attendances.filter(vehicle__transporter=user.transporter_profile)
    elif user.role == User.Role.DRIVER:
        if not hasattr(user, "driver_profile"):
            return None, Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.driver_profile.transporter_id is None:
            attendances = attendances.none()
        else:
            attendances = attendances.filter(
                driver=user.driver_profile,
                vehicle__transporter_id=user.driver_profile.transporter_id,
            )

    return attendances, None


def _resolve_closing_km(attendance):
    child_trip_end_values = [
        trip.end_km
        for trip in getattr(attendance, "_prefetched_child_trips", [])
        if trip.end_km is not None
    ]

    candidates = [attendance.start_km]
    if attendance.end_km is not None:
        candidates.append(attendance.end_km)
    if child_trip_end_values:
        candidates.append(max(child_trip_end_values))

    return max(candidates)


def _build_daily_trip_sheet_rows(attendances):
    grouped = {}
    for attendance in attendances:
        opening_km = attendance.start_km
        closing_km = _resolve_closing_km(attendance)
        if closing_km < opening_km:
            closing_km = opening_km

        purpose = (attendance.service_purpose or "").strip()
        key = (
            attendance.date,
            attendance.vehicle.vehicle_number,
            attendance.service_id,
            attendance.service_name,
        )
        row = grouped.get(key)
        if row is None:
            grouped[key] = {
                "date": attendance.date,
                "vehicle_number": attendance.vehicle.vehicle_number,
                "service_id": attendance.service_id,
                "service_name": attendance.service_name,
                "opening_km": opening_km,
                "closing_km": closing_km,
                "purposes": [purpose] if purpose else [],
            }
            continue

        row["opening_km"] = min(row["opening_km"], opening_km)
        row["closing_km"] = max(row["closing_km"], closing_km)
        if purpose and purpose not in row["purposes"]:
            row["purposes"].append(purpose)

    sorted_values = sorted(
        grouped.values(),
        key=lambda item: (item["date"], item["vehicle_number"], item["service_name"]),
    )
    rows = []
    for index, item in enumerate(sorted_values, start=1):
        total_run_km = max(item["closing_km"] - item["opening_km"], 0)
        purpose = " | ".join(item["purposes"]) if item["purposes"] else "-"
        rows.append(
            {
                "sl_no": index,
                "date": item["date"],
                "vehicle_number": item["vehicle_number"],
                "service_id": item["service_id"],
                "service_name": item["service_name"],
                "opening_km": item["opening_km"],
                "closing_km": item["closing_km"],
                "total_run_km": total_run_km,
                "purpose": purpose,
                # Backward-compatible aliases.
                "start_km": item["opening_km"],
                "end_km": item["closing_km"],
                "total_km": total_run_km,
            }
        )
    return rows


def _resolve_report_service_label(rows, query_service_name):
    if query_service_name:
        return query_service_name
    non_empty = sorted(
        {
            (row.get("service_name") or "").strip()
            for row in rows
            if (row.get("service_name") or "").strip()
        }
    )
    if len(non_empty) == 1:
        return non_empty[0]
    if len(non_empty) > 1:
        return "Multiple Services"
    return "Unspecified Service"


def _build_monthly_report_payload_or_error(request):
    month, year, month_error = _parse_month_year_or_error(request)
    if month_error is not None:
        return None, month_error

    vehicle_id = request.query_params.get("vehicle_id")
    service_id = request.query_params.get("service_id")
    service_name = request.query_params.get("service_name")

    attendances, scope_error = _scoped_attendance_queryset_or_error(request, month, year)
    if scope_error is not None:
        return None, scope_error

    if vehicle_id:
        attendances = attendances.filter(vehicle_id=vehicle_id)

    if service_id:
        try:
            service_id_int = int(service_id)
        except ValueError:
            return None, Response(
                {"detail": "service_id must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        attendances = attendances.filter(service_id=service_id_int)
        service_id = service_id_int
    else:
        service_id = None

    if service_name:
        normalized_service_name = service_name.strip()
        attendances = attendances.filter(service_name__iexact=normalized_service_name)
        service_name = normalized_service_name
    else:
        service_name = None

    attendances = attendances.prefetch_related(
        Prefetch(
            "trips",
            queryset=Trip.objects.filter(
                is_day_trip=False,
                end_km__isnull=False,
            ).only("id", "end_km", "ended_at", "created_at", "attendance_id"),
            to_attr="_prefetched_child_trips",
        )
    ).order_by("date", "vehicle__vehicle_number", "driver__user__username")

    rows = _build_daily_trip_sheet_rows(attendances)
    payload = {
        "month": month,
        "year": year,
        "vehicle_id": int(vehicle_id) if vehicle_id else None,
        "service_id": service_id,
        "service_name": service_name,
        "service_label": _resolve_report_service_label(rows, service_name),
        "total_days": len(rows),
        "total_km": sum(row["total_km"] for row in rows),
        "rows": rows,
    }
    return payload, None


class MonthlyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload, error_response = _build_monthly_report_payload_or_error(request)
        if error_response is not None:
            return error_response

        serializer = MonthlyReportSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MonthlyReportPdfView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrTransporterRole]

    def get(self, request):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {
                    "detail": (
                        "PDF export dependency missing. Install reportlab on server."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        payload, error_response = _build_monthly_report_payload_or_error(request)
        if error_response is not None:
            return error_response

        layout = request.query_params.get("layout", "full").strip().lower()
        if layout not in {"full", "compact"}:
            return Response(
                {"detail": "layout must be either 'full' or 'compact'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = self._build_pdf(payload=payload, request=request, layout=layout)
        service_for_filename = (payload["service_label"] or "service").replace(" ", "-")
        filename = (
            f"trip-sheet-{service_for_filename}-{payload['month']:02d}-{payload['year']}-{layout}.pdf"
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _build_pdf(self, *, payload, request, layout):
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
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            alignment=1,
        )
        subtitle_style = ParagraphStyle(
            "SubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=12,
            alignment=1,
        )
        normal_style = ParagraphStyle(
            "NormalSmall",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
        )
        right_style = ParagraphStyle(
            "RightSmall",
            parent=normal_style,
            alignment=2,
        )

        elements = []
        transporter = getattr(request.user, "transporter_profile", None)
        if layout == "full":
            company_name = "TripMate"
            address = None
            if transporter is not None:
                company_name = transporter.company_name or "TripMate"
                address = transporter.address
            elements.append(Paragraph(company_name, title_style))
            if address:
                elements.append(Paragraph(address, subtitle_style))
            phone_value = request.user.phone.strip() if request.user.phone else "-"
            if phone_value:
                elements.append(Paragraph(f"Phone: {phone_value}", subtitle_style))
            elements.append(Spacer(1, 4 * mm))

        elements.append(Paragraph("VEHICLE TRIP SHEET", title_style))
        service_label = payload.get("service_label") or "Unspecified Service"
        elements.append(Paragraph(f"Service: {service_label}", subtitle_style))
        elements.append(
            Paragraph(
                f"Month: {payload['month']:02d}/{payload['year']} &nbsp;&nbsp;&nbsp; Total KM: {payload['total_km']}",
                subtitle_style,
            )
        )
        elements.append(Spacer(1, 3 * mm))

        table_data = [["Sl.no", "Date", "Vehicle", "Start km", "End km", "Total KM", "Purpose"]]
        for row in payload["rows"]:
            date_value = row["date"]
            table_data.append(
                [
                    row["sl_no"],
                    f"{date_value.day}/{date_value.month}/{date_value.year}",
                    row["vehicle_number"],
                    row["opening_km"],
                    row["closing_km"],
                    row["total_run_km"],
                    row["purpose"],
                ]
            )

        table = Table(
            table_data,
            colWidths=[14 * mm, 22 * mm, 32 * mm, 18 * mm, 18 * mm, 18 * mm, 134 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17395F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("ALIGN", (0, 0), (5, -1), "CENTER"),
                    ("ALIGN", (6, 0), (6, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 4 * mm))

        total_table = Table(
            [["TOTAL KM:", str(payload["total_km"])]],
            colWidths=[30 * mm, 24 * mm],
            hAlign="LEFT",
        )
        total_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#17395F")),
                    ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
                    ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (1, 0), 9),
                    ("ALIGN", (0, 0), (1, 0), "CENTER"),
                    ("GRID", (0, 0), (1, 0), 0.35, colors.HexColor("#2B2B2B")),
                ]
            )
        )
        elements.append(total_table)

        if layout == "full":
            elements.append(Spacer(1, 10 * mm))
            elements.append(Paragraph("Issuer Signature", right_style))
            elements.append(Paragraph("__________________________", right_style))

        document.build(elements)
        return buffer.getvalue()


class FuelMonthlySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
        except ValueError:
            return Response(
                {"detail": "Month and year must be numeric values."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if month < 1 or month > 12:
            return Response(
                {"detail": "Month must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scoped_fuel_records = FuelRecord.objects.select_related(
            "vehicle", "driver", "driver__user"
        ).filter(
            entry_type=FuelRecord.EntryType.VEHICLE_FILLING,
        )
        fuel_records = scoped_fuel_records.filter(
            date__year=year,
            date__month=month,
        )

        user = request.user
        if user.role == User.Role.TRANSPORTER:
            if not hasattr(user, "transporter_profile"):
                return Response(
                    {"detail": "Transporter profile does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            scoped_fuel_records = scoped_fuel_records.filter(
                vehicle__transporter=user.transporter_profile
            )
            fuel_records = fuel_records.filter(
                vehicle__transporter=user.transporter_profile
            )
        elif user.role == User.Role.DRIVER:
            if not hasattr(user, "driver_profile"):
                return Response(
                    {"detail": "Driver profile does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            scoped_fuel_records = scoped_fuel_records.filter(driver=user.driver_profile)
            fuel_records = fuel_records.filter(driver=user.driver_profile)

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
        overall_fill_count = 0

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
                    "vehicle_id": vehicle_id,
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
            overall_fill_count += int(item["fuel_fill_count"] or 0)

        if overall_mileage_liters > 0:
            overall_average = (
                Decimal(overall_mileage_km) / overall_mileage_liters
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        else:
            overall_average = Decimal("0.00")

        payload = {
            "month": month,
            "year": year,
            "total_vehicles_filled": len(rows),
            "total_fuel_fills": overall_fill_count,
            "total_liters": overall_liters.quantize(Decimal("0.01")),
            "total_amount": overall_amount.quantize(Decimal("0.01")),
            "overall_average_mileage": overall_average,
            "rows": rows,
        }
        serializer = FuelMonthlySummarySerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
