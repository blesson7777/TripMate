from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle


@dataclass(frozen=True)
class BankDetails:
    bank_name: str = ""
    branch: str = ""
    account_no: str = ""
    ifsc_code: str = ""


@dataclass(frozen=True)
class VehicleMonthlyRunBill:
    from_lines: list[str]
    bill_date_label: str
    to_lines: list[str]
    month_label: str
    si_no: str
    description: str
    vehicle_number: str
    extra_km: str
    add_vh_rate: str
    total_amount: str
    amount_in_words: str
    grand_total: str
    bank_details: BankDetails
    signatures: list[str]
    bill_no_label: str = ""
    header_company_name: str = ""
    header_contact_name: str = ""
    header_phone: str = ""
    header_email: str = ""
    header_gstin: str = ""
    header_pan: str = ""
    header_website: str = ""
    biller_name: str = ""
    logo_path: str = ""
    logo_bytes: bytes | None = None
    show_office_signatures: bool = True
    bill_receiver_name: str = ""


_ONES = [
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
_TENS = [
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
]


def _two_digits(value: int) -> str:
    if value <= 0:
        return ""
    if value < 20:
        return _ONES[value]
    tens = value // 10
    ones = value % 10
    return f"{_TENS[tens]}{(' ' + _ONES[ones]) if ones else ''}".strip()


def _three_digits(value: int) -> str:
    if value <= 0:
        return ""
    hundred = value // 100
    rest = value % 100
    parts: list[str] = []
    if hundred:
        parts.append(f"{_ONES[hundred]} Hundred")
    if rest:
        parts.append(_two_digits(rest))
    return " ".join([part for part in parts if part]).strip()


def amount_to_words_inr(amount: Decimal) -> str:
    """
    Converts a numeric amount to words using the Indian numbering system.
    Intended for invoice-style labels like: "Rupees One Lakh Twenty Three Only".
    """
    try:
        quantized = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return ""

    rupees = int(quantized)
    paise = int((quantized - Decimal(rupees)) * 100)

    if rupees == 0:
        rupee_words = "Zero"
    else:
        parts: list[str] = []
        crore = rupees // 10_000_000
        rupees %= 10_000_000
        lakh = rupees // 100_000
        rupees %= 100_000
        thousand = rupees // 1000
        rupees %= 1000
        remainder = rupees

        if crore:
            parts.append(f"{_three_digits(crore)} Crore")
        if lakh:
            parts.append(f"{_three_digits(lakh)} Lakh")
        if thousand:
            parts.append(f"{_three_digits(thousand)} Thousand")
        if remainder:
            parts.append(_three_digits(remainder))

        rupee_words = " ".join([part for part in parts if part]).strip()

    if paise:
        return f"Rupees {rupee_words} and Paise {_two_digits(paise)} Only"
    return f"Rupees {rupee_words} Only"


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    safe = (text or "").replace("\n", "<br/>")
    return Paragraph(safe, style)


def _sanitize_lines(lines: Iterable[str]) -> list[str]:
    sanitized = []
    for line in lines:
        value = (line or "").strip()
        if value:
            sanitized.append(value)
    return sanitized


def build_vehicle_monthly_run_bill_pdf(bill: VehicleMonthlyRunBill) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Vehicle Monthly Run Bill",
    )

    page_width, _ = A4
    available_width = page_width - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "BillNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=12,
    )
    small = ParagraphStyle(
        "BillSmall",
        parent=normal,
        fontSize=9,
        leading=11,
    )
    bold = ParagraphStyle(
        "BillBold",
        parent=normal,
        fontName="Helvetica-Bold",
    )
    company = ParagraphStyle(
        "BillCompany",
        parent=bold,
        fontSize=13,
        leading=15,
    )
    header = ParagraphStyle(
        "BillHeader",
        parent=bold,
        alignment=1,
    )

    company_name = (bill.header_company_name or "").strip()
    contact_name = (bill.header_contact_name or "").strip()
    phone = (bill.header_phone or "").strip()
    email = (bill.header_email or "").strip()
    gstin = (bill.header_gstin or "").strip()
    pan = (bill.header_pan or "").strip()
    website = (bill.header_website or "").strip()

    sanitized_from = _sanitize_lines(bill.from_lines)
    from_lines = [
        line
        for line in sanitized_from
        if line.lower() not in {"from", "from,"}
        and line != company_name
        and line != contact_name
    ]

    from_rows: list[list[Paragraph]] = [[_para("<b>From,</b>", bold)]]
    if company_name:
        from_rows.append([_para(company_name, company)])
    if contact_name and contact_name != company_name:
        from_rows.append([_para(contact_name, normal)])

    contact_bits: list[str] = []
    if phone:
        contact_bits.append(f"Ph: {phone}")
    if email:
        contact_bits.append(f"Email: {email}")
    if contact_bits:
        from_rows.append([_para(" | ".join(contact_bits), small)])
    if gstin:
        from_rows.append([_para(f"GSTIN: {gstin}", small)])
    if pan:
        from_rows.append([_para(f"PAN: {pan}", small)])
    if website:
        from_rows.append([_para(f"Web: {website}", small)])
    for line in from_lines:
        from_rows.append([_para(line, normal)])

    left_width = available_width * 0.7
    right_width = available_width * 0.3
    cell_padding = 6
    content_left_width = max(10, left_width - (cell_padding * 2))
    content_right_width = max(10, right_width - (cell_padding * 2))

    from_text_table = Table(from_rows, colWidths=[content_left_width])
    from_text_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    from_cell = from_text_table
    logo_size = 22 * mm
    logo_flowable = None
    if bill.logo_bytes:
        try:
            logo_stream = BytesIO(bill.logo_bytes)
            logo_stream.seek(0)
            logo_flowable = Image(logo_stream, width=logo_size, height=logo_size)
        except Exception:
            logo_flowable = None
    if logo_flowable is None:
        logo_path = (bill.logo_path or "").strip()
        if logo_path and Path(logo_path).exists():
            try:
                logo_flowable = Image(logo_path, width=logo_size, height=logo_size)
            except Exception:
                logo_flowable = None

    if logo_flowable is not None:
        logo_flowable.hAlign = "CENTER"
        text_width = max(10, content_left_width - (logo_size + 6))
        from_text_table = Table(from_rows, colWidths=[text_width])
        from_text_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        from_cell = Table(
            [[logo_flowable, from_text_table]],
            colWidths=[logo_size + 6, text_width],
        )
        from_cell.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

    bill_no_label = (bill.bill_no_label or "").strip() or "____________"
    date_label = bill.bill_date_label or "____________"
    month_label = (bill.month_label or "").strip()
    vehicle_label = (bill.vehicle_number or "").strip()
    service_label = (bill.description or "").strip()

    meta_rows = [
        [_para("<b>Bill No:</b>", small), _para(bill_no_label, small)],
        [_para("<b>Date:</b>", small), _para(date_label, small)],
        [_para("<b>Month:</b>", small), _para(month_label, small)],
        [_para("<b>Vehicle:</b>", small), _para(vehicle_label, small)],
        [_para("<b>Service:</b>", small), _para(service_label, small)],
    ]
    meta_table = Table(
        meta_rows,
        colWidths=[content_right_width * 0.42, content_right_width * 0.58],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    top_section = Table(
        [
            [
                from_cell,
                meta_table,
            ]
        ],
        colWidths=[left_width, right_width],
    )
    top_section.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEAFTER", (0, 0), (0, 0), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    to_text = "<br/>".join(_sanitize_lines(bill.to_lines))
    to_section = Table([[_para(to_text, normal)]], colWidths=[available_width])
    to_section.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    month_line = f"<br/><br/><b>Month:</b> {bill.month_label}" if bill.month_label else ""
    description_cell = _para(
        f"{bill.description}{month_line}<br/><br/><b>Vehicle No:</b> {bill.vehicle_number}",
        normal,
    )

    main_table = Table(
        [
            [
                _para("SI No", header),
                _para("Description", header),
                _para("Extra km", header),
                _para("Add.VH.Rate", header),
                _para("Total Amount", header),
            ],
            [
                _para(bill.si_no, normal),
                description_cell,
                _para(bill.extra_km, normal),
                _para(bill.add_vh_rate, normal),
                _para(bill.total_amount, normal),
            ],
        ],
        colWidths=[
            15 * mm,
            available_width - (15 * mm + 20 * mm + 25 * mm + 30 * mm),
            20 * mm,
            25 * mm,
            30 * mm,
        ],
        # Large row height for the main description cell (printed invoice style).
        rowHeights=[9 * mm, 70 * mm],
    )
    main_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (0, 1), "CENTER"),
                ("ALIGN", (2, 1), (4, 1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    amount_section = Table(
        [
            [
                _para(f"<b>Amount in words:</b><br/>{bill.amount_in_words}", normal),
                _para(f"<b>Grand Total</b><br/>{bill.grand_total}", bold),
            ]
        ],
        colWidths=[available_width * 0.68, available_width * 0.32],
    )
    amount_section.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEAFTER", (0, 0), (0, 0), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )

    bank_lines = [
        "<b>Bank Details:</b>",
        f"Bank: {bill.bank_details.bank_name}",
        f"Branch: {bill.bank_details.branch}",
        f"Account No.: {bill.bank_details.account_no}",
        f"IFSC Code: {bill.bank_details.ifsc_code}",
    ]
    bank_section = Table([[_para("<br/>".join(bank_lines), normal)]], colWidths=[available_width])
    bank_section.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    resolved_biller_name = (bill.biller_name or "").strip() or contact_name or company_name
    biller_text = "__________________________"
    if resolved_biller_name:
        biller_text = f"{biller_text}<br/><b>{resolved_biller_name}</b>"

    biller_section = Table(
        [
            [
                _para("<b>Biller Sign:</b>", bold),
                _para(biller_text, normal),
            ]
        ],
        colWidths=[available_width * 0.3, available_width * 0.7],
        rowHeights=[22 * mm],
    )
    biller_section.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LINEAFTER", (0, 0), (0, 0), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ]
        )
    )

    include_office_signatures = bool(bill.show_office_signatures) and any(
        (label or "").strip() for label in (bill.signatures or [])
    )

    signature_section = None
    receiver_section = None

    if include_office_signatures:
        sig_labels = (bill.signatures or [])[:4]
        while len(sig_labels) < 4:
            sig_labels.append("")

        signature_section = Table(
            [[_para(label, bold) for label in sig_labels]],
            colWidths=[available_width / 4] * 4,
            rowHeights=[28 * mm],
        )
        signature_section.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LINEAFTER", (0, 0), (0, 0), 1, colors.black),
                    ("LINEAFTER", (1, 0), (1, 0), 1, colors.black),
                    ("LINEAFTER", (2, 0), (2, 0), 1, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
    else:
        receiver_name = (bill.bill_receiver_name or "").strip()
        receiver_text = "__________________________"
        if receiver_name:
            receiver_text = f"{receiver_text}<br/><b>{receiver_name}</b>"

        receiver_section = Table(
            [
                [
                    _para("<b>Bill Receiver:</b>", bold),
                    _para(receiver_text, normal),
                ]
            ],
            colWidths=[available_width * 0.3, available_width * 0.7],
            rowHeights=[22 * mm],
        )
        receiver_section.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LINEAFTER", (0, 0), (0, 0), 1, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ]
            )
        )

    page_rows = [
        [top_section],
        [to_section],
        [main_table],
        [amount_section],
        [bank_section],
        [biller_section],
    ]
    if signature_section is not None:
        page_rows.append([signature_section])
    elif receiver_section is not None:
        page_rows.append([receiver_section])

    page_table = Table(
        page_rows,
        colWidths=[available_width],
    )
    page_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    doc.build([page_table])
    return buffer.getvalue()
