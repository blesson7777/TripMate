from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class DriverSalaryPayment(models.Model):
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="salary_payments",
    )
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="salary_payments",
    )
    salary_year = models.PositiveIntegerField()
    salary_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    month_start = models.DateField()
    month_end = models.DateField()
    total_days_in_month = models.PositiveSmallIntegerField()
    future_days = models.PositiveSmallIntegerField(default=0)
    present_days = models.PositiveSmallIntegerField(default=0)
    no_duty_days = models.PositiveSmallIntegerField(default=0)
    weekly_off_days = models.PositiveSmallIntegerField(default=0)
    leave_days = models.PositiveSmallIntegerField(default=0)
    cl_count = models.PositiveSmallIntegerField(default=0)
    paid_leave_days = models.PositiveSmallIntegerField(default=0)
    absent_days = models.PositiveSmallIntegerField(default=0)
    paid_days = models.PositiveSmallIntegerField(default=0)
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    per_day_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    payable_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    advance_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    net_paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    notes = models.CharField(max_length=255, blank=True, default="")
    paid_at = models.DateTimeField(default=timezone.now)
    paid_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_salary_payments_made",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-salary_year", "-salary_month", "driver__user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "salary_year", "salary_month"],
                name="unique_salary_payment_per_driver_month",
            )
        ]

    def clean(self):
        if self.driver.transporter_id != self.transporter_id:
            raise ValidationError("Driver and transporter must match.")
        if self.paid_by_id and self.paid_by.role != "TRANSPORTER":
            raise ValidationError("Salary payments can only be marked by transporter users.")

    def __str__(self):
        return (
            f"{self.driver.user.username} salary {self.salary_month:02d}/{self.salary_year} "
            f"- {self.payable_amount}"
        )


class DriverSalaryAdvance(models.Model):
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="salary_advances",
    )
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="salary_advances",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    advance_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=255, blank=True, default="")
    recorded_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_salary_advances_recorded",
    )
    settled_payment = models.ForeignKey(
        "salary.DriverSalaryPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_advances",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-advance_date", "-created_at"]

    def clean(self):
        if self.driver.transporter_id != self.transporter_id:
            raise ValidationError("Driver and transporter must match.")
        if self.recorded_by_id and self.recorded_by.role != "TRANSPORTER":
            raise ValidationError("Advances can only be recorded by transporter users.")

    def __str__(self):
        return f"{self.driver.user.username} advance {self.advance_date.isoformat()} - {self.amount}"


class DriverSalaryEmailLog(models.Model):
    class EmailType(models.TextChoices):
        BALANCE_ACK = "BALANCE_ACK", "Balance Acknowledgement"

    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="salary_email_logs",
    )
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="salary_email_logs",
    )
    salary_year = models.PositiveIntegerField()
    salary_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    email_type = models.CharField(max_length=30, choices=EmailType.choices)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "salary_year", "salary_month", "email_type"],
                name="unique_salary_email_per_driver_month_type",
            )
        ]

    def clean(self):
        if self.driver.transporter_id != self.transporter_id:
            raise ValidationError("Driver and transporter must match.")

    def __str__(self):
        return (
            f"{self.driver.user.username} {self.email_type} "
            f"{self.salary_month:02d}/{self.salary_year}"
        )
