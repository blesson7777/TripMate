from calendar import month_name
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db.models import Count, F, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from fuel.models import FuelRecord
from reports.serializers import FuelMonthlySummarySerializer, MonthlyReportSerializer
from reports.serializers import (
    TransporterBankDetailsSerializer,
    TransporterBillHeaderDetailsSerializer,
    TransporterBillRecipientSerializer,
    TransporterVehicleBillListSerializer,
    VehicleMonthlyRunBillPdfRequestSerializer,
)
from reports.models import (
    TransporterBankDetails,
    TransporterBillHeaderDetails,
    TransporterBillRecipient,
    TransporterVehicleBill,
)
from trips.models import Trip
from users.permissions import IsAdminOrTransporterRole
from users.permissions import IsTransporterRole

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


def _split_address_lines(raw_value: str) -> list[str]:
    value = (raw_value or "").replace("\r", "\n").strip()
    if not value:
        return []

    if "\n" in value:
        return [line.strip() for line in value.split("\n") if line.strip()]

    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts or [value]


def _format_amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _month_label_or_blank(month: int | None, year: int | None) -> str:
    if not month or not year:
        return ""
    if month < 1 or month > 12:
        return f"{month:02d}/{year}"
    return f"{month_name[month]} {year}"


def _default_contact_name(user, transporter) -> str:
    value = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    if value:
        return value
    value = (getattr(user, "username", "") or "").strip()
    if value:
        return value
    return (getattr(transporter, "company_name", "") or "").strip()


def _generate_vehicle_bill_no(transporter, month: int | None, year: int | None) -> str:
    today = timezone.localdate()
    resolved_month = month or today.month
    resolved_year = year or today.year
    suffix = f"{resolved_month:02d}{resolved_year}"

    max_sequence = 0
    candidates = (
        TransporterVehicleBill.objects.filter(
            transporter=transporter,
            month=resolved_month,
            year=resolved_year,
        )
        .only("bill_no")
        .order_by("-created_at")
    )
    for candidate in candidates.iterator():
        bill_no = (candidate.bill_no or "").strip()
        if not bill_no.endswith(suffix):
            continue
        prefix = bill_no[: -len(suffix)]
        if not prefix or not prefix.isdigit():
            continue
        max_sequence = max(max_sequence, int(prefix))

    return f"{max_sequence + 1}{suffix}"


def _resolve_header_details(transporter, user, override: dict | None) -> dict:
    details = TransporterBillHeaderDetails.objects.filter(transporter=transporter).first()

    payload = {
        "company_name": (details.company_name if details else "").strip()
        or (transporter.company_name or "").strip(),
        "contact_name": (details.contact_name if details else "").strip()
        or _default_contact_name(user, transporter),
        "phone": (details.phone if details else "").strip() or (user.phone or "").strip(),
        "email": (details.email if details else "").strip() or (user.email or "").strip(),
        "gstin": (details.gstin if details else "").strip() or (transporter.gstin or "").strip(),
        "pan": (details.pan if details else "").strip() or (transporter.pan or "").strip(),
        "website": (details.website if details else "").strip() or (transporter.website or "").strip(),
        "biller_name": (details.biller_name if details else "").strip(),
    }

    if override:
        for key in payload.keys():
            if key in override:
                payload[key] = str(override.get(key) or "").strip()
        if not payload["company_name"]:
            payload["company_name"] = (transporter.company_name or "").strip()

    return payload


def _resolve_transporter_logo_for_pdf(transporter) -> tuple[str, bytes | None]:
    logo_field = getattr(transporter, "logo", None)
    if not logo_field:
        return "", None

    logo_path = ""
    try:
        logo_path = logo_field.path
    except Exception:
        logo_path = ""

    if logo_path and Path(logo_path).exists():
        return logo_path, None

    try:
        logo_field.open("rb")
        logo_bytes = logo_field.read()
        if logo_bytes:
            return "", logo_bytes
    except Exception:
        pass
    finally:
        try:
            logo_field.close()
        except Exception:
            pass

    return logo_path, None


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
        status=Attendance.Status.ON_DUTY,
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

        table_data.append(
            [
                "",
                "",
                "",
                "",
                "",
                "TOTAL KM:",
                str(payload["total_km"]),
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
                    ("ALIGN", (0, 0), (2, -1), "CENTER"),
                    ("ALIGN", (3, 0), (5, -1), "RIGHT"),
                    ("ALIGN", (3, 0), (5, 0), "CENTER"),
                    ("ALIGN", (6, 0), (6, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#2B2B2B")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("SPAN", (0, -1), (4, -1)),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF3F8")),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("ALIGN", (5, -1), (6, -1), "RIGHT"),
                ]
            )
        )
        elements.append(table)

        if layout == "full":
            elements.append(Spacer(1, 10 * mm))
            elements.append(Paragraph("Issuer Signature", right_style))
            elements.append(Paragraph("__________________________", right_style))

        document.build(elements)
        return buffer.getvalue()


class TransporterBillRecipientsView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipients = TransporterBillRecipient.objects.filter(transporter=transporter).order_by(
            "name",
            "-updated_at",
        )
        serializer = TransporterBillRecipientSerializer(
            [{"id": rec.id, "name": rec.name, "address": rec.address} for rec in recipients],
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TransporterBillRecipientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipient = TransporterBillRecipient.objects.create(
            transporter=transporter,
            name=serializer.validated_data["name"].strip(),
            address=serializer.validated_data["address"].strip(),
        )
        return Response(
            {"id": recipient.id, "name": recipient.name, "address": recipient.address},
            status=status.HTTP_201_CREATED,
        )


class TransporterBillRecipientDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def put(self, request, recipient_id: int):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient = TransporterBillRecipient.objects.filter(
            id=recipient_id,
            transporter=transporter,
        ).first()
        if recipient is None:
            return Response({"detail": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TransporterBillRecipientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipient.name = serializer.validated_data["name"].strip()
        recipient.address = serializer.validated_data["address"].strip()
        recipient.save(update_fields=["name", "address", "updated_at"])
        return Response(
            {"id": recipient.id, "name": recipient.name, "address": recipient.address},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, recipient_id: int):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient = TransporterBillRecipient.objects.filter(
            id=recipient_id,
            transporter=transporter,
        ).first()
        if recipient is None:
            return Response({"detail": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)
        recipient.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransporterBankDetailsView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        details, _ = TransporterBankDetails.objects.get_or_create(transporter=transporter)
        serializer = TransporterBankDetailsSerializer(
            {
                "bank_name": details.bank_name,
                "branch": details.branch,
                "account_no": details.account_no,
                "ifsc_code": details.ifsc_code,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TransporterBankDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details, _ = TransporterBankDetails.objects.get_or_create(transporter=transporter)
        for field in ("bank_name", "branch", "account_no", "ifsc_code"):
            if field in serializer.validated_data:
                setattr(details, field, serializer.validated_data[field].strip())
        details.save()
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class TransporterBillHeaderDetailsView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        details, _ = TransporterBillHeaderDetails.objects.get_or_create(transporter=transporter)
        payload = _resolve_header_details(transporter, request.user, None)
        serializer = TransporterBillHeaderDetailsSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransporterBillHeaderDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details, _ = TransporterBillHeaderDetails.objects.get_or_create(transporter=transporter)
        for field in (
            "company_name",
            "contact_name",
            "phone",
            "email",
            "gstin",
            "pan",
            "website",
            "biller_name",
        ):
            if field in serializer.validated_data:
                setattr(details, field, serializer.validated_data[field].strip())
        details.save()

        payload = _resolve_header_details(transporter, request.user, None)
        return Response(payload, status=status.HTTP_200_OK)


class VehicleMonthlyRunBillPdfView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"detail": "PDF export dependency missing. Install reportlab on server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VehicleMonthlyRunBillPdfRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        recipient = None
        recipient_id = payload.get("recipient_id")
        if recipient_id:
            recipient = TransporterBillRecipient.objects.filter(
                id=int(recipient_id),
                transporter=transporter,
            ).first()
            if recipient is None:
                return Response({"detail": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)

        to_name = (payload.get("to_name") or "").strip()
        to_address = (payload.get("to_address") or "").strip()
        if recipient is None and (not to_name or not to_address):
            return Response(
                {"detail": "Provide recipient_id or both to_name and to_address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_name = (payload.get("service_name") or "").strip() or "Diesel filling Vehicle Rent"
        vehicle_number = payload["vehicle_number"].strip()

        month = payload.get("month")
        year = payload.get("year")

        bill_date = payload.get("bill_date")
        period_date = bill_date or timezone.localdate()
        period_month = month or period_date.month
        period_year = year or period_date.year
        month_label = _month_label_or_blank(period_month, period_year)

        base_amount = payload.get("base_amount") or Decimal("0.00")
        extra_km = int(payload.get("extra_km") or 0)
        extra_rate = payload.get("extra_rate") or Decimal("0.00")
        total_amount = (base_amount + (Decimal(extra_km) * extra_rate)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        bank_payload = payload.get("bank_details") or {}
        if bank_payload:
            bank_name = (bank_payload.get("bank_name") or "").strip()
            branch = (bank_payload.get("branch") or "").strip()
            account_no = (bank_payload.get("account_no") or "").strip()
            ifsc_code = (bank_payload.get("ifsc_code") or "").strip()
        else:
            details = TransporterBankDetails.objects.filter(transporter=transporter).first()
            bank_name = (details.bank_name if details else "").strip() or "Indian Bank"
            branch = (details.branch if details else "").strip() or "Kattappana"
            account_no = (details.account_no if details else "").strip() or "8149461216"
            ifsc_code = (details.ifsc_code if details else "").strip() or "IDIB000K351"

        bill_date_label = "____________"
        if bill_date:
            bill_date_label = f"{bill_date.day:02d}/{bill_date.month:02d}/{bill_date.year}"

        bill_no = (payload.get("bill_no") or "").strip() or _generate_vehicle_bill_no(
            transporter,
            period_month,
            period_year,
        )

        header_override = payload.get("header_details") or {}
        header_details = _resolve_header_details(transporter, request.user, header_override)
        from_lines = _split_address_lines(transporter.address)

        if recipient is not None:
            to_lines = ["To", recipient.name]
            to_lines.extend(_split_address_lines(recipient.address))
        else:
            to_lines = ["To", to_name]
            to_lines.extend(_split_address_lines(to_address))

        from reports.vehicle_bill_pdf import (
            BankDetails,
            VehicleMonthlyRunBill,
            amount_to_words_inr,
            build_vehicle_monthly_run_bill_pdf,
        )

        logo_path, logo_bytes = _resolve_transporter_logo_for_pdf(transporter)
        show_office_signatures = bool(getattr(transporter, "diesel_tracking_enabled", False))
        signature_labels = (
            ["Energy Manager", "IME Manager", "OM Head", "Zonal Head"]
            if show_office_signatures
            else []
        )

        pdf_bill = VehicleMonthlyRunBill(
            from_lines=from_lines,
            bill_date_label=bill_date_label,
            to_lines=to_lines,
            month_label=month_label,
            si_no="1",
            description=service_name,
            vehicle_number=vehicle_number,
            extra_km=str(extra_km),
            add_vh_rate=_format_amount(extra_rate),
            total_amount=_format_amount(total_amount),
            amount_in_words=amount_to_words_inr(total_amount),
            grand_total=_format_amount(total_amount),
            bank_details=BankDetails(
                bank_name=bank_name,
                branch=branch,
                account_no=account_no,
                ifsc_code=ifsc_code,
            ),
            bill_no_label=bill_no,
            header_company_name=header_details.get("company_name", ""),
            header_contact_name=header_details.get("contact_name", ""),
            header_phone=header_details.get("phone", ""),
            header_email=header_details.get("email", ""),
            header_gstin=header_details.get("gstin", ""),
            header_pan=header_details.get("pan", ""),
            header_website=header_details.get("website", ""),
            biller_name=header_details.get("biller_name", ""),
            logo_path=logo_path,
            logo_bytes=logo_bytes,
            signatures=signature_labels,
            show_office_signatures=show_office_signatures,
            bill_receiver_name="",
        )

        pdf_bytes = build_vehicle_monthly_run_bill_pdf(pdf_bill)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="vehicle_bill.pdf"'
        response["X-Bill-No"] = bill_no
        return response


class TransporterVehicleBillsView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bills = (
            TransporterVehicleBill.objects.filter(transporter=transporter)
            .order_by("-created_at")[:200]
        )
        payload = [
            {
                "id": bill.id,
                "bill_no": bill.bill_no or "",
                "bill_date": bill.bill_date,
                "month": bill.month,
                "year": bill.year,
                "vehicle_number": bill.vehicle_number,
                "service_name": bill.service_name or "",
                "total_amount": bill.total_amount,
                "created_at": bill.created_at,
            }
            for bill in bills
        ]
        serializer = TransporterVehicleBillListSerializer(payload, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"detail": "PDF export dependency missing. Install reportlab on server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VehicleMonthlyRunBillPdfRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        requested_bill_no = (payload.get("bill_no") or "").strip()

        recipient = None
        recipient_id = payload.get("recipient_id")
        if recipient_id:
            recipient = TransporterBillRecipient.objects.filter(
                id=int(recipient_id),
                transporter=transporter,
            ).first()
            if recipient is None:
                return Response({"detail": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)

        to_name = (payload.get("to_name") or "").strip()
        to_address = (payload.get("to_address") or "").strip()
        if recipient is None and (not to_name or not to_address):
            return Response(
                {"detail": "Provide recipient_id or both to_name and to_address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient is not None:
            to_name = recipient.name
            to_address = recipient.address

        service_name = (payload.get("service_name") or "").strip() or "Diesel filling Vehicle Rent"
        vehicle_number = payload["vehicle_number"].strip()

        month = payload.get("month")
        year = payload.get("year")

        bill_date = payload.get("bill_date") or timezone.localdate()
        period_month = month or bill_date.month
        period_year = year or bill_date.year
        month_label = _month_label_or_blank(period_month, period_year)

        base_amount = payload.get("base_amount") or Decimal("0.00")
        extra_km = int(payload.get("extra_km") or 0)
        extra_rate = payload.get("extra_rate") or Decimal("0.00")
        total_amount = (base_amount + (Decimal(extra_km) * extra_rate)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        bank_payload = payload.get("bank_details") or {}
        if any(str(bank_payload.get(key) or "").strip() for key in ("bank_name", "branch", "account_no", "ifsc_code")):
            bank_name = (bank_payload.get("bank_name") or "").strip()
            branch = (bank_payload.get("branch") or "").strip()
            account_no = (bank_payload.get("account_no") or "").strip()
            ifsc_code = (bank_payload.get("ifsc_code") or "").strip()
        else:
            details = TransporterBankDetails.objects.filter(transporter=transporter).first()
            bank_name = (details.bank_name if details else "").strip() or "Indian Bank"
            branch = (details.branch if details else "").strip() or "Kattappana"
            account_no = (details.account_no if details else "").strip() or "8149461216"
            ifsc_code = (details.ifsc_code if details else "").strip() or "IDIB000K351"

        header_override = payload.get("header_details") or {}
        header_details = _resolve_header_details(transporter, request.user, header_override)

        bill_date_label = f"{bill_date.day:02d}/{bill_date.month:02d}/{bill_date.year}"

        from_lines = _split_address_lines(transporter.address)
        to_lines = ["To", to_name]
        to_lines.extend(_split_address_lines(to_address))

        if requested_bill_no:
            existing = TransporterVehicleBill.objects.filter(
                transporter=transporter,
                bill_no=requested_bill_no,
            ).first()
            if existing is not None:
                download_url = request.build_absolute_uri(
                    reverse("vehicle-bill-bill-download", args=[existing.id])
                )
                return Response(
                    {
                        "id": existing.id,
                        "bill_no": existing.bill_no,
                        "bill_date": existing.bill_date,
                        "month": existing.month,
                        "year": existing.year,
                        "vehicle_number": existing.vehicle_number,
                        "service_name": existing.service_name,
                        "total_amount": _format_amount(existing.total_amount),
                        "download_url": download_url,
                    },
                    status=status.HTTP_200_OK,
                )

        bill_no = requested_bill_no or _generate_vehicle_bill_no(
            transporter,
            period_month,
            period_year,
        )

        try:
            bill_record = TransporterVehicleBill.objects.create(
                transporter=transporter,
                recipient=recipient,
                bill_no=bill_no,
                bill_date=bill_date,
                month=period_month,
                year=period_year,
                vehicle_number=vehicle_number,
                service_name=service_name,
                base_amount=base_amount,
                extra_km=extra_km,
                extra_rate=extra_rate,
                total_amount=total_amount,
                to_name=to_name.strip(),
                to_address=to_address.strip(),
                bank_name=bank_name,
                branch=branch,
                account_no=account_no,
                ifsc_code=ifsc_code,
                from_company_name=header_details.get("company_name", ""),
                from_contact_name=header_details.get("contact_name", ""),
                from_phone=header_details.get("phone", ""),
                from_email=header_details.get("email", ""),
                from_gstin=header_details.get("gstin", ""),
                from_pan=header_details.get("pan", ""),
                from_website=header_details.get("website", ""),
                biller_name=header_details.get("biller_name", ""),
            )
        except IntegrityError:
            if requested_bill_no:
                return Response(
                    {"detail": "Bill number already exists. Please generate again."},
                    status=status.HTTP_409_CONFLICT,
                )
            bill_no = _generate_vehicle_bill_no(transporter, period_month, period_year)
            bill_record = TransporterVehicleBill.objects.create(
                transporter=transporter,
                recipient=recipient,
                bill_no=bill_no,
                bill_date=bill_date,
                month=period_month,
                year=period_year,
                vehicle_number=vehicle_number,
                service_name=service_name,
                base_amount=base_amount,
                extra_km=extra_km,
                extra_rate=extra_rate,
                total_amount=total_amount,
                to_name=to_name.strip(),
                to_address=to_address.strip(),
                bank_name=bank_name,
                branch=branch,
                account_no=account_no,
                ifsc_code=ifsc_code,
                from_company_name=header_details.get("company_name", ""),
                from_contact_name=header_details.get("contact_name", ""),
                from_phone=header_details.get("phone", ""),
                from_email=header_details.get("email", ""),
                from_gstin=header_details.get("gstin", ""),
                from_pan=header_details.get("pan", ""),
                from_website=header_details.get("website", ""),
                biller_name=header_details.get("biller_name", ""),
            )

        from reports.vehicle_bill_pdf import (
            BankDetails,
            VehicleMonthlyRunBill,
            amount_to_words_inr,
            build_vehicle_monthly_run_bill_pdf,
        )

        logo_path, logo_bytes = _resolve_transporter_logo_for_pdf(transporter)
        show_office_signatures = bool(getattr(transporter, "diesel_tracking_enabled", False))
        signature_labels = (
            ["Energy Manager", "IME Manager", "OM Head", "Zonal Head"]
            if show_office_signatures
            else []
        )

        pdf_bill = VehicleMonthlyRunBill(
            from_lines=from_lines,
            bill_date_label=bill_date_label,
            to_lines=to_lines,
            month_label=month_label,
            si_no="1",
            description=service_name,
            vehicle_number=vehicle_number,
            extra_km=str(extra_km),
            add_vh_rate=_format_amount(extra_rate),
            total_amount=_format_amount(total_amount),
            amount_in_words=amount_to_words_inr(total_amount),
            grand_total=_format_amount(total_amount),
            bank_details=BankDetails(
                bank_name=bank_name,
                branch=branch,
                account_no=account_no,
                ifsc_code=ifsc_code,
            ),
            bill_no_label=bill_no,
            header_company_name=header_details.get("company_name", ""),
            header_contact_name=header_details.get("contact_name", ""),
            header_phone=header_details.get("phone", ""),
            header_email=header_details.get("email", ""),
            header_gstin=header_details.get("gstin", ""),
            header_pan=header_details.get("pan", ""),
            header_website=header_details.get("website", ""),
            biller_name=header_details.get("biller_name", ""),
            logo_path=logo_path,
            logo_bytes=logo_bytes,
            signatures=signature_labels,
            show_office_signatures=show_office_signatures,
            bill_receiver_name="",
        )

        pdf_bytes = build_vehicle_monthly_run_bill_pdf(pdf_bill)
        bill_record.pdf_file.save(f"{bill_no}.pdf", ContentFile(pdf_bytes), save=False)
        bill_record.save(update_fields=["pdf_file", "updated_at"])

        download_url = request.build_absolute_uri(
            reverse("vehicle-bill-bill-download", args=[bill_record.id])
        )
        return Response(
            {
                "id": bill_record.id,
                "bill_no": bill_record.bill_no,
                "bill_date": bill_record.bill_date,
                "month": bill_record.month,
                "year": bill_record.year,
                "vehicle_number": bill_record.vehicle_number,
                "service_name": bill_record.service_name,
                "total_amount": _format_amount(bill_record.total_amount),
                "download_url": download_url,
            },
            status=status.HTTP_201_CREATED,
        )


class TransporterVehicleBillDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def delete(self, request, bill_id: int):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bill = TransporterVehicleBill.objects.filter(
            id=bill_id,
            transporter=transporter,
        ).first()
        if bill is None:
            return Response({"detail": "Bill not found."}, status=status.HTTP_404_NOT_FOUND)

        if bill.pdf_file:
            bill.pdf_file.delete(save=False)
        bill.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransporterVehicleBillDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request, bill_id: int):
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bill = TransporterVehicleBill.objects.filter(
            id=bill_id,
            transporter=transporter,
        ).first()
        if bill is None:
            return Response({"detail": "Bill not found."}, status=status.HTTP_404_NOT_FOUND)
        if not bill.pdf_file:
            return Response(
                {"detail": "Bill PDF not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        filename = f"{bill.bill_no or 'vehicle_bill'}.pdf"
        return FileResponse(
            bill.pdf_file.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )


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
