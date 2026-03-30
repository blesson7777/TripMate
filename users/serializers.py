from django.contrib.auth import get_user_model
import base64
import re
import uuid

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer

from drivers.models import Driver
from users.account_deletion import perform_account_deletion
from users.auth_events import token_issued_at
from users.models import (
    AccountDeletionRequest,
    AdminBroadcastNotification,
    DriverNotification,
    EmailOTP,
    Transporter,
    TransporterNotification,
)
from users.firebase_verification import normalize_phone_number
from users.services import (
    send_account_deletion_otp,
    send_driver_login_otp,
    send_driver_signup_otp,
    send_password_reset_otp,
    send_profile_email_change_otp,
    send_transporter_login_otp,
    send_transporter_signup_otp,
)

User = get_user_model()


def _decode_base64_image(raw_value: str) -> tuple[bytes, str]:
    value = (raw_value or "").strip()
    if not value:
        raise ValueError("Empty image payload.")

    if value.lower().startswith("data:") and "," in value:
        _, value = value.split(",", 1)
        value = value.strip()

    decoded = base64.b64decode(value)
    if not decoded:
        raise ValueError("Decoded image was empty.")

    extension = "png"
    if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif decoded.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif decoded.startswith(b"GIF87a") or decoded.startswith(b"GIF89a"):
        extension = "gif"
    elif decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP":
        extension = "webp"

    return decoded, extension


_INDIAN_LICENSE_NUMBER_PATTERN = re.compile(r"^[A-Z]{2}\d{2}\d{4}\d{7}$")


def _normalize_indian_license_number(raw_value: str) -> str:
    cleaned = re.sub(r"[\s/-]+", "", str(raw_value or "").upper())
    if not cleaned:
        raise serializers.ValidationError("License number is required.")
    if not _INDIAN_LICENSE_NUMBER_PATTERN.match(cleaned):
        raise serializers.ValidationError(
            "Enter a valid Indian license number like KL0720110012345."
        )
    return cleaned


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "phone", "role")


def _resolve_login_user(credential: str):
    raw = (credential or "").strip()
    if not raw:
        return None

    user = None
    if "@" in raw:
        user = User.objects.filter(email__iexact=raw).first()
    else:
        normalized_phone = "".join(
            character for character in raw if character.isdigit() or character == "+"
        )
        user = User.objects.filter(phone=raw).first()
        if user is None and normalized_phone:
            user = User.objects.filter(phone=normalized_phone).first()

    if user is None:
        user = User.objects.filter(username__iexact=raw).first()

    return user


def _resolve_login_username(credential: str) -> str:
    user = _resolve_login_user(credential)
    if user is None:
        return (credential or "").strip()
    return user.get_username()


def _raise_for_ineligible_login_user(user: User | None) -> None:
    if user is None:
        return
    if not user.is_active:
        raise serializers.ValidationError(
            {
                "detail": (
                    "Your account has been disabled by admin. "
                    "Please contact transporter support."
                )
            }
        )
    if not user.has_usable_password():
        raise serializers.ValidationError(
            {
                "detail": (
                    "Password reset required by admin. "
                    "Use Forgot Password with OTP to continue."
                )
            }
        )


def _authenticate_login_user(credential: str, password: str):
    resolved_username = _resolve_login_username(credential)
    candidate_user = User.objects.filter(username__iexact=resolved_username).first()
    _raise_for_ineligible_login_user(candidate_user)

    user = authenticate(username=resolved_username, password=password)
    if user is None:
        raise serializers.ValidationError(
            {"detail": "Invalid username/email/phone or password."}
        )
    _raise_for_ineligible_login_user(user)
    return user, resolved_username


class TransporterSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Transporter
        fields = (
            "id",
            "user",
            "company_name",
            "address",
            "gstin",
            "pan",
            "website",
            "logo",
            "diesel_tracking_enabled",
            "diesel_readings_enabled",
            "location_tracking_enabled",
        )


class TransporterPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transporter
        fields = ("id", "company_name", "address")


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["username"] = user.username
        token["session_nonce"] = str(user.session_nonce)
        return token

    def validate(self, attrs):
        username_field = self.username_field
        login_credential = attrs.get(username_field, "")
        resolved_username = _resolve_login_username(login_credential)
        attrs[username_field] = resolved_username

        candidate_user = User.objects.filter(username__iexact=resolved_username).first()
        _raise_for_ineligible_login_user(candidate_user)

        try:
            data = super().validate(attrs)
        except serializers.ValidationError as exception:
            detail = exception.detail
            if isinstance(detail, dict) and "detail" in detail:
                raw = str(detail["detail"]).lower()
                if "no active account found" in raw:
                    raise serializers.ValidationError(
                        {"detail": "Invalid username/email/phone or password."}
                    ) from exception
            raise
        data["user"] = UserSerializer(self.user).data

        if hasattr(self.user, "transporter_profile"):
            data["transporter_id"] = self.user.transporter_profile.id
            data["diesel_tracking_enabled"] = (
                self.user.transporter_profile.diesel_tracking_enabled
            )
            data["diesel_readings_enabled"] = (
                self.user.transporter_profile.diesel_readings_enabled
            )
            data["location_tracking_enabled"] = (
                self.user.transporter_profile.location_tracking_enabled
            )
        if hasattr(self.user, "driver_profile"):
            data["driver_id"] = self.user.driver_profile.id
            driver_transporter = self.user.driver_profile.transporter
            data["diesel_tracking_enabled"] = bool(
                driver_transporter and driver_transporter.diesel_tracking_enabled
            )
            data["diesel_readings_enabled"] = bool(
                driver_transporter and driver_transporter.diesel_readings_enabled
            )
            data["location_tracking_enabled"] = bool(
                driver_transporter and driver_transporter.location_tracking_enabled
            )

        return data


class DriverLoginOtpRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user, _resolved_username = _authenticate_login_user(
            attrs.get("username", ""),
            attrs.get("password", ""),
        )
        if user.role != User.Role.DRIVER or not hasattr(user, "driver_profile"):
            raise serializers.ValidationError(
                {"detail": "This login is only for driver accounts."}
            )
        if not (user.email or "").strip():
            raise serializers.ValidationError(
                {"detail": "Driver email is missing. Please contact admin."}
            )
        attrs["user"] = user
        attrs["email"] = user.email.strip().lower()
        return attrs

    def save(self):
        user = self.validated_data["user"]
        email = self.validated_data["email"]
        otp = send_driver_login_otp(email)
        return {
            "user": user,
            "email": email,
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class TransporterLoginOtpRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user, _resolved_username = _authenticate_login_user(
            attrs.get("username", ""),
            attrs.get("password", ""),
        )
        if user.role != User.Role.TRANSPORTER or not hasattr(user, "transporter_profile"):
            raise serializers.ValidationError(
                {"detail": "This login is only for transporter accounts."}
            )
        if not (user.email or "").strip():
            raise serializers.ValidationError(
                {"detail": "Transporter email is missing. Please contact admin."}
            )
        attrs["user"] = user
        attrs["email"] = user.email.strip().lower()
        return attrs

    def save(self):
        user = self.validated_data["user"]
        email = self.validated_data["email"]
        otp = send_transporter_login_otp(email)
        return {
            "user": user,
            "email": email,
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class DriverLoginOtpVerifySerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)

    def validate(self, attrs):
        user, _resolved_username = _authenticate_login_user(
            attrs.get("username", ""),
            attrs.get("password", ""),
        )
        if user.role != User.Role.DRIVER or not hasattr(user, "driver_profile"):
            raise serializers.ValidationError(
                {"detail": "This login is only for driver accounts."}
            )

        email = (user.email or "").strip().lower()
        if not email:
            raise serializers.ValidationError(
                {"detail": "Driver email is missing. Please contact admin."}
            )

        otp = (
            EmailOTP.objects.filter(
                email__iexact=email,
                purpose=EmailOTP.Purpose.DRIVER_LOGIN,
                code=str(attrs.get("otp", "")).strip(),
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})

        attrs["user"] = user
        attrs["email"] = email
        attrs["otp_obj"] = otp
        return attrs

    def save(self):
        otp_obj = self.validated_data["otp_obj"]
        email = self.validated_data["email"]

        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        EmailOTP.objects.filter(
            email__iexact=email,
            purpose=EmailOTP.Purpose.DRIVER_LOGIN,
            is_used=False,
        ).exclude(pk=otp_obj.pk).update(is_used=True)

        return self.validated_data["user"]


class TransporterLoginOtpVerifySerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)

    def validate(self, attrs):
        user, _resolved_username = _authenticate_login_user(
            attrs.get("username", ""),
            attrs.get("password", ""),
        )
        if user.role != User.Role.TRANSPORTER or not hasattr(user, "transporter_profile"):
            raise serializers.ValidationError(
                {"detail": "This login is only for transporter accounts."}
            )

        email = (user.email or "").strip().lower()
        if not email:
            raise serializers.ValidationError(
                {"detail": "Transporter email is missing. Please contact admin."}
            )

        otp = (
            EmailOTP.objects.filter(
                email__iexact=email,
                purpose=EmailOTP.Purpose.TRANSPORTER_LOGIN,
                code=str(attrs.get("otp", "")).strip(),
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})

        attrs["user"] = user
        attrs["email"] = email
        attrs["otp_obj"] = otp
        return attrs

    def save(self):
        otp_obj = self.validated_data["otp_obj"]
        email = self.validated_data["email"]

        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        EmailOTP.objects.filter(
            email__iexact=email,
            purpose=EmailOTP.Purpose.TRANSPORTER_LOGIN,
            is_used=False,
        ).exclude(pk=otp_obj.pk).update(is_used=True)

        return self.validated_data["user"]


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get("user_id")
        user = User.objects.filter(pk=user_id).first()
        if user is None:
            raise InvalidToken("User not found for refresh token.")
        if not user.is_active:
            raise InvalidToken("User account is disabled.")
        if not user.has_usable_password():
            raise InvalidToken("Password reset required.")
        token_session_nonce = str(refresh.payload.get("session_nonce") or "").strip()
        if token_session_nonce and token_session_nonce != str(user.session_nonce):
            raise InvalidToken("Session revoked by new login.")

        issued_at = token_issued_at(refresh)
        if (
            not token_session_nonce
            and user.session_revoked_at
            and issued_at
            and issued_at <= user.session_revoked_at
        ):
            raise InvalidToken("Session revoked by admin or logout.")

        return super().validate(attrs)


class DriverProfileSerializer(serializers.ModelSerializer):
    transporter = serializers.SerializerMethodField()
    assigned_vehicle = serializers.SerializerMethodField()
    default_service = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = (
            "id",
            "license_number",
            "is_active",
            "transporter",
            "assigned_vehicle",
            "default_service",
        )

    def get_transporter(self, obj):
        transporter = obj.transporter
        if transporter is None:
            return None
        return {
            "id": transporter.id,
            "company_name": transporter.company_name,
            "diesel_tracking_enabled": transporter.diesel_tracking_enabled,
            "diesel_readings_enabled": transporter.diesel_readings_enabled,
            "location_tracking_enabled": transporter.location_tracking_enabled,
        }

    def get_assigned_vehicle(self, obj):
        vehicle = obj.assigned_vehicle
        if vehicle is None:
            return None
        return {
            "id": vehicle.id,
            "vehicle_number": vehicle.vehicle_number,
        }

    def get_default_service(self, obj):
        service = obj.default_service
        if service is None:
            return None
        return {
            "id": service.id,
            "name": service.name,
        }


class _BaseProfileUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    email_otp = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        min_length=6,
        max_length=6,
    )

    def validate_username(self, value):
        user = self.context["request"].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        user = self.context["request"].user
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email is already registered.")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context["request"].user
        next_email = attrs.get("email")
        if next_email is None:
            return attrs

        current_email = (user.email or "").strip().lower()
        if next_email == current_email:
            attrs.pop("email_otp", None)
            return attrs

        otp_code = str(attrs.get("email_otp", "") or "").strip()
        if not otp_code:
            raise serializers.ValidationError(
                {"email_otp": "OTP is required to update your email address."}
            )

        otp = (
            EmailOTP.objects.filter(
                email__iexact=next_email,
                purpose=EmailOTP.Purpose.PROFILE_EMAIL_CHANGE,
                code=otp_code,
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            raise serializers.ValidationError(
                {"email_otp": "Invalid or expired OTP."}
            )
        attrs["email_otp_obj"] = otp
        return attrs

    def _consume_email_change_otp(self, otp_obj, email):
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        EmailOTP.objects.filter(
            email__iexact=email,
            purpose=EmailOTP.Purpose.PROFILE_EMAIL_CHANGE,
            is_used=False,
        ).exclude(pk=otp_obj.pk).update(is_used=True)

    def _update_user(self, user, validated_data):
        update_fields = []

        username = validated_data.get("username")
        if username is not None:
            user.username = username
            update_fields.append("username")

        email = validated_data.get("email")
        if email is not None:
            user.email = email
            update_fields.append("email")

        if update_fields:
            user.save(update_fields=update_fields)


class DriverProfileUpdateSerializer(_BaseProfileUpdateSerializer):
    license_number = serializers.CharField(max_length=50, required=False)

    def validate_license_number(self, value):
        normalized = _normalize_indian_license_number(value)
        instance = self.instance
        if (
            Driver.objects.filter(license_number__iexact=normalized)
            .exclude(pk=instance.pk)
            .exists()
        ):
            raise serializers.ValidationError("This license number is already in use.")
        return normalized

    def save(self):
        user = self.context["request"].user
        driver = self.instance
        validated_data = self.validated_data
        email_otp_obj = validated_data.pop("email_otp_obj", None)
        validated_data.pop("email_otp", None)

        with transaction.atomic():
            self._update_user(user, validated_data)
            if "license_number" in validated_data:
                driver.license_number = validated_data["license_number"]
                driver.save(update_fields=["license_number"])
            if email_otp_obj is not None:
                self._consume_email_change_otp(email_otp_obj, user.email)

        user.refresh_from_db()
        driver.refresh_from_db()
        return {"user": user, "driver": driver}


class TransporterProfileUpdateSerializer(_BaseProfileUpdateSerializer):
    company_name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    gstin = serializers.CharField(required=False, allow_blank=True, max_length=32)
    pan = serializers.CharField(required=False, allow_blank=True, max_length=32)
    website = serializers.CharField(required=False, allow_blank=True, max_length=120)
    logo_base64 = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def save(self):
        user = self.context["request"].user
        transporter = self.instance
        validated_data = self.validated_data
        transporter_update_fields = []
        email_otp_obj = validated_data.pop("email_otp_obj", None)
        validated_data.pop("email_otp", None)

        with transaction.atomic():
            self._update_user(user, validated_data)
            if "company_name" in validated_data:
                transporter.company_name = validated_data["company_name"]
                transporter_update_fields.append("company_name")
            if "address" in validated_data:
                transporter.address = validated_data["address"]
                transporter_update_fields.append("address")
            if "gstin" in validated_data:
                transporter.gstin = validated_data["gstin"].strip()
                transporter_update_fields.append("gstin")
            if "pan" in validated_data:
                transporter.pan = validated_data["pan"].strip()
                transporter_update_fields.append("pan")
            if "website" in validated_data:
                transporter.website = validated_data["website"].strip()
                transporter_update_fields.append("website")
            if "logo_base64" in validated_data:
                raw_logo = (validated_data.get("logo_base64") or "").strip()
                if raw_logo:
                    decoded, extension = _decode_base64_image(raw_logo)
                    filename = f"transporter_logo_{uuid.uuid4().hex}.{extension}"
                    transporter.logo.save(filename, ContentFile(decoded), save=False)
                    transporter_update_fields.append("logo")
            if transporter_update_fields:
                transporter.save(update_fields=transporter_update_fields)
            if email_otp_obj is not None:
                self._consume_email_change_otp(email_otp_obj, user.email)

        user.refresh_from_db()
        transporter.refresh_from_db()
        return {"user": user, "transporter": transporter}


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user

        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "Current password is incorrect."}
            )

        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Password confirmation does not match."}
            )

        validate_password(attrs["new_password"], user=user)
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class ProfileAccountDeletionSerializer(serializers.Serializer):
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        user = self.context["request"].user
        email = (user.email or "").strip().lower()
        if not email:
            raise serializers.ValidationError(
                {"detail": "A verified email address is required to delete this account."}
            )

        otp = (
            EmailOTP.objects.filter(
                email__iexact=email,
                purpose=EmailOTP.Purpose.ACCOUNT_DELETION,
                code=str(attrs["otp"]).strip(),
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})
        attrs["email"] = email
        attrs["otp_obj"] = otp
        return attrs

    def save(self, *, revoked_at=None):
        user = self.context["request"].user
        note = str(self.validated_data.get("note", "") or "").strip()
        otp_obj = self.validated_data["otp_obj"]
        email = self.validated_data["email"]
        deletion_request = perform_account_deletion(
            user,
            source=AccountDeletionRequest.Source.APP,
            note=note,
            processed_at=revoked_at,
        )
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        EmailOTP.objects.filter(
            email__iexact=email,
            purpose=EmailOTP.Purpose.ACCOUNT_DELETION,
            is_used=False,
        ).exclude(pk=otp_obj.pk).update(is_used=True)
        return {
            "user": user,
            "account_deletion_request": deletion_request,
        }


class _OtpValidationMixin:
    otp_purpose = None

    def _validate_otp(self, attrs):
        otp = (
            EmailOTP.objects.filter(
                email__iexact=attrs["email"].strip(),
                purpose=self.otp_purpose,
                code=attrs["otp"].strip(),
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})
        attrs["otp_obj"] = otp

    def _consume_otp(self, otp_obj, email):
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])
        EmailOTP.objects.filter(
            email__iexact=email,
            purpose=self.otp_purpose,
            is_used=False,
        ).exclude(pk=otp_obj.pk).update(is_used=True)


class TransporterRegisterSerializer(_OtpValidationMixin, serializers.Serializer):
    otp_purpose = EmailOTP.Purpose.TRANSPORTER_SIGNUP

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField()
    otp = serializers.CharField(
        write_only=True,
        min_length=6,
        max_length=6,
    )
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    company_name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True)
    gstin = serializers.CharField(required=False, allow_blank=True, max_length=32)
    pan = serializers.CharField(required=False, allow_blank=True, max_length=32)
    website = serializers.CharField(required=False, allow_blank=True, max_length=120)
    logo_base64 = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_phone(self, value):
        normalized = normalize_phone_number(value)
        if not normalized:
            return ""
        if User.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("This mobile number is already registered.")
        return normalized

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Password confirmation does not match."}
            )

        self._validate_otp(attrs)
        candidate = User(
            username=attrs["username"],
            email=attrs["email"].strip(),
            phone=attrs.get("phone", ""),
            role=User.Role.TRANSPORTER,
        )
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        validated_data.pop("otp", None)
        otp_obj = validated_data.pop("otp_obj", None)
        company_name = validated_data.pop("company_name")
        address = validated_data.pop("address", "")
        gstin = str(validated_data.pop("gstin", "") or "").strip()
        pan = str(validated_data.pop("pan", "") or "").strip()
        website = str(validated_data.pop("website", "") or "").strip()
        logo_base64 = validated_data.pop("logo_base64", "")
        email = validated_data["email"].strip().lower()

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                password=password,
                email=email,
                phone=validated_data.get("phone", ""),
                role=User.Role.TRANSPORTER,
            )
            transporter = Transporter.objects.create(
                user=user,
                company_name=company_name,
                address=address,
                gstin=gstin,
                pan=pan,
                website=website,
            )
            if logo_base64 and str(logo_base64).strip():
                decoded, extension = _decode_base64_image(str(logo_base64))
                filename = f"transporter_logo_{uuid.uuid4().hex}.{extension}"
                transporter.logo.save(filename, ContentFile(decoded), save=True)
            if otp_obj is not None:
                self._consume_otp(otp_obj, email)

        return {"user": user, "transporter": transporter}


class DriverRegisterSerializer(_OtpValidationMixin, serializers.Serializer):
    otp_purpose = EmailOTP.Purpose.DRIVER_SIGNUP

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField()
    otp = serializers.CharField(
        write_only=True,
        min_length=6,
        max_length=6,
    )
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    license_number = serializers.CharField(max_length=50)
    transporter_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_license_number(self, value):
        normalized = _normalize_indian_license_number(value)
        if Driver.objects.filter(license_number__iexact=normalized).exists():
            raise serializers.ValidationError("This license number is already in use.")
        return normalized

    def validate_phone(self, value):
        normalized = normalize_phone_number(value)
        if not normalized:
            return ""
        if User.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("This mobile number is already registered.")
        return normalized

    def validate_transporter_id(self, value):
        if value is None:
            return None
        try:
            transporter = Transporter.objects.get(pk=value)
        except Transporter.DoesNotExist as exception:
            raise serializers.ValidationError("Selected transporter does not exist.") from exception
        return transporter

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Password confirmation does not match."}
            )

        self._validate_otp(attrs)
        candidate = User(
            username=attrs["username"],
            email=attrs["email"].strip(),
            phone=attrs.get("phone", ""),
            role=User.Role.DRIVER,
        )
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("confirm_password")
        validated_data.pop("otp", None)
        otp_obj = validated_data.pop("otp_obj", None)
        transporter = validated_data.pop("transporter_id", None)
        email = validated_data["email"].strip().lower()

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                password=password,
                email=email,
                phone=validated_data.get("phone", ""),
                role=User.Role.DRIVER,
            )
            driver = Driver.objects.create(
                user=user,
                transporter=transporter,
                license_number=validated_data["license_number"],
            )
            if otp_obj is not None:
                self._consume_otp(otp_obj, email)

        return {"user": user, "driver": driver}


class _BaseOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    send_otp_function = None

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("This email is already registered.")
        return normalized

    def create(self, validated_data):
        try:
            otp_sender = self.__class__.send_otp_function
            if otp_sender is None:
                raise RuntimeError("OTP sender is not configured.")
            otp = otp_sender(validated_data["email"])
        except RuntimeError as exception:
            raise serializers.ValidationError({"detail": str(exception)}) from exception
        except Exception as exception:
            if settings.DEBUG:
                raise serializers.ValidationError({"detail": str(exception)}) from exception
            raise serializers.ValidationError(
                {"detail": "Unable to send OTP email. Please try again."}
            )
        return {
            "email": validated_data["email"],
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class TransporterOtpRequestSerializer(_BaseOtpRequestSerializer):
    send_otp_function = send_transporter_signup_otp


class DriverOtpRequestSerializer(_BaseOtpRequestSerializer):
    send_otp_function = send_driver_signup_otp


class PasswordResetOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        normalized = value.strip().lower()
        if not User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("No account found with this email.")
        return normalized

    def create(self, validated_data):
        try:
            otp = send_password_reset_otp(validated_data["email"])
        except RuntimeError as exception:
            raise serializers.ValidationError({"detail": str(exception)}) from exception
        except Exception as exception:
            if settings.DEBUG:
                raise serializers.ValidationError({"detail": str(exception)}) from exception
            raise serializers.ValidationError(
                {"detail": "Unable to send OTP email. Please try again."}
            )
        return {
            "email": validated_data["email"],
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class ProfileEmailChangeOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        user = self.context["request"].user
        normalized = value.strip().lower()
        current_email = (user.email or "").strip().lower()
        if normalized == current_email:
            raise serializers.ValidationError(
                "Enter a new email address to receive the OTP."
            )
        if User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email is already registered.")
        return normalized

    def create(self, validated_data):
        try:
            otp = send_profile_email_change_otp(validated_data["email"])
        except RuntimeError as exception:
            raise serializers.ValidationError({"detail": str(exception)}) from exception
        except Exception as exception:
            if settings.DEBUG:
                raise serializers.ValidationError({"detail": str(exception)}) from exception
            raise serializers.ValidationError(
                {"detail": "Unable to send OTP email. Please try again."}
            )
        return {
            "email": validated_data["email"],
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class ProfileAccountDeletionOtpRequestSerializer(serializers.Serializer):
    def create(self, validated_data):
        user = self.context["request"].user
        email = (user.email or "").strip().lower()
        if not email:
            raise serializers.ValidationError(
                {"detail": "A verified email address is required to delete this account."}
            )
        try:
            otp = send_account_deletion_otp(email)
        except RuntimeError as exception:
            raise serializers.ValidationError({"detail": str(exception)}) from exception
        except Exception as exception:
            if settings.DEBUG:
                raise serializers.ValidationError({"detail": str(exception)}) from exception
            raise serializers.ValidationError(
                {"detail": "Unable to send OTP email. Please try again."}
            )
        return {
            "email": email,
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class ResetPasswordWithOtpSerializer(_OtpValidationMixin, serializers.Serializer):
    otp_purpose = EmailOTP.Purpose.PASSWORD_RESET

    email = serializers.EmailField()
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        normalized = value.strip().lower()
        user = User.objects.filter(email__iexact=normalized).first()
        if user is None:
            raise serializers.ValidationError("No account found with this email.")
        self.context["target_user"] = user
        return normalized

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Password confirmation does not match."}
            )

        self._validate_otp(attrs)
        validate_password(attrs["new_password"], user=self.context["target_user"])
        return attrs

    def save(self):
        email = self.validated_data["email"]
        otp_obj = self.validated_data["otp_obj"]
        user = self.context["target_user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        self._consume_otp(otp_obj, email)
        return user


class AdminDieselModuleToggleSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(min_value=1)
    enabled = serializers.IntegerField(min_value=0, max_value=1)

    def validate_partner_id(self, value):
        transporter = Transporter.objects.filter(pk=value).first()
        if transporter is None:
            raise serializers.ValidationError("Transporter does not exist.")
        self.context["target_transporter"] = transporter
        return value


class TransporterNotificationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    target = serializers.SerializerMethodField()

    def get_target(self, obj):
        event_key = (obj.event_key or "").strip().lower()
        if event_key.startswith("app-release-"):
            return "APP_UPDATE"
        return None

    class Meta:
        model = TransporterNotification
        fields = (
            "id",
            "notification_type",
            "title",
            "message",
            "target",
            "driver",
            "driver_name",
            "trip",
            "is_read",
            "created_at",
        )


class AdminBroadcastNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminBroadcastNotification
        fields = (
            "id",
            "title",
            "message",
            "audience",
            "is_active",
            "created_at",
            "updated_at",
        )


class DriverNotificationSerializer(serializers.ModelSerializer):
    driver = serializers.IntegerField(source="driver_id", read_only=True)
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    trip = serializers.IntegerField(source="trip_id", read_only=True)
    target = serializers.SerializerMethodField()

    def get_target(self, obj):
        event_key = (obj.event_key or "").strip().lower()
        if event_key.startswith("app-release-"):
            return "APP_UPDATE"
        return None

    class Meta:
        model = DriverNotification
        fields = (
            "id",
            "notification_type",
            "title",
            "message",
            "target",
            "driver",
            "driver_name",
            "trip",
            "is_read",
            "created_at",
        )
