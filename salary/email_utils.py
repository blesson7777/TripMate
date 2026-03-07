from calendar import month_name

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from salary.models import DriverSalaryAdvance, DriverSalaryEmailLog, DriverSalaryPayment
from salary.utils import calculate_salary_summary_for_driver


def _format_currency(value):
    return f"Rs. {value}"


def _format_date(value):
    return value.strftime("%d %B %Y")


def _build_advance_items(*, driver, month_start, month_end):
    advances = list(
        DriverSalaryAdvance.objects.filter(
            driver=driver,
            advance_date__gte=month_start,
            advance_date__lte=month_end,
        ).order_by("advance_date", "created_at")
    )
    if not advances:
        return []
    return advances


def _build_text_message(*, driver, month_label, summary, generated_on, advances):
    advance_lines = (
        "\n".join(
            [
                f"- {_format_date(item.advance_date)}: {_format_currency(item.amount)}"
                f"{f' ({item.notes})' if item.notes else ''}"
                for item in advances
            ]
        )
        if advances
        else "No advance salary was recorded for this period."
    )
    return (
        f"Subject: Salary Balance Statement - {month_label}\n\n"
        f"Dear {driver.user.username},\n\n"
        "This is your monthly salary balance statement generated from TripMate Payroll.\n\n"
        f"Salary Period: {month_label}\n"
        f"Generated On: {generated_on}\n"
        f"Salary Due Date: {_format_date(summary['salary_due_date'])}\n\n"
        "Payroll Summary\n"
        f"- Monthly Salary: {_format_currency(summary['monthly_salary'])}\n"
        f"- Paid Days: {summary['paid_days']} / {summary['total_days_in_month']}\n"
        f"- Present Days: {summary['present_days']}\n"
        f"- No Duty Treated as Present: {summary['no_duty_days']}\n"
        f"- Payable Weekly Off Days: {summary['weekly_off_days']}\n"
        f"- Unpaid Weekly Off Days: {summary['unpaid_weekly_off_days']}\n"
        f"- Leave Days: {summary['leave_days']}\n"
        f"- Company CL Applied: {summary['cl_count']}\n"
        f"- Gross Salary Payable: {_format_currency(summary['payable_amount'])}\n"
        f"- Advance Collected: {_format_currency(summary['advance_amount'])}\n"
        f"- Balance Salary Payable: {_format_currency(summary['net_payable_amount'])}\n\n"
        "Advance Collection Details\n"
        f"{advance_lines}\n\n"
        "If you notice any discrepancy, please contact your transporter before salary processing.\n\n"
        f"Regards,\n{driver.transporter.company_name}\nTripMate Payroll Team"
    )


def _build_html_message(*, driver, month_label, summary, generated_on, advances):
    if advances:
        advance_rows = "".join(
            [
                (
                    "<tr>"
                    f"<td style=\"padding:8px;border:1px solid #d7dee6;\">{_format_date(item.advance_date)}</td>"
                    f"<td style=\"padding:8px;border:1px solid #d7dee6;\">{_format_currency(item.amount)}</td>"
                    f"<td style=\"padding:8px;border:1px solid #d7dee6;\">{item.notes or '-'}</td>"
                    "</tr>"
                )
                for item in advances
            ]
        )
    else:
        advance_rows = (
            "<tr>"
            "<td colspan=\"3\" style=\"padding:8px;border:1px solid #d7dee6;\">"
            "No advance salary was recorded for this period."
            "</td>"
            "</tr>"
        )

    summary_rows = [
        ("Monthly Salary", _format_currency(summary["monthly_salary"])),
        ("Paid Days", f"{summary['paid_days']} / {summary['total_days_in_month']}"),
        ("Present Days", str(summary["present_days"])),
        ("No Duty Treated as Present", str(summary["no_duty_days"])),
        ("Payable Weekly Off Days", str(summary["weekly_off_days"])),
        ("Unpaid Weekly Off Days", str(summary["unpaid_weekly_off_days"])),
        ("Leave Days", str(summary["leave_days"])),
        ("Company CL Applied", str(summary["cl_count"])),
        ("Gross Salary Payable", _format_currency(summary["payable_amount"])),
        ("Advance Collected", _format_currency(summary["advance_amount"])),
        ("Balance Salary Payable", _format_currency(summary["net_payable_amount"])),
        ("Salary Due Date", _format_date(summary["salary_due_date"])),
    ]
    summary_html = "".join(
        [
            (
                "<tr>"
                f"<td style=\"padding:10px 12px;border:1px solid #d7dee6;background:#f7fafc;font-weight:600;\">{label}</td>"
                f"<td style=\"padding:10px 12px;border:1px solid #d7dee6;\">{value}</td>"
                "</tr>"
            )
            for label, value in summary_rows
        ]
    )

    return f"""
<html>
  <body style="margin:0;padding:24px;background:#f3f6f9;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
    <div style="max-width:720px;margin:0 auto;background:#ffffff;border:1px solid #d7dee6;border-radius:16px;overflow:hidden;">
      <div style="padding:20px 24px;background:#0f766e;color:#ffffff;">
        <h2 style="margin:0;font-size:22px;">Salary Balance Statement</h2>
        <p style="margin:8px 0 0 0;font-size:14px;opacity:0.92;">TripMate Payroll Notification</p>
      </div>
      <div style="padding:24px;">
        <p style="margin:0 0 16px 0;">Dear {driver.user.username},</p>
        <p style="margin:0 0 16px 0;">
          Please find your salary balance statement for <strong>{month_label}</strong>.
          This statement was generated on <strong>{generated_on}</strong>.
        </p>
        <table style="width:100%;border-collapse:collapse;margin:0 0 20px 0;">
          {summary_html}
        </table>
        <h3 style="margin:0 0 10px 0;font-size:16px;color:#0f172a;">Advance Collection Details</h3>
        <table style="width:100%;border-collapse:collapse;margin:0 0 18px 0;">
          <thead>
            <tr>
              <th style="text-align:left;padding:8px;border:1px solid #d7dee6;background:#eef2f7;">Date</th>
              <th style="text-align:left;padding:8px;border:1px solid #d7dee6;background:#eef2f7;">Amount</th>
              <th style="text-align:left;padding:8px;border:1px solid #d7dee6;background:#eef2f7;">Notes</th>
            </tr>
          </thead>
          <tbody>
            {advance_rows}
          </tbody>
        </table>
        <p style="margin:0 0 16px 0;">
          If you notice any discrepancy, please contact your transporter before salary processing.
        </p>
        <p style="margin:0;">
          Regards,<br>
          <strong>{driver.transporter.company_name}</strong><br>
          TripMate Payroll Team
        </p>
      </div>
    </div>
  </body>
</html>
"""


def send_salary_balance_email_now(*, driver, month: int, year: int, current_time=None):
    current_time = timezone.localtime(current_time or timezone.now())
    if not driver.transporter_id or not driver.user.email:
        return False

    summary = calculate_salary_summary_for_driver(
        driver=driver,
        month=month,
        year=year,
        today=current_time.date(),
    )
    month_label = f"{month_name[month]} {year}"
    generated_on = timezone.localtime(current_time).strftime("%d %B %Y, %I:%M %p")
    advances = _build_advance_items(
        driver=driver,
        month_start=summary["month_start"],
        month_end=summary["month_end"],
    )

    subject = f"Salary Balance Statement - {month_label}"
    text_body = _build_text_message(
        driver=driver,
        month_label=month_label,
        summary=summary,
        generated_on=generated_on,
        advances=advances,
    )
    html_body = _build_html_message(
        driver=driver,
        month_label=month_label,
        summary=summary,
        generated_on=generated_on,
        advances=advances,
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[driver.user.email.strip().lower()],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)
    return True


def send_salary_balance_email_if_due(*, driver, current_time=None):
    current_time = current_time or timezone.localtime()
    if current_time.day != 1 or current_time.hour != 10:
        return False
    if not driver.transporter_id or not driver.user.email:
        return False

    if current_time.month == 1:
        salary_month = 12
        salary_year = current_time.year - 1
    else:
        salary_month = current_time.month - 1
        salary_year = current_time.year

    if DriverSalaryPayment.objects.filter(
        driver=driver,
        transporter=driver.transporter,
        salary_month=salary_month,
        salary_year=salary_year,
    ).exists():
        return False

    log, created = DriverSalaryEmailLog.objects.get_or_create(
        driver=driver,
        transporter=driver.transporter,
        salary_month=salary_month,
        salary_year=salary_year,
        email_type=DriverSalaryEmailLog.EmailType.BALANCE_ACK,
        defaults={"sent_at": current_time},
    )
    if not created:
        return False

    summary = calculate_salary_summary_for_driver(
        driver=driver,
        month=salary_month,
        year=salary_year,
        today=current_time.date(),
    )
    month_label = f"{month_name[salary_month]} {salary_year}"
    generated_on = timezone.localtime(current_time).strftime("%d %B %Y, %I:%M %p")
    advances = _build_advance_items(
        driver=driver,
        month_start=summary["month_start"],
        month_end=summary["month_end"],
    )

    subject = f"Salary Balance Statement - {month_label}"
    text_body = _build_text_message(
        driver=driver,
        month_label=month_label,
        summary=summary,
        generated_on=generated_on,
        advances=advances,
    )
    html_body = _build_html_message(
        driver=driver,
        month_label=month_label,
        summary=summary,
        generated_on=generated_on,
        advances=advances,
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[driver.user.email.strip().lower()],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)
    return True
