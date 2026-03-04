from django.core.exceptions import ValidationError
from django.db import models


class Trip(models.Model):
    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.CASCADE,
        related_name="trips",
    )
    start_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    start_km = models.PositiveIntegerField()
    end_km = models.PositiveIntegerField()
    total_km = models.PositiveIntegerField(default=0)
    purpose = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.end_km < self.start_km:
            raise ValidationError("Trip end_km must be greater than or equal to start_km.")

    def save(self, *args, **kwargs):
        self.total_km = self.end_km - self.start_km
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.start_location} -> {self.destination} ({self.total_km} km)"
