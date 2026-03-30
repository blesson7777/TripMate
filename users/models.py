import uuid

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
    session_revoked_at = models.DateTimeField(null=True, blank=True)
    session_nonce = models.UUIDField(default=uuid.uuid4, editable=False)

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
    gstin = models.CharField(max_length=32, blank=True)
    pan = models.CharField(max_length=32, blank=True)
    website = models.CharField(max_length=120, blank=True)
    logo = models.ImageField(upload_to="transporters/logos/%Y/%m/", null=True, blank=True)
    diesel_tracking_enabled = models.BooleanField(default=False)
    diesel_readings_enabled = models.BooleanField(default=False)
    location_tracking_enabled = models.BooleanField(default=True)
    salary_auto_email_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name


class FeatureToggleLog(models.Model):
    class Action(models.TextChoices):
        ENABLED = "ENABLED", "Enabled"
        DISABLED = "DISABLED", "Disabled"

    admin = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="feature_toggle_logs",
        limit_choices_to={"role": User.Role.ADMIN},
    )
    partner = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="feature_toggle_logs",
    )
    feature_name = models.CharField(max_length=80, default="diesel_module")
    action = models.CharField(max_length=20, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.admin.username} {self.action.lower()} "
            f"{self.feature_name} for {self.partner.company_name}"
        )


class TransporterNotification(models.Model):
    class Type(models.TextChoices):
        TRIP_STARTED = "TRIP_STARTED", "Trip Started"
        TRIP_CLOSED = "TRIP_CLOSED", "Trip Closed"
        START_DAY_REMINDER = "START_DAY_REMINDER", "Start Day Reminder"
        OPEN_TRIP_ALERT = "OPEN_TRIP_ALERT", "Open Trip Alert"
        TRIP_OVERDUE = "TRIP_OVERDUE", "Trip Overdue"
        FUEL_ANOMALY = "FUEL_ANOMALY", "Fuel Anomaly"
        MONTH_END_REMINDER = "MONTH_END_REMINDER", "Month End Reminder"
        DIESEL_MODULE_TOGGLED = "DIESEL_MODULE_TOGGLED", "Diesel Module Toggled"
        SYSTEM = "SYSTEM", "System"

    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(max_length=40, choices=Type.choices)
    title = models.CharField(max_length=160)
    message = models.TextField()
    event_key = models.CharField(max_length=140, null=True, blank=True, unique=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transporter.company_name}: {self.title}"

class DriverNotification(models.Model):
    class Type(models.TextChoices):
        ATTENDANCE_MARK_UPDATED = "ATTENDANCE_MARK_UPDATED", "Attendance Mark Updated"
        START_DAY_MISSED = "START_DAY_MISSED", "Start Day Missed"
        TRIP_OVERDUE = "TRIP_OVERDUE", "Trip Overdue"
        FUEL_ANOMALY = "FUEL_ANOMALY", "Fuel Anomaly"
        DIESEL_MODULE_TOGGLED = "DIESEL_MODULE_TOGGLED", "Diesel Module Toggled"
        MONTH_END_REMINDER = "MONTH_END_REMINDER", "Month End Reminder"
        WELCOME_ALLOCATED = "WELCOME_ALLOCATED", "Welcome Allocated"
        SALARY_PAID = "SALARY_PAID", "Salary Paid"
        ADVANCE_UPDATED = "ADVANCE_UPDATED", "Advance Updated"
        SYSTEM = "SYSTEM", "System"

    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="driver_notifications",
    )
    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.SET_NULL,
        related_name="driver_notifications",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(max_length=40, choices=Type.choices)
    title = models.CharField(max_length=160)
    message = models.TextField()
    event_key = models.CharField(max_length=140, null=True, blank=True, unique=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.driver.user.username}: {self.title}"


class AdminBroadcastNotification(models.Model):
    class Audience(models.TextChoices):
        ALL = "ALL", "All"
        DRIVER = "DRIVER", "Driver"
        TRANSPORTER = "TRANSPORTER", "Transporter"

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="broadcast_notifications",
        limit_choices_to={"role": User.Role.ADMIN},
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.audience}] {self.title}"


class UserDeviceToken(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"
        WEB = "WEB", "Web"

    class AppVariant(models.TextChoices):
        DRIVER = "DRIVER", "Driver"
        TRANSPORTER = "TRANSPORTER", "Transporter"
        GENERIC = "GENERIC", "Generic"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token = models.CharField(max_length=255, unique=True)
    app_version = models.CharField(max_length=32, blank=True)
    app_build_number = models.PositiveIntegerField(null=True, blank=True)
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.ANDROID,
    )
    app_variant = models.CharField(
        max_length=20,
        choices=AppVariant.choices,
        default=AppVariant.GENERIC,
    )
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} [{self.app_variant}]"


class AppRelease(models.Model):
    class AppVariant(models.TextChoices):
        DRIVER = "DRIVER", "Driver"
        TRANSPORTER = "TRANSPORTER", "Transporter"

    app_variant = models.CharField(max_length=20, choices=AppVariant.choices)
    version_name = models.CharField(max_length=32)
    build_number = models.PositiveIntegerField()
    apk_file = models.FileField(upload_to="app_updates/%Y/%m/")
    force_update = models.BooleanField(default=False)
    message = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    push_sent_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="uploaded_app_releases",
        null=True,
        blank=True,
        limit_choices_to={"role": User.Role.ADMIN},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["app_variant", "-build_number", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["app_variant", "version_name", "build_number"],
                name="unique_app_release_variant_version_build",
            ),
        ]

    def __str__(self):
        return f"{self.get_app_variant_display()} {self.version_name} ({self.build_number})"


class AuthSessionEvent(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login Success"
        LOGOUT_NORMAL = "LOGOUT_NORMAL", "Normal Logout"
        LOGOUT_FORCED = "LOGOUT_FORCED", "Forced Logout"
        TOKEN_EXPIRED = "TOKEN_EXPIRED", "Token Expired"
        TOKEN_INVALID = "TOKEN_INVALID", "Token Invalid"

    class AppVariant(models.TextChoices):
        DRIVER = "DRIVER", "Driver"
        TRANSPORTER = "TRANSPORTER", "Transporter"
        ADMIN = "ADMIN", "Admin"
        UNKNOWN = "UNKNOWN", "Unknown"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="auth_session_events",
        null=True,
        blank=True,
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, blank=True)
    app_variant = models.CharField(
        max_length=20,
        choices=AppVariant.choices,
        default=AppVariant.UNKNOWN,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    reason = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    token_jti = models.CharField(max_length=64, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["app_variant", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} {self.username or '-'} @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class AccountDeletionRequest(models.Model):
    class Source(models.TextChoices):
        APP = "APP", "In-App"
        WEB = "WEB", "Website"

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        COMPLETED = "COMPLETED", "Completed"
        REJECTED = "REJECTED", "Rejected"

    email = models.EmailField(db_index=True)
    role = models.CharField(max_length=20, choices=User.Role.choices)
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="account_deletion_requests",
        null=True,
        blank=True,
    )
    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.WEB,
    )
    note = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="processed_account_deletion_requests",
        null=True,
        blank=True,
        limit_choices_to={"role": User.Role.ADMIN},
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["email", "requested_at"]),
            models.Index(fields=["status", "requested_at"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.role}) - {self.status}"


class EmailOTP(models.Model):
    class Purpose(models.TextChoices):
        TRANSPORTER_SIGNUP = "TRANSPORTER_SIGNUP", "Transporter Signup"
        DRIVER_SIGNUP = "DRIVER_SIGNUP", "Driver Signup"
        TRANSPORTER_LOGIN = "TRANSPORTER_LOGIN", "Transporter Login"
        DRIVER_LOGIN = "DRIVER_LOGIN", "Driver Login"
        DRIVER_ALLOCATION = "DRIVER_ALLOCATION", "Driver Allocation"
        PASSWORD_RESET = "PASSWORD_RESET", "Password Reset"
        PROFILE_EMAIL_CHANGE = "PROFILE_EMAIL_CHANGE", "Profile Email Change"
        ACCOUNT_DELETION = "ACCOUNT_DELETION", "Account Deletion"

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
