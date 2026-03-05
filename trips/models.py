from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.db.models import Q


class Trip(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.CASCADE,
        related_name="trips",
    )
    parent_trip = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="child_trips",
        null=True,
        blank=True,
    )
    start_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    start_km = models.PositiveIntegerField()
    end_km = models.PositiveIntegerField(null=True, blank=True)
    total_km = models.PositiveIntegerField(default=0)
    purpose = models.TextField(blank=True)
    start_odo_image = models.ImageField(upload_to="trips/odo_start/", null=True, blank=True)
    end_odo_image = models.ImageField(upload_to="trips/odo_end/", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CLOSED)
    is_day_trip = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["attendance"],
                condition=Q(is_day_trip=True, parent_trip__isnull=True),
                name="unique_master_trip_per_attendance",
            ),
        ]

    def clean(self):
        if self.end_km is not None and self.end_km < self.start_km:
            raise ValidationError("Trip end_km must be greater than or equal to start_km.")
        if self.status == self.Status.CLOSED and self.end_km is None:
            raise ValidationError("Closed trip must include end_km.")
        if self.is_day_trip and self.parent_trip_id is not None:
            raise ValidationError("Master day trip cannot have a parent trip.")
        if not self.is_day_trip and self.parent_trip_id is None:
            raise ValidationError("Child trip must reference a master trip.")
        if self.parent_trip_id is not None:
            if self.parent_trip.attendance_id != self.attendance_id:
                raise ValidationError("Child trip must belong to the same attendance as its master.")
            if not self.parent_trip.is_day_trip:
                raise ValidationError("Child trip parent must be a master day trip.")

    def save(self, *args, **kwargs):
        if self.status == self.Status.OPEN:
            self.end_km = None
            self.ended_at = None
            self.total_km = 0
        else:
            if self.end_km is None:
                self.end_km = self.start_km
            if self.ended_at is None:
                self.ended_at = timezone.now()
            self.total_km = max(self.end_km - self.start_km, 0)

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.start_location} -> {self.destination} ({self.total_km} km)"
