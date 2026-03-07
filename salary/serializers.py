from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from drivers.models import Driver
from salary.models import DriverSalaryAdvance, DriverSalaryPayment
from salary.utils import calculate_salary_summary_for_driver, can_pay_salary_for_month
from users.notification_utils import (
    create_salary_advance_updated_notification,
    create_salary_paid_notification,
)


class DriverSalaryMonthRowSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    driver_name = serializers.CharField()
    driver_phone = serializers.CharField(allow_blank=True)
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    month_start = serializers.DateField()
    month_end = serializers.DateField()
    salary_due_date = serializers.DateField()
    can_pay = serializers.BooleanField()
    total_days_in_month = serializers.IntegerField()
    future_days = serializers.IntegerField()
    present_days = serializers.IntegerField()
    no_duty_days = serializers.IntegerField()
    weekly_off_days = serializers.IntegerField()
    unpaid_weekly_off_days = serializers.IntegerField()
    leave_days = serializers.IntegerField()
    cl_count = serializers.IntegerField()
    paid_leave_days = serializers.IntegerField()
    unpaid_leave_days = serializers.IntegerField()
    absent_days = serializers.IntegerField()
    paid_days = serializers.IntegerField()
    monthly_salary = serializers.DecimalField(max_digits=12, decimal_places=2)
    per_day_salary = serializers.DecimalField(max_digits=12, decimal_places=2)
    payable_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    advance_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_payable_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_status = serializers.CharField()
    is_paid = serializers.BooleanField()
    paid_at = serializers.DateTimeField(allow_null=True)
    paid_by_username = serializers.CharField(allow_null=True, allow_blank=True)
    payment_id = serializers.IntegerField(allow_null=True)
    notes = serializers.CharField(allow_blank=True)


class SalaryMonthSummarySerializer(serializers.Serializer):
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    month_start = serializers.DateField()
    month_end = serializers.DateField()
    salary_due_date = serializers.DateField()
    total_drivers = serializers.IntegerField()
    paid_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    total_payable_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    rows = DriverSalaryMonthRowSerializer(many=True)


class DriverMonthlySalaryUpdateSerializer(serializers.Serializer):
    monthly_salary = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
    )

    def save(self):
        driver = self.context["driver"]
        driver.monthly_salary = self.validated_data["monthly_salary"]
        driver.save(update_fields=["monthly_salary"])
        return driver


class DriverSalaryPaySerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    year = serializers.IntegerField(min_value=2020)
    cl_count = serializers.IntegerField(min_value=0, default=0)
    monthly_salary = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        request = self.context["request"]
        transporter = request.user.transporter_profile
        driver = (
            Driver.objects.select_related("user", "transporter")
            .filter(id=attrs["driver_id"], transporter=transporter, is_active=True)
            .first()
        )
        if driver is None:
            raise serializers.ValidationError({"driver_id": "Driver not found for this transporter."})

        if DriverSalaryPayment.objects.filter(
            driver=driver,
            transporter=transporter,
            salary_month=attrs["month"],
            salary_year=attrs["year"],
        ).exists():
            raise serializers.ValidationError({"detail": "Salary already paid for this driver and month."})

        if not can_pay_salary_for_month(
            month=attrs["month"],
            year=attrs["year"],
            today=timezone.localdate(),
        ):
            raise serializers.ValidationError(
                {"detail": "Salary can be paid only after the selected month is completed."}
            )

        effective_salary = attrs.get("monthly_salary", driver.monthly_salary)
        if effective_salary is None or effective_salary <= 0:
            raise serializers.ValidationError(
                {"monthly_salary": "Monthly salary must be set before paying salary."}
            )

        attrs["driver"] = driver
        return attrs

    def save(self):
        request = self.context["request"]
        transporter = request.user.transporter_profile
        driver = self.validated_data["driver"]
        month = self.validated_data["month"]
        year = self.validated_data["year"]
        cl_count = self.validated_data.get("cl_count", 0)
        notes = self.validated_data.get("notes", "").strip()
        monthly_salary = self.validated_data.get("monthly_salary")

        with transaction.atomic():
            if monthly_salary is not None:
                driver.monthly_salary = monthly_salary
                driver.save(update_fields=["monthly_salary"])

            summary = calculate_salary_summary_for_driver(
                driver=driver,
                month=month,
                year=year,
                cl_count=cl_count,
                today=timezone.localdate(),
            )

            payment = DriverSalaryPayment.objects.create(
                driver=driver,
                transporter=transporter,
                salary_year=year,
                salary_month=month,
                month_start=summary["month_start"],
                month_end=summary["month_end"],
                total_days_in_month=summary["total_days_in_month"],
                future_days=summary["future_days"],
                present_days=summary["present_days"],
                no_duty_days=summary["no_duty_days"],
                weekly_off_days=summary["weekly_off_days"],
                leave_days=summary["leave_days"],
                cl_count=summary["cl_count"],
                paid_leave_days=summary["paid_leave_days"],
                absent_days=summary["absent_days"],
                paid_days=summary["paid_days"],
                monthly_salary=summary["monthly_salary"],
                per_day_salary=summary["per_day_salary"],
                payable_amount=summary["payable_amount"],
                advance_amount=summary["advance_amount"],
                net_paid_amount=summary["net_payable_amount"],
                notes=notes,
                paid_at=timezone.now(),
                paid_by=request.user,
            )

            DriverSalaryAdvance.objects.filter(
                driver=driver,
                transporter=transporter,
                settled_payment__isnull=True,
                advance_date__gte=summary["month_start"],
                advance_date__lte=summary["month_end"],
            ).update(settled_payment=payment)

        create_salary_paid_notification(payment=payment)
        return payment


class DriverSalaryAdvanceSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    recorded_by_username = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = DriverSalaryAdvance
        fields = (
            "id",
            "driver",
            "driver_name",
            "amount",
            "advance_date",
            "notes",
            "settled_payment",
            "recorded_by_username",
            "created_at",
            "updated_at",
        )


class DriverSalaryAdvanceUpsertSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    advance_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        request = self.context["request"]
        transporter = request.user.transporter_profile
        instance = self.context.get("instance")
        driver = None

        if instance is None:
            driver = (
                Driver.objects.select_related("user")
                .filter(
                    id=attrs.get("driver_id"),
                    transporter=transporter,
                    is_active=True,
                )
                .first()
            )
            if driver is None:
                raise serializers.ValidationError({"driver_id": "Driver not found for this transporter."})
        else:
            driver = instance.driver
            if driver.transporter_id != transporter.id:
                raise serializers.ValidationError({"detail": "Advance does not belong to your transporter."})

        attrs["driver"] = driver
        attrs["advance_date"] = attrs.get("advance_date") or timezone.localdate()
        return attrs

    def save(self):
        request = self.context["request"]
        instance = self.context.get("instance")
        action_label = "Updated"
        if instance is None:
            action_label = "Added"
            advance = DriverSalaryAdvance.objects.create(
                driver=self.validated_data["driver"],
                transporter=request.user.transporter_profile,
                amount=self.validated_data["amount"],
                advance_date=self.validated_data["advance_date"],
                notes=self.validated_data.get("notes", "").strip(),
                recorded_by=request.user,
            )
        else:
            advance = instance
            advance.amount = self.validated_data["amount"]
            advance.advance_date = self.validated_data["advance_date"]
            advance.notes = self.validated_data.get("notes", "").strip()
            advance.recorded_by = request.user
            advance.save(
                update_fields=["amount", "advance_date", "notes", "recorded_by", "updated_at"]
            )

        create_salary_advance_updated_notification(
            advance=advance,
            action_label=action_label,
        )
        return advance
