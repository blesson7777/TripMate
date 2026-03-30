from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta

from django.utils import timezone

from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from users.models import AuthSessionEvent, User, UserDeviceToken


def _guess_app_variant(role: str | None) -> str:
    normalized = (role or "").strip().upper()
    if normalized == User.Role.DRIVER:
        return AuthSessionEvent.AppVariant.DRIVER
    if normalized == User.Role.TRANSPORTER:
        return AuthSessionEvent.AppVariant.TRANSPORTER
    if normalized == User.Role.ADMIN:
        return AuthSessionEvent.AppVariant.ADMIN
    return AuthSessionEvent.AppVariant.UNKNOWN


def _client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    remote_addr = request.META.get("REMOTE_ADDR", "").strip()
    return remote_addr or None


def _decode_unverified_claims(raw_token: str) -> dict:
    try:
        segments = raw_token.split(".")
        if len(segments) < 2:
            return {}
        payload = segments[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}")
        data = json.loads(decoded.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def _parse_exp_timestamp(value) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(
        datetime.fromtimestamp(timestamp),
        timezone.get_current_timezone(),
    )


def _dedupe_recent(event_type: str, username: str, path: str, token_jti: str) -> bool:
    recent_cutoff = timezone.now() - timedelta(minutes=10)
    return AuthSessionEvent.objects.filter(
        event_type=event_type,
        username=username,
        path=path,
        token_jti=token_jti,
        created_at__gte=recent_cutoff,
    ).exists()


def log_login_success(request, user: User) -> AuthSessionEvent:
    return AuthSessionEvent.objects.create(
        user=user,
        username=user.username,
        role=user.role,
        app_variant=_guess_app_variant(user.role),
        event_type=AuthSessionEvent.EventType.LOGIN_SUCCESS,
        reason="JWT issued successfully.",
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        status_code=200,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
    )


def log_normal_logout(request, user: User, reason: str = "User initiated logout.") -> AuthSessionEvent:
    return AuthSessionEvent.objects.create(
        user=user,
        username=user.username,
        role=user.role,
        app_variant=_guess_app_variant(user.role),
        event_type=AuthSessionEvent.EventType.LOGOUT_NORMAL,
        reason=reason,
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        status_code=200,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
    )


def log_forced_logout(request, user: User, reason: str = "Admin forced logout.") -> AuthSessionEvent:
    return AuthSessionEvent.objects.create(
        user=user,
        username=user.username,
        role=user.role,
        app_variant=_guess_app_variant(user.role),
        event_type=AuthSessionEvent.EventType.LOGOUT_FORCED,
        reason=reason,
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        status_code=200,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
    )


def token_issued_at(validated_token) -> datetime | None:
    try:
        issued_at = validated_token.get("iat")
    except Exception:
        return None
    return _parse_exp_timestamp(issued_at)


def revoke_user_sessions(user: User, *, when: datetime | None = None) -> datetime:
    revoked_at = when or timezone.now()
    user.session_revoked_at = revoked_at
    user.session_nonce = uuid.uuid4()
    user.save(update_fields=["session_revoked_at", "session_nonce"])

    outstanding_tokens = OutstandingToken.objects.filter(
        user=user,
        expires_at__gt=timezone.now(),
    )
    for outstanding in outstanding_tokens:
        BlacklistedToken.objects.get_or_create(token=outstanding)

    UserDeviceToken.objects.filter(user=user, is_active=True).update(is_active=False)
    return revoked_at


def log_invalid_token_event(request, raw_token: str, exc: Exception) -> AuthSessionEvent | None:
    claims = _decode_unverified_claims(raw_token)
    user = None
    user_id = claims.get("user_id")
    if user_id is not None:
        user = User.objects.filter(pk=user_id).first()

    username = (claims.get("username") or (user.username if user else "") or "").strip()
    role = (claims.get("role") or (user.role if user else "") or "").strip().upper()
    token_expires_at = _parse_exp_timestamp(claims.get("exp"))
    token_jti = str(claims.get("jti") or "").strip()
    now = timezone.now()
    expired = token_expires_at is not None and token_expires_at <= now
    event_type = (
        AuthSessionEvent.EventType.TOKEN_EXPIRED
        if expired
        else AuthSessionEvent.EventType.TOKEN_INVALID
    )
    if _dedupe_recent(
        event_type=event_type,
        username=username,
        path=getattr(request, "path", "") or "",
        token_jti=token_jti,
    ):
        return None

    reason = str(exc)
    if expired and token_expires_at is not None:
        reason = f"JWT expired at {timezone.localtime(token_expires_at).strftime('%d %b %Y, %I:%M %p')}."

    return AuthSessionEvent.objects.create(
        user=user,
        username=username,
        role=role,
        app_variant=_guess_app_variant(role),
        event_type=event_type,
        reason=reason[:255],
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        status_code=401,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
        token_jti=token_jti,
        token_expires_at=token_expires_at,
    )
