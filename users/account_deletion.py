from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from users.models import AccountDeletionRequest


def _deleted_identity_suffix(user) -> str:
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"{user.pk}-{timestamp}-{uuid.uuid4().hex[:6]}"


def perform_account_deletion(
    user,
    *,
    source: str,
    note: str = "",
    processed_at=None,
    processed_by=None,
    existing_request: AccountDeletionRequest | None = None,
) -> AccountDeletionRequest:
    deleted_at = processed_at or timezone.now()
    unique_suffix = _deleted_identity_suffix(user)
    deleted_username = f"deleted-{user.role.lower()}-{unique_suffix}"[:150]
    deleted_email = f"deleted+{unique_suffix}@tripmate.local"[:254]

    with transaction.atomic():
        deletion_request = existing_request
        if deletion_request is None:
            deletion_request = (
                AccountDeletionRequest.objects.filter(
                    user=user,
                    source=source,
                )
                .order_by("-requested_at")
                .first()
            )
        if deletion_request is None:
            deletion_request = AccountDeletionRequest.objects.create(
                email=(user.email or "").strip().lower(),
                role=user.role,
                user=user,
                source=source,
                note=note,
                status=AccountDeletionRequest.Status.COMPLETED,
                processed_at=deleted_at,
                processed_by=processed_by,
            )
        else:
            deletion_request.email = (user.email or "").strip().lower()
            deletion_request.role = user.role
            deletion_request.note = note
            deletion_request.status = AccountDeletionRequest.Status.COMPLETED
            deletion_request.processed_at = deleted_at
            deletion_request.processed_by = processed_by
            deletion_request.save(
                update_fields=[
                    "email",
                    "role",
                    "note",
                    "status",
                    "processed_at",
                    "processed_by",
                ]
            )

        driver = getattr(user, "driver_profile", None)
        if driver is not None:
            driver_update_fields = []
            if driver.is_active:
                driver.is_active = False
                driver_update_fields.append("is_active")
            if driver.assigned_vehicle_id is not None:
                driver.assigned_vehicle = None
                driver_update_fields.append("assigned_vehicle")
            if driver.default_service_id is not None:
                driver.default_service = None
                driver_update_fields.append("default_service")
            license_number = (driver.license_number or "").strip()
            if license_number and not license_number.upper().startswith("DELETED-"):
                driver.license_number = (
                    f"DELETED-{driver.pk}-{deleted_at.strftime('%Y%m%d%H%M%S')}"
                )[:50]
                driver_update_fields.append("license_number")
            if driver_update_fields:
                driver.save(update_fields=driver_update_fields)

        user.username = deleted_username
        user.email = deleted_email
        user.phone = ""
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()
        update_fields = [
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "is_active",
            "password",
        ]
        if processed_at is not None:
            user.session_revoked_at = processed_at
            update_fields.append("session_revoked_at")
        user.save(update_fields=update_fields)

    return deletion_request
