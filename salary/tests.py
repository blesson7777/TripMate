from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from attendance.models import Attendance, DriverDailyAttendanceMark, TransportService
from drivers.models import Driver
from salary.email_utils import send_salary_balance_email_if_due, send_salary_balance_email_now
from salary.models import DriverSalaryAdvance, DriverSalaryEmailLog, DriverSalaryPayment
from salary.utils import calculate_salary_summary_for_driver
from users.models import DriverNotification, Transporter, User
from vehicles.models import Vehicle


class SalaryModuleTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.transporter_user = User.objects.create_user(
            username="salary_transporter",
            password="SafePass@123",
            role=User.Role.TRANSPORTER,
            email="salary.transporter@example.com",
        )
        self.transporter = Transporter.objects.create(
            user=self.transporter_user,
            company_name="Salary Fleet",
            address="Yard",
        )
        self.driver_user = User.objects.create_user(
            username="salary_driver",
            password="SafePass@123",
            role=User.Role.DRIVER,
            email="salary.driver@example.com",
        )
        self.driver = Driver.objects.create(
            user=self.driver_user,
            transporter=self.transporter,
            license_number="SAL-LIC-01",
            monthly_salary=Decimal("30000.00"),
        )
        self.vehicle = Vehicle.objects.create(
            transporter=self.transporter,
            vehicle_number="SAL-VEH-01",
            model="Salary Van",
            status=Vehicle.Status.ACTIVE,
        )
        self.service = TransportService.objects.create(
            transporter=self.transporter,
            name="DTM Vehicle",
            is_active=True,
        )
        self.target_year, self.target_month = self._previous_month(timezone.localdate())
        self.month_start = date(self.target_year, self.target_month, 1)
        self.month_end = date(
            self.target_year,
            self.target_month,
            monthrange(self.target_year, self.target_month)[1],
        )
        self.driver.joined_transporter_at = timezone.make_aware(
            datetime.combine(self.month_start - timedelta(days=10), datetime.min.time())
        )
        self.driver.save(update_fields=["joined_transporter_at"])

    def _previous_month(self, value):
        if value.month == 1:
            return value.year - 1, 12
        return value.year, value.month - 1

    def _odo_image(self, name="odo.gif"):
        return SimpleUploadedFile(
            name,
            (
                b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00"
                b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
                b"\x4c\x01\x00\x3b"
            ),
            content_type="image/gif",
        )

    def _first_non_sunday_dates(self, count):
        results = []
        current = self.month_start
        while len(results) < count:
            if current.weekday() != 6:
                results.append(current)
            current += timedelta(days=1)
        return results

    def _create_attendance(self, run_date, start_km, end_km):
        return Attendance.objects.create(
            driver=self.driver,
            vehicle=self.vehicle,
            date=run_date,
            status=Attendance.Status.ON_DUTY,
            service=self.service,
            service_name=self.service.name,
            start_km=start_km,
            end_km=end_km,
            odo_start_image=self._odo_image(f"start-{run_date}.gif"),
            odo_end_image=self._odo_image(f"end-{run_date}.gif"),
            latitude="22.572646",
            longitude="88.363895",
        )

    def test_salary_monthly_summary_counts_sundays_no_duty_and_advances(self):
        work_day_one, work_day_two, no_duty_day, leave_day, advance_day = self._first_non_sunday_dates(5)
        self._create_attendance(work_day_one, 1000, 1040)
        self._create_attendance(work_day_two, 1040, 1085)
        DriverDailyAttendanceMark.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            date=no_duty_day,
            status=DriverDailyAttendanceMark.Status.PRESENT,
            marked_by=self.transporter_user,
        )
        DriverDailyAttendanceMark.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            date=leave_day,
            status=DriverDailyAttendanceMark.Status.LEAVE,
            marked_by=self.transporter_user,
        )
        DriverSalaryAdvance.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            amount=Decimal("500.00"),
            advance_date=advance_day,
            recorded_by=self.transporter_user,
        )

        sunday_count = sum(
            1
            for day in range(1, monthrange(self.target_year, self.target_month)[1] + 1)
            if date(self.target_year, self.target_month, day).weekday() == 6
        )
        total_days = monthrange(self.target_year, self.target_month)[1]
        expected_no_duty_days = total_days - sunday_count - 2 - 1
        expected_paid_days = 2 + expected_no_duty_days + sunday_count
        expected_per_day = Decimal("30000.00") / Decimal(monthrange(self.target_year, self.target_month)[1])
        expected_per_day = expected_per_day.quantize(Decimal("0.01"))
        expected_payable = (expected_per_day * Decimal(expected_paid_days)).quantize(Decimal("0.01"))
        expected_net = (expected_payable - Decimal("500.00")).quantize(Decimal("0.01"))

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("salary-monthly"),
            {"month": self.target_month, "year": self.target_year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        self.assertEqual(row["present_days"], 2)
        self.assertEqual(row["no_duty_days"], expected_no_duty_days)
        self.assertEqual(row["leave_days"], 1)
        self.assertEqual(row["weekly_off_days"], sunday_count)
        self.assertEqual(Decimal(str(row["advance_amount"])), Decimal("500.00"))
        self.assertEqual(row["paid_days"], expected_paid_days)
        self.assertEqual(Decimal(str(row["payable_amount"])), expected_payable)
        self.assertEqual(Decimal(str(row["net_payable_amount"])), expected_net)

    def test_salary_monthly_summary_defaults_unmarked_non_working_day_to_no_duty(self):
        work_day_one, absent_day = self._first_non_sunday_dates(2)
        self._create_attendance(work_day_one, 1000, 1040)
        DriverDailyAttendanceMark.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            date=absent_day,
            status=DriverDailyAttendanceMark.Status.ABSENT,
            marked_by=self.transporter_user,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("salary-monthly"),
            {"month": self.target_month, "year": self.target_year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        total_days = monthrange(self.target_year, self.target_month)[1]
        sunday_count = sum(
            1
            for day in range(1, total_days + 1)
            if date(self.target_year, self.target_month, day).weekday() == 6
        )
        expected_no_duty = total_days - sunday_count - 1 - 1
        self.assertEqual(row["present_days"], 1)
        self.assertEqual(row["weekly_off_days"], sunday_count)
        self.assertEqual(row["absent_days"], 1)
        self.assertEqual(row["no_duty_days"], expected_no_duty)

    def test_salary_monthly_summary_ignores_days_before_joined_transporter_date(self):
        join_date = self.month_start + timedelta(days=9)
        self.driver.joined_transporter_at = timezone.make_aware(
            datetime.combine(join_date, datetime.min.time())
        )
        self.driver.save(update_fields=["joined_transporter_at"])

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("salary-monthly"),
            {"month": self.target_month, "year": self.target_year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        pre_join_days = join_date.day - 1
        total_days = monthrange(self.target_year, self.target_month)[1]
        sunday_count_after_join = sum(
            1
            for day in range(join_date.day, total_days + 1)
            if date(self.target_year, self.target_month, day).weekday() == 6
        )
        payable_sundays_after_join = sum(
            1
            for day in range(join_date.day, total_days + 1)
            if date(self.target_year, self.target_month, day).weekday() == 6
            and date(self.target_year, self.target_month, day)
            - timedelta(days=date(self.target_year, self.target_month, day).weekday())
            >= join_date
        )
        expected_no_duty = total_days - pre_join_days - sunday_count_after_join
        self.assertEqual(row["present_days"], 0)
        self.assertEqual(row["absent_days"], 0)
        self.assertEqual(row["leave_days"], 0)
        self.assertEqual(row["weekly_off_days"], payable_sundays_after_join)
        self.assertEqual(
            row["unpaid_weekly_off_days"],
            sunday_count_after_join - payable_sundays_after_join,
        )
        self.assertEqual(row["no_duty_days"], expected_no_duty)

    def test_salary_monthly_summary_does_not_pay_first_partial_week_sunday(self):
        join_date = self.month_start
        while join_date.weekday() != 5:
            join_date += timedelta(days=1)
        self.driver.joined_transporter_at = timezone.make_aware(
            datetime.combine(join_date, datetime.min.time())
        )
        self.driver.save(update_fields=["joined_transporter_at"])

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.get(
            reverse("salary-monthly"),
            {"month": self.target_month, "year": self.target_year},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["rows"][0]
        first_sunday = join_date + timedelta(days=1)
        self.assertEqual(first_sunday.weekday(), 6)
        total_sundays_after_join = sum(
            1
            for day in range(join_date.day, monthrange(self.target_year, self.target_month)[1] + 1)
            if date(self.target_year, self.target_month, day).weekday() == 6
        )
        self.assertEqual(row["weekly_off_days"], total_sundays_after_join - 1)
        self.assertEqual(row["unpaid_weekly_off_days"], 1)

    def test_future_dates_do_not_count_as_no_duty(self):
        current_month_start = date(2026, 3, 1)
        self.driver.joined_transporter_at = timezone.make_aware(
            datetime.combine(current_month_start, datetime.min.time())
        )
        self.driver.save(update_fields=["joined_transporter_at"])

        summary = calculate_salary_summary_for_driver(
            driver=self.driver,
            month=3,
            year=2026,
            today=date(2026, 3, 7),
        )

        payable_sundays = sum(
            1
            for day in range(1, 8)
            if date(2026, 3, day).weekday() == 6
            and date(2026, 3, day) - timedelta(days=date(2026, 3, day).weekday())
            >= current_month_start
        )
        working_days_elapsed = sum(
            1
            for day in range(1, 8)
            if date(2026, 3, day).weekday() != 6
        )
        self.assertEqual(summary["future_days"], 24)
        self.assertEqual(summary["no_duty_days"], working_days_elapsed)
        self.assertEqual(summary["weekly_off_days"], payable_sundays)
        self.assertEqual(summary["unpaid_weekly_off_days"], 1)
        self.assertEqual(summary["paid_days"], working_days_elapsed + payable_sundays)

    def test_salary_pay_creates_payment_settles_advances_and_notifies_driver(self):
        work_day_one, _, _, leave_day, advance_day = self._first_non_sunday_dates(5)
        self._create_attendance(work_day_one, 1000, 1040)
        DriverDailyAttendanceMark.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            date=leave_day,
            status=DriverDailyAttendanceMark.Status.LEAVE,
            marked_by=self.transporter_user,
        )
        advance = DriverSalaryAdvance.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            amount=Decimal("750.00"),
            advance_date=advance_day,
            recorded_by=self.transporter_user,
        )

        self.client.force_authenticate(user=self.transporter_user)
        response = self.client.post(
            reverse("driver-salary-pay"),
            {
                "driver_id": self.driver.id,
                "month": self.target_month,
                "year": self.target_year,
                "cl_count": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = DriverSalaryPayment.objects.get(
            driver=self.driver,
            salary_month=self.target_month,
            salary_year=self.target_year,
        )
        advance.refresh_from_db()
        self.assertEqual(advance.settled_payment_id, payment.id)
        self.assertEqual(payment.cl_count, 1)
        self.assertTrue(
            DriverNotification.objects.filter(
                driver=self.driver,
                notification_type=DriverNotification.Type.SALARY_PAID,
            ).exists()
        )

    def test_salary_advance_create_and_update_notify_driver(self):
        self.client.force_authenticate(user=self.transporter_user)
        create_response = self.client.post(
            reverse("salary-advances"),
            {
                "driver_id": self.driver.id,
                "amount": "500.00",
                "advance_date": self.month_start.isoformat(),
                "notes": "Festival advance",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        advance_id = create_response.data["advance"]["id"]
        self.assertTrue(
            DriverNotification.objects.filter(
                driver=self.driver,
                notification_type=DriverNotification.Type.ADVANCE_UPDATED,
            ).exists()
        )

        update_response = self.client.patch(
            reverse("salary-advance-detail", kwargs={"advance_id": advance_id}),
            {
                "amount": "650.00",
                "advance_date": self.month_start.isoformat(),
                "notes": "Updated advance",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_month_start_salary_balance_email_sent_once(self):
        work_day_one, _, _, _, advance_day = self._first_non_sunday_dates(5)
        self._create_attendance(work_day_one, 1000, 1040)
        DriverSalaryAdvance.objects.create(
            driver=self.driver,
            transporter=self.transporter,
            amount=Decimal("300.00"),
            advance_date=advance_day,
            recorded_by=self.transporter_user,
        )
        current_time = timezone.make_aware(
            datetime(
                year=self.target_year if self.target_month < 12 else self.target_year + 1,
                month=self.target_month + 1 if self.target_month < 12 else 1,
                day=1,
                hour=10,
                minute=0,
            )
        )

        sent = send_salary_balance_email_if_due(
            driver=self.driver,
            current_time=timezone.localtime(current_time),
        )
        sent_again = send_salary_balance_email_if_due(
            driver=self.driver,
            current_time=timezone.localtime(current_time),
        )

        self.assertTrue(sent)
        self.assertFalse(sent_again)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Salary Balance Statement", mail.outbox[0].subject)
        self.assertIn("TripMate Payroll", mail.outbox[0].body)
        self.assertIn("Unpaid Weekly Off Days", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertIn("Advance Collection Details", mail.outbox[0].alternatives[0][0])
        self.assertTrue(
            DriverSalaryEmailLog.objects.filter(
                driver=self.driver,
                salary_month=self.target_month,
                salary_year=self.target_year,
            ).exists()
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_manual_salary_email_sends_even_without_auto_schedule(self):
        sent = send_salary_balance_email_now(
            driver=self.driver,
            month=self.target_month,
            year=self.target_year,
            current_time=timezone.make_aware(datetime(2026, 3, 7, 10, 0)),
        )
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Salary Balance Statement", mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_auto_salary_email_skipped_when_transporter_toggle_disabled(self):
        self.transporter.salary_auto_email_enabled = False
        self.transporter.save(update_fields=["salary_auto_email_enabled"])

        with patch(
            "users.management.commands.process_scheduled_notifications.send_salary_balance_email_if_due"
        ) as mock_sender:
            call_command("process_scheduled_notifications")
        mock_sender.assert_not_called()
