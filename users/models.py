from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TRANSPORTER = "TRANSPORTER", "Transporter"
        DRIVER = "DRIVER", "Driver"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DRIVER)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class Transporter(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="transporter_profile",
        limit_choices_to={"role": User.Role.TRANSPORTER},
    )
    company_name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name


class EmailOTP(models.Model):
    class Purpose(models.TextChoices):
        TRANSPORTER_SIGNUP = "TRANSPORTER_SIGNUP", "Transporter Signup"
        DRIVER_SIGNUP = "DRIVER_SIGNUP", "Driver Signup"
        DRIVER_ALLOCATION = "DRIVER_ALLOCATION", "Driver Allocation"

    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=40, choices=Purpose.choices)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "purpose", "created_at"]),
        ]

    def is_valid(self):
        return not self.is_used and self.expires_at >= timezone.now()
