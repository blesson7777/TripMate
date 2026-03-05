from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Attendance(models.Model):
    class Status(models.TextChoices):
        ON_DUTY = "ON_DUTY", "On Duty"
        NO_TRIP = "NO_TRIP", "No Trip"
        LEAVE = "LEAVE", "Leave"

    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ON_DUTY)
    start_km = models.PositiveIntegerField()
    end_km = models.PositiveIntegerField(null=True, blank=True)
    odo_start_image = models.ImageField(upload_to="attendance/odo_start/")
    odo_end_image = models.ImageField(upload_to="attendance/odo_end/", null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    end_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "date"],
                name="unique_driver_attendance_per_day",
            )
        ]

    def clean(self):
        if self.vehicle.transporter_id != self.driver.transporter_id:
            raise ValidationError("Vehicle and driver transporter must match.")
        if self.end_km is not None and self.end_km < self.start_km:
            raise ValidationError("End KM must be greater than or equal to Start KM.")

    @property
    def total_km(self):
        if self.end_km is None:
            return 0
        return self.end_km - self.start_km

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.driver.user.username} - {self.date}"


class DriverDailyAttendanceMark(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ABSENT = "ABSENT", "Absent"

    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="daily_marks",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices)
    marked_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_marks",
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "driver__user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "date"],
                name="unique_driver_mark_per_day",
            )
        ]

    def __str__(self):
        return f"{self.driver.user.username} - {self.date} - {self.status}"
