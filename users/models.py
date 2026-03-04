from django.contrib.auth.models import AbstractUser
from django.db import models


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
