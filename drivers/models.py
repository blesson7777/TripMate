from django.core.exceptions import ValidationError
from django.db import models


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

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username
