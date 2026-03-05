from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from drivers.models import Driver
from users.models import EmailOTP
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
            "is_active",
        )

    def get_transporter_company(self, obj):
        if obj.transporter is None:
            return None
        return obj.transporter.company_name


class DriverVehicleAssignmentSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        request = self.context["request"]
        driver = self.context["driver"]
        transporter = request.user.transporter_profile
        vehicle_id = attrs.get("vehicle_id")

        if driver.transporter_id != transporter.id:
            raise serializers.ValidationError(
                {"detail": "You can assign vehicles only for your own drivers."}
            )

        vehicle = None
        if vehicle_id is not None:
            vehicle = Vehicle.objects.filter(id=vehicle_id).first()
            if not vehicle:
                raise serializers.ValidationError({"vehicle_id": "Vehicle does not exist."})
            if vehicle.transporter_id != transporter.id:
                raise serializers.ValidationError(
                    {"vehicle_id": "Vehicle does not belong to your transporter."}
                )

        attrs["vehicle"] = vehicle
        return attrs

    def save(self):
        driver = self.context["driver"]
        vehicle = self.validated_data["vehicle"]
        driver.assigned_vehicle = vehicle
        driver.save(update_fields=["assigned_vehicle"])
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
                driver.save(update_fields=["transporter", "assigned_vehicle"])
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
        return driver
