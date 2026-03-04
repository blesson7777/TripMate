from django.db import models


class Vehicle(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        INACTIVE = "INACTIVE", "Inactive"

    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    vehicle_number = models.CharField(max_length=30)
    model = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vehicle_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["transporter", "vehicle_number"],
                name="unique_vehicle_number_per_transporter",
            )
        ]

    def __str__(self):
        return self.vehicle_number
