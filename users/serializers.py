from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from drivers.models import Driver
from users.models import EmailOTP, Transporter
from users.services import send_driver_signup_otp, send_transporter_signup_otp

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "phone", "role")


class TransporterSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Transporter
        fields = ("id", "user", "company_name", "address")


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
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data

        if hasattr(self.user, "transporter_profile"):
            data["transporter_id"] = self.user.transporter_profile.id
        if hasattr(self.user, "driver_profile"):
            data["driver_id"] = self.user.driver_profile.id

        return data


class DriverProfileSerializer(serializers.ModelSerializer):
    transporter = serializers.SerializerMethodField()
    assigned_vehicle = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = ("id", "license_number", "is_active", "transporter", "assigned_vehicle")

    def get_transporter(self, obj):
        transporter = obj.transporter
        if transporter is None:
            return None
        return {
            "id": transporter.id,
            "company_name": transporter.company_name,
        }

    def get_assigned_vehicle(self, obj):
        vehicle = obj.assigned_vehicle
        if vehicle is None:
            return None
        return {
            "id": vehicle.id,
            "vehicle_number": vehicle.vehicle_number,
        }


class _BaseProfileUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)

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

        phone = validated_data.get("phone")
        if phone is not None:
            user.phone = phone
            update_fields.append("phone")

        if update_fields:
            user.save(update_fields=update_fields)


class DriverProfileUpdateSerializer(_BaseProfileUpdateSerializer):
    license_number = serializers.CharField(max_length=50, required=False)

    def validate_license_number(self, value):
        instance = self.instance
        if (
            Driver.objects.filter(license_number__iexact=value)
            .exclude(pk=instance.pk)
            .exists()
        ):
            raise serializers.ValidationError("This license number is already in use.")
        return value

    def save(self):
        user = self.context["request"].user
        driver = self.instance
        validated_data = self.validated_data

        with transaction.atomic():
            self._update_user(user, validated_data)
            if "license_number" in validated_data:
                driver.license_number = validated_data["license_number"]
                driver.save(update_fields=["license_number"])

        user.refresh_from_db()
        driver.refresh_from_db()
        return {"user": user, "driver": driver}


class TransporterProfileUpdateSerializer(_BaseProfileUpdateSerializer):
    company_name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(required=False, allow_blank=True)

    def save(self):
        user = self.context["request"].user
        transporter = self.instance
        validated_data = self.validated_data
        transporter_update_fields = []

        with transaction.atomic():
            self._update_user(user, validated_data)
            if "company_name" in validated_data:
                transporter.company_name = validated_data["company_name"]
                transporter_update_fields.append("company_name")
            if "address" in validated_data:
                transporter.address = validated_data["address"]
                transporter_update_fields.append("address")
            if transporter_update_fields:
                transporter.save(update_fields=transporter_update_fields)

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
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    company_name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

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
        validated_data.pop("otp")
        otp_obj = validated_data.pop("otp_obj")
        company_name = validated_data.pop("company_name")
        address = validated_data.pop("address", "")
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
            )
            self._consume_otp(otp_obj, email)

        return {"user": user, "transporter": transporter}


class DriverRegisterSerializer(_OtpValidationMixin, serializers.Serializer):
    otp_purpose = EmailOTP.Purpose.DRIVER_SIGNUP

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField()
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    license_number = serializers.CharField(max_length=50)
    transporter_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_license_number(self, value):
        if Driver.objects.filter(license_number__iexact=value).exists():
            raise serializers.ValidationError("This license number is already in use.")
        return value

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
        validated_data.pop("otp")
        otp_obj = validated_data.pop("otp_obj")
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
