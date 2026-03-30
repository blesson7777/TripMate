from django.conf import settings

try:
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import id_token as google_id_token
except Exception:  # pragma: no cover
    GoogleAuthError = Exception
    GoogleAuthRequest = None
    google_id_token = None


def normalize_phone_number(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""

    if value.startswith("+"):
        digits = "".join(character for character in value[1:] if character.isdigit())
        return f"+{digits}" if digits else ""

    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}"


def verify_firebase_phone_token(
    raw_id_token: str,
    *,
    expected_phone: str | None = None,
) -> dict:
    token = str(raw_id_token or "").strip()
    if not token:
        raise ValueError("Firebase mobile verification token is required.")

    if google_id_token is None or GoogleAuthRequest is None:
        raise RuntimeError("Firebase mobile verification is not configured on the server.")

    project_id = str(getattr(settings, "FCM_PROJECT_ID", "") or "").strip()
    if not project_id:
        raise RuntimeError("Firebase project ID is not configured on the server.")

    try:
        decoded = google_id_token.verify_firebase_token(
            token,
            GoogleAuthRequest(),
            audience=project_id,
        )
    except GoogleAuthError as exception:
        raise ValueError("Unable to verify the mobile OTP token.") from exception
    except Exception as exception:
        raise ValueError("Unable to verify the mobile OTP token.") from exception

    if not decoded:
        raise ValueError("Unable to verify the mobile OTP token.")

    phone_number = normalize_phone_number(decoded.get("phone_number", ""))
    if not phone_number:
        raise ValueError("Verified mobile number was not found in the OTP token.")

    expected = normalize_phone_number(expected_phone or "")
    if expected and expected != phone_number:
        raise ValueError("Verified mobile number does not match the entered phone number.")

    return {
        "uid": str(decoded.get("uid") or decoded.get("sub") or "").strip(),
        "phone_number": phone_number,
    }
