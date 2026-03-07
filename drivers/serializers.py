from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from attendance.models import TransportService
from drivers.models import Driver
from users.models import EmailOTP
from users.notification_utils import create_driver_allocation_welcome_notification
from users.services import send_driver_allocation_otp
from vehicles.models import Vehicle

User = get_user_model()


class DriverSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    transporter_company = serializers.SerializerMethodField()
    vehicle_number = serializers.CharField(
        source="assigned_vehicle.vehicle_number", read_only=True
    )
    default_service_name = serializers.CharField(
        source="default_service.name",
        read_only=True,
    )

    class Meta:
        model = Driver
        fields = (
            "id",
            "username",
            "phone",
            "license_number",
            "transporter",
            "transporter_company",
            "assigned_vehicle",
            "vehicle_number",
            "default_service",
            "default_service_name",
            "monthly_salary",
            "joined_transporter_at",
            "is_active",
        )

    def get_transporter_company(self, obj):
        if obj.transporter is None:
            return None
        return obj.transporter.company_name


class DriverVehicleAssignmentSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField(required=False, allow_null=True)
    service_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        request = self.context["request"]
        driver = self.context["driver"]
        transporter = request.user.transporter_profile
        vehicle_provided = "vehicle_id" in attrs
        service_provided = "service_id" in attrs

        if driver.transporter_id != transporter.id:
            raise serializers.ValidationError(
                {"detail": "You can assign vehicles only for your own drivers."}
            )

        vehicle = None
        if vehicle_provided and attrs.get("vehicle_id") is not None:
            vehicle_id = attrs["vehicle_id"]
            vehicle = Vehicle.objects.filter(id=vehicle_id).first()
            if not vehicle:
                raise serializers.ValidationError({"vehicle_id": "Vehicle does not exist."})
            if vehicle.transporter_id != transporter.id:
                raise serializers.ValidationError(
                    {"vehicle_id": "Vehicle does not belong to your transporter."}
                )

        service = None
        if service_provided and attrs.get("service_id") is not None:
            service_id = attrs["service_id"]
            service = (
                TransportService.objects.filter(
                    id=service_id,
                    transporter_id=transporter.id,
                    is_active=True,
                )
                .order_by("id")
                .first()
            )
            if service is None:
                raise serializers.ValidationError(
                    {
                        "service_id": (
                            "Service does not exist, is inactive, or does not belong to your transporter."
                        )
                    }
                )

        attrs["vehicle_provided"] = vehicle_provided
        attrs["service_provided"] = service_provided
        attrs["vehicle"] = vehicle
        attrs["service"] = service
        return attrs

    def save(self):
        driver = self.context["driver"]
        update_fields = []

        if self.validated_data["vehicle_provided"]:
            driver.assigned_vehicle = self.validated_data["vehicle"]
            update_fields.append("assigned_vehicle")

        if self.validated_data["service_provided"]:
            driver.default_service = self.validated_data["service"]
            update_fields.append("default_service")

        if update_fields:
            driver.save(update_fields=update_fields)
        driver.refresh_from_db()
        return driver


class DriverAllocationOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        transporter = self.context["request"].user.transporter_profile

        try:
            user = User.objects.get(email__iexact=email, role=User.Role.DRIVER)
        except User.DoesNotExist as exception:
            raise serializers.ValidationError(
                {"email": "No registered driver account found for this email."}
            ) from exception

        if not hasattr(user, "driver_profile"):
            raise serializers.ValidationError(
                {"email": "No driver profile exists for this account."}
            )

        driver = user.driver_profile
        if driver.transporter_id == transporter.id:
            raise serializers.ValidationError(
                {"email": "Driver is already allocated to your transporter."}
            )

        attrs["email"] = email
        return attrs

    def create(self, validated_data):
        otp = send_driver_allocation_otp(validated_data["email"])
        return {
            "email": validated_data["email"],
            "debug_otp": otp.code if settings.DEBUG else None,
        }


class DriverAllocationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        otp_code = attrs["otp"].strip()
        transporter = self.context["request"].user.transporter_profile

        try:
            user = User.objects.get(email__iexact=email, role=User.Role.DRIVER)
        except User.DoesNotExist as exception:
            raise serializers.ValidationError(
                {"email": "No registered driver account found for this email."}
            ) from exception

        if not hasattr(user, "driver_profile"):
            raise serializers.ValidationError(
                {"email": "No driver profile exists for this account."}
            )

        driver = user.driver_profile
        if driver.transporter_id == transporter.id:
            raise serializers.ValidationError(
                {"email": "Driver is already allocated to your transporter."}
            )

        otp = (
            EmailOTP.objects.filter(
                email__iexact=email,
                purpose=EmailOTP.Purpose.DRIVER_ALLOCATION,
                code=otp_code,
                is_used=False,
                expires_at__gte=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})

        attrs["email"] = email
        attrs["otp_obj"] = otp
        attrs["driver"] = driver
        return attrs

    def save(self):
        transporter = self.context["request"].user.transporter_profile
        driver = self.validated_data["driver"]
        otp = self.validated_data["otp_obj"]
        email = self.validated_data["email"]

        with transaction.atomic():
            driver.transporter = transporter
            # If driver was previously allocated and had a vehicle from old transporter,
            # clear vehicle before moving to the new transporter.
            if (
                driver.assigned_vehicle_id is not None
                and driver.assigned_vehicle is not None
                and driver.assigned_vehicle.transporter_id != transporter.id
            ):
                driver.assigned_vehicle = None
                driver.default_service = None
                driver.save(
                    update_fields=["transporter", "assigned_vehicle", "default_service"]
                )
            else:
                if (
                    driver.default_service_id is not None
                    and driver.default_service is not None
                    and driver.default_service.transporter_id != transporter.id
                ):
                    driver.default_service = None
                    driver.save(update_fields=["transporter", "default_service"])
                else:
                    driver.save(update_fields=["transporter"])

            otp.is_used = True
            otp.save(update_fields=["is_used"])
            EmailOTP.objects.filter(
                email__iexact=email,
                purpose=EmailOTP.Purpose.DRIVER_ALLOCATION,
                is_used=False,
            ).exclude(pk=otp.pk).update(is_used=True)

        driver.refresh_from_db()
        create_driver_allocation_welcome_notification(
            driver=driver,
            transporter=transporter,
        )
        return driver
