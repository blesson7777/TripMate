from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from users.auth_events import log_invalid_token_event, token_issued_at


class TripMateJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None
        try:
            raw_value = raw_token.decode("utf-8")
        except Exception:
            raw_value = ""

        try:
            validated_token = self.get_validated_token(raw_token)
        except Exception as exc:
            log_invalid_token_event(request, raw_value, exc)
            raise

        user = self.get_user(validated_token)
        token_session_nonce = str(validated_token.get("session_nonce") or "").strip()
        if token_session_nonce and token_session_nonce != str(user.session_nonce):
            log_invalid_token_event(
                request,
                raw_value,
                InvalidToken("Session revoked by new login."),
            )
            raise InvalidToken("Session revoked by new login.")
        issued_at = token_issued_at(validated_token)
        if (
            not token_session_nonce
            and user.session_revoked_at
            and issued_at
            and issued_at <= user.session_revoked_at
        ):
            log_invalid_token_event(
                request,
                raw_value,
                InvalidToken("Session revoked by admin or logout."),
            )
            raise InvalidToken("Session revoked by admin or logout.")

        return user, validated_token
