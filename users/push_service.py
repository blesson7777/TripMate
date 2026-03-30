import json
import logging
import os
from functools import lru_cache
from urllib import error as url_error
from urllib import request as url_request

from django.conf import settings
from django.utils import timezone

from users.models import User, UserDeviceToken

logger = logging.getLogger(__name__)

FCM_LEGACY_SEND_URL = "https://fcm.googleapis.com/fcm/send"
FCM_V1_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
INVALID_TOKEN_ERRORS_LEGACY = {"NotRegistered", "InvalidRegistration", "MismatchSenderId"}
INVALID_TOKEN_ERRORS_V1 = {"UNREGISTERED", "INVALID_ARGUMENT"}

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except Exception:  # pragma: no cover
    GoogleAuthRequest = None
    service_account = None


def _fcm_server_key() -> str:
    value = getattr(settings, "FCM_SERVER_KEY", "")
    return value.strip()


def _fcm_project_id() -> str:
    value = getattr(settings, "FCM_PROJECT_ID", "")
    return value.strip()


def _fcm_service_account_file() -> str:
    value = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", "")
    return value.strip()


def _fcm_service_account_json() -> str:
    value = getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "")
    return value.strip()


def _normalize_data(data: dict | None) -> dict:
    if not data:
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _parse_service_account_info(raw_value: str) -> dict | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


@lru_cache(maxsize=1)
def _build_v1_credentials():
    if service_account is None or GoogleAuthRequest is None:
        return None, None

    project_id = _fcm_project_id()
    service_account_file = _fcm_service_account_file()
    raw_json = _fcm_service_account_json()
    account_info = _parse_service_account_info(raw_json)

    credentials = None
    if service_account_file and os.path.exists(service_account_file):
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=[FCM_V1_SCOPE],
        )
        if not project_id:
            project_id = credentials.project_id or ""
    elif account_info:
        credentials = service_account.Credentials.from_service_account_info(
            account_info,
            scopes=[FCM_V1_SCOPE],
        )
        if not project_id:
            project_id = account_info.get("project_id") or ""

    if credentials is None or not project_id:
        return None, None
    return credentials, project_id


def is_push_enabled() -> bool:
    credentials, project_id = _build_v1_credentials()
    if credentials is not None and project_id:
        return True
    return bool(_fcm_server_key())


def _send_to_token_v1(*, token: str, title: str, body: str, data: dict | None = None) -> dict | None:
    credentials, project_id = _build_v1_credentials()
    if credentials is None or not project_id:
        return None

    if not credentials.valid or credentials.expired or not credentials.token:
        credentials.refresh(GoogleAuthRequest())

    normalized_data = _normalize_data(data)
    normalized_data.setdefault("title", title)
    normalized_data.setdefault("message", body)
    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": normalized_data,
            "android": {
                "priority": "HIGH",
            },
        }
    }
    raw_body = json.dumps(payload).encode("utf-8")
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    request = url_request.Request(
        url,
        data=raw_body,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {credentials.token}",
        },
        method="POST",
    )

    try:
        with url_request.urlopen(request, timeout=8) as response:
            response_body = response.read().decode("utf-8")
            if not response_body:
                return None
            return json.loads(response_body)
    except url_error.HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8")
        except Exception:
            error_body = ""
        try:
            parsed = json.loads(error_body) if error_body else {}
        except json.JSONDecodeError:
            parsed = {"raw": error_body}
        logger.warning("FCM v1 push HTTP error: %s body=%s", exc, parsed)
        return {"error": parsed}
    except (url_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("FCM v1 push request failed: %s", exc)
        return None


def _send_to_token_legacy(
    *,
    token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict | None:
    server_key = _fcm_server_key()
    if not server_key:
        return None

    normalized_data = _normalize_data(data)
    normalized_data.setdefault("title", title)
    normalized_data.setdefault("message", body)
    payload = {
        "to": token,
        "priority": "high",
        "notification": {"title": title, "body": body},
        "data": normalized_data,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(
        FCM_LEGACY_SEND_URL,
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"key={server_key}",
        },
        method="POST",
    )

    try:
        with url_request.urlopen(request, timeout=8) as response:
            response_body = response.read().decode("utf-8")
            if not response_body:
                return None
            return json.loads(response_body)
    except url_error.HTTPError as exc:
        logger.warning("FCM legacy push HTTP error: %s", exc)
        return None
    except (url_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("FCM legacy push request failed: %s", exc)
        return None


def _send_to_token(*, token: str, title: str, body: str, data: dict | None = None) -> dict | None:
    response = _send_to_token_v1(
        token=token,
        title=title,
        body=body,
        data=data,
    )
    if response is not None:
        return response
    return _send_to_token_legacy(
        token=token,
        title=title,
        body=body,
        data=data,
    )


def _mark_inactive_if_invalid_token(device: UserDeviceToken, response: dict) -> bool:
    results = response.get("results") or []
    if results:
        first = results[0] or {}
        error_code = first.get("error")
        if error_code in INVALID_TOKEN_ERRORS_LEGACY:
            UserDeviceToken.objects.filter(pk=device.pk).update(
                is_active=False,
                updated_at=timezone.now(),
            )
            return True

    error_blob = response.get("error")
    if isinstance(error_blob, dict):
        details = error_blob.get("error", {}).get("details", [])
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("errorCode") or "")
                if code in INVALID_TOKEN_ERRORS_V1:
                    UserDeviceToken.objects.filter(pk=device.pk).update(
                        is_active=False,
                        updated_at=timezone.now(),
                    )
                    return True
    return False


def send_push_to_user(
    *,
    user: User,
    title: str,
    body: str,
    data: dict | None = None,
    app_variant: str | None = None,
) -> int:
    if not is_push_enabled():
        return 0

    queryset = UserDeviceToken.objects.filter(user=user, is_active=True)
    if app_variant:
        queryset = queryset.filter(app_variant=app_variant)

    sent = 0
    for device in queryset:
        response = _send_to_token(
            token=device.token,
            title=title,
            body=body,
            data=data,
        )
        if response is None:
            continue

        if _mark_inactive_if_invalid_token(device, response):
            continue

        v1_name = response.get("name")
        if isinstance(v1_name, str) and v1_name:
            sent += 1
            continue

        results = response.get("results") or []
        if results:
            first = results[0] or {}
            if first.get("message_id"):
                sent += 1
                continue

        success = int(response.get("success") or 0)
        if success > 0:
            sent += 1

    return sent
