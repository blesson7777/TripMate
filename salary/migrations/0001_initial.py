import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("drivers", "0005_driver_monthly_salary"),
        ("users", "0011_alter_drivernotification_notification_type_salary"),
    ]

    operations = [
        migrations.CreateModel(
            name="DriverSalaryPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("salary_year", models.PositiveIntegerField()),
                (
                    "salary_month",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(12),
                        ]
                    ),
                ),
                ("month_start", models.DateField()),
                ("month_end", models.DateField()),
                ("total_days_in_month", models.PositiveSmallIntegerField()),
                ("future_days", models.PositiveSmallIntegerField(default=0)),
                ("present_days", models.PositiveSmallIntegerField(default=0)),
                ("no_duty_days", models.PositiveSmallIntegerField(default=0)),
                ("weekly_off_days", models.PositiveSmallIntegerField(default=0)),
                ("leave_days", models.PositiveSmallIntegerField(default=0)),
                ("cl_count", models.PositiveSmallIntegerField(default=0)),
                ("paid_leave_days", models.PositiveSmallIntegerField(default=0)),
                ("absent_days", models.PositiveSmallIntegerField(default=0)),
                ("paid_days", models.PositiveSmallIntegerField(default=0)),
                (
                    "monthly_salary",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "per_day_salary",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "payable_amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "advance_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "net_paid_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("paid_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_payments",
                        to="drivers.driver",
                    ),
                ),
                (
                    "paid_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="driver_salary_payments_made",
                        to="users.user",
                    ),
                ),
                (
                    "transporter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_payments",
                        to="users.transporter",
                    ),
                ),
            ],
            options={
                "ordering": ["-salary_year", "-salary_month", "driver__user__username"],
            },
        ),
        migrations.CreateModel(
            name="DriverSalaryAdvance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("advance_date", models.DateField(default=django.utils.timezone.localdate)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_advances",
                        to="drivers.driver",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="driver_salary_advances_recorded",
                        to="users.user",
                    ),
                ),
                (
                    "settled_payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="applied_advances",
                        to="salary.driversalarypayment",
                    ),
                ),
                (
                    "transporter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_advances",
                        to="users.transporter",
                    ),
                ),
            ],
            options={
                "ordering": ["-advance_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DriverSalaryEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("salary_year", models.PositiveIntegerField()),
                (
                    "salary_month",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(12),
                        ]
                    ),
                ),
                (
                    "email_type",
                    models.CharField(
                        choices=[("BALANCE_ACK", "Balance Acknowledgement")],
                        max_length=30,
                    ),
                ),
                ("sent_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_email_logs",
                        to="drivers.driver",
                    ),
                ),
                (
                    "transporter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="salary_email_logs",
                        to="users.transporter",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="driversalarypayment",
            constraint=models.UniqueConstraint(
                fields=("driver", "salary_year", "salary_month"),
                name="unique_salary_payment_per_driver_month",
            ),
        ),
        migrations.AddConstraint(
            model_name="driversalaryemaillog",
            constraint=models.UniqueConstraint(
                fields=("driver", "salary_year", "salary_month", "email_type"),
                name="unique_salary_email_per_driver_month_type",
            ),
        ),
    ]
