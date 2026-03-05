import os
import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from users.models import EmailOTP


def _otp_expiry_minutes():
    raw = os.getenv("OTP_EXPIRY_MINUTES", "10")
    try:
        value = int(raw)
    except ValueError:
        return 10
    return max(value, 1)


def _generate_code():
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _ensure_email_backend_ready():
    if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise RuntimeError(
                "Email service is not configured. Set DJANGO_EMAIL_HOST_USER and DJANGO_EMAIL_HOST_PASSWORD."
            )


def _send_signup_otp(email, purpose, subject):
    _ensure_email_backend_ready()

    normalized_email = email.strip().lower()
    expiry_minutes = _otp_expiry_minutes()
    code = _generate_code()
    expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

    otp = EmailOTP.objects.create(
        email=normalized_email,
        code=code,
        purpose=purpose,
        expires_at=expires_at,
    )

    message = (
        f"Your TripMate OTP is {code}.\n"
        f"It expires in {expiry_minutes} minutes."
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[normalized_email],
        fail_silently=False,
    )

    return otp


def send_transporter_signup_otp(email):
    return _send_signup_otp(
        email=email,
        purpose=EmailOTP.Purpose.TRANSPORTER_SIGNUP,
        subject="TripMate Transporter Signup OTP",
    )


def send_driver_signup_otp(email):
    return _send_signup_otp(
        email=email,
        purpose=EmailOTP.Purpose.DRIVER_SIGNUP,
        subject="TripMate Driver Signup OTP",
    )


def send_driver_allocation_otp(email):
    return _send_signup_otp(
        email=email,
        purpose=EmailOTP.Purpose.DRIVER_ALLOCATION,
        subject="TripMate Driver Allocation OTP",
    )
