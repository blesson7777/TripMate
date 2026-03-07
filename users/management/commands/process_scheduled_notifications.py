from django.core.management.base import BaseCommand
from django.utils import timezone

from drivers.models import Driver
from salary.email_utils import send_salary_balance_email_if_due
from users.models import Transporter
from users.notification_utils import (
    ensure_time_based_driver_notifications,
    ensure_time_based_transporter_notifications,
)


class Command(BaseCommand):
    help = "Generate scheduled driver/transporter notifications and dispatch push alerts."

    def handle(self, *args, **options):
        now = timezone.localtime()
        transporter_count = 0
        driver_count = 0
        salary_email_count = 0

        for transporter in Transporter.objects.select_related("user").all():
            ensure_time_based_transporter_notifications(transporter, current_time=now)
            transporter_count += 1

        for driver in Driver.objects.select_related("user", "transporter").filter(
            is_active=True,
            user__is_active=True,
        ):
            ensure_time_based_driver_notifications(driver, current_time=now)
            if (
                driver.transporter_id
                and driver.transporter
                and driver.transporter.salary_auto_email_enabled
                and send_salary_balance_email_if_due(driver=driver, current_time=now)
            ):
                salary_email_count += 1
            driver_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                (
                    "Processed scheduled notifications for "
                    f"{transporter_count} transporters and {driver_count} drivers. "
                    f"Salary emails sent: {salary_email_count}."
                )
            )
        )
