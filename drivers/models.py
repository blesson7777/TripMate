from django.core.validators import MinValueValidator
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


DEFAULT_JOINED_TRANSPORTER_AT = timezone.make_aware(datetime(2016, 3, 1, 0, 0, 0))


class Driver(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="driver_profile",
        limit_choices_to={"role": "DRIVER"},
    )
    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers",
    )
    license_number = models.CharField(max_length=50, unique=True)
    assigned_vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers",
    )
    default_service = models.ForeignKey(
        "attendance.TransportService",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_drivers",
    )
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    joined_transporter_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def clean(self):
        if self.assigned_vehicle and self.transporter_id is None:
            raise ValidationError("Driver must be assigned to a transporter before vehicle assignment.")
        if self.assigned_vehicle and self.assigned_vehicle.transporter_id != self.transporter_id:
            raise ValidationError("Assigned vehicle must belong to the same transporter.")
        if self.default_service and self.transporter_id is None:
            raise ValidationError("Driver must be assigned to a transporter before service assignment.")
        if self.default_service and self.default_service.transporter_id != self.transporter_id:
            raise ValidationError("Default service must belong to the same transporter.")

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)

        previous_transporter_id = None
        if self.pk:
            previous_transporter_id = (
                Driver.objects.filter(pk=self.pk)
                .values_list("transporter_id", flat=True)
                .first()
            )

        joined_changed = False
        if self.transporter_id is None:
            if self.joined_transporter_at is not None:
                self.joined_transporter_at = None
                joined_changed = True
        elif self.joined_transporter_at is None:
            self.joined_transporter_at = timezone.now()
            joined_changed = True
        elif previous_transporter_id is not None and previous_transporter_id != self.transporter_id:
            self.joined_transporter_at = timezone.now()
            joined_changed = True

        if update_fields is not None and joined_changed:
            update_fields.add("joined_transporter_at")
            kwargs["update_fields"] = list(update_fields)

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def joined_transporter_date(self):
        reference = self.joined_transporter_at
        if reference is None and self.transporter_id is not None:
            reference = DEFAULT_JOINED_TRANSPORTER_AT
        reference = reference or self.created_at
        if reference is None:
            return None
        return timezone.localtime(reference).date()

    def __str__(self):
        return self.user.username
