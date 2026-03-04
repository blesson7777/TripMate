from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class FuelRecord(models.Model):
    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    liters = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    meter_image = models.ImageField(upload_to="fuel/meter/")
    bill_image = models.ImageField(upload_to="fuel/bill/")
    date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def clean(self):
        if self.attendance.driver_id != self.driver_id:
            raise ValidationError("Fuel record driver must match attendance driver.")
        if self.attendance.vehicle_id != self.vehicle_id:
            raise ValidationError("Fuel record vehicle must match attendance vehicle.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vehicle.vehicle_number} - {self.date}"
