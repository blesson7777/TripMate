import os
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from diesel.models import IndusTowerSite
from diesel.site_utils import (
    SiteNameUpdateConfirmationRequired,
    ensure_site_name_update_confirmed,
    haversine_distance_meters,
    validate_indus_site_id,
    validate_site_name,
)
from fuel.models import FuelRecord
from trips.models import Trip


class TowerDieselRecordSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.username", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)
    partner_id = serializers.IntegerField(source="partner.id", read_only=True)
    indus_site_id = serializers.SerializerMethodField()
    site_name = serializers.SerializerMethodField()
    tower_latitude = serializers.SerializerMethodField()
    tower_longitude = serializers.SerializerMethodField()
    logbook_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = FuelRecord
        fields = (
            "id",
            "attendance",
            "driver",
            "driver_name",
            "partner_id",
            "vehicle",
            "vehicle_number",
            "indus_site_id",
            "site_name",
            "purpose",
            "fuel_filled",
            "start_km",
            "end_km",
            "run_km",
            "tower_latitude",
            "tower_longitude",
            "fill_date",
            "logbook_photo",
            "logbook_photo_url",
            "ocr_raw_text",
            "ocr_confidence",
            "created_at",
        )
        read_only_fields = ("attendance", "driver", "vehicle")

    def get_logbook_photo_url(self, obj):
        if not obj.logbook_photo:
            return ""
        request = self.context.get("request")
        if request is None:
            return obj.logbook_photo.url
        return request.build_absolute_uri(f"/api/diesel/{obj.id}/logbook-photo")

    def get_indus_site_id(self, obj):
        return (obj.resolved_indus_site_id or "").strip()

    def get_site_name(self, obj):
        return (obj.resolved_site_name or "").strip()

    def get_tower_latitude(self, obj):
        return obj.resolved_tower_latitude

    def get_tower_longitude(self, obj):
        return obj.resolved_tower_longitude


class TowerDieselRecordCreateSerializer(serializers.ModelSerializer):
    fuel_filled = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    start_km = serializers.IntegerField(min_value=0, required=False)
    end_km = serializers.IntegerField(min_value=0, required=False)
    fill_date = serializers.DateField(required=False)
    tower_latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    tower_longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    logbook_photo = serializers.ImageField(required=True)
    indus_site_id = serializers.CharField(max_length=64, allow_blank=True)
    site_name = serializers.CharField(max_length=255, allow_blank=True)
    confirm_site_name_update = serializers.BooleanField(
        required=False,
        default=False,
        write_only=True,
    )
    purpose = serializers.CharField(max_length=255, allow_blank=True, required=False)
    ocr_raw_text = serializers.CharField(required=False, allow_blank=True)
    ocr_confidence = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0.00"),
        max_value=Decimal("1.00"),
    )

    class Meta:
        model = FuelRecord
        fields = (
            "indus_site_id",
            "site_name",
            "confirm_site_name_update",
            "purpose",
            "fuel_filled",
            "start_km",
            "end_km",
            "tower_latitude",
            "tower_longitude",
            "fill_date",
            "logbook_photo",
            "ocr_raw_text",
            "ocr_confidence",
        )

    def validate_logbook_photo(self, value):
        max_size_bytes = 5 * 1024 * 1024
        if value.size > max_size_bytes:
            raise serializers.ValidationError("Logbook photo must be <= 5MB.")

        allowed_mime_types = {"image/jpeg", "image/jpg", "image/png"}
        content_type = (getattr(value, "content_type", "") or "").lower()
        if content_type and content_type not in allowed_mime_types:
            raise serializers.ValidationError("Only JPG, JPEG and PNG images are allowed.")

        extension = os.path.splitext(value.name or "")[1].lower()
        if extension not in {".jpg", ".jpeg", ".png"}:
            raise serializers.ValidationError("Only JPG, JPEG and PNG images are allowed.")

        filename = value.name.replace("\\", "/")
        if "../" in filename or filename.startswith("/"):
            raise serializers.ValidationError("Invalid file name.")
        return value

    def validate(self, attrs):
        indus_site_id = (attrs.get("indus_site_id") or "").strip()
        site_name = (attrs.get("site_name") or "").strip()
        confirm_site_name_update = bool(attrs.get("confirm_site_name_update"))
        start_km = attrs.get("start_km")
        end_km = attrs.get("end_km")
        tower_latitude = attrs.get("tower_latitude")
        tower_longitude = attrs.get("tower_longitude")
        driver = self.context.get("driver")

        try:
            indus_site_id = validate_indus_site_id(indus_site_id)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"indus_site_id": exc.messages[0]}) from exc
        attrs["indus_site_id"] = indus_site_id

        existing_site = None
        if driver is not None:
            existing_site = (
                IndusTowerSite.objects.filter(
                    partner=driver.transporter,
                    indus_site_id__iexact=indus_site_id,
                )
                .order_by("id")
                .first()
            )
        try:
            site_name = validate_site_name(
                site_name,
                required=existing_site is None,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"site_name": exc.messages[0]}) from exc
        if not site_name and existing_site is not None:
            site_name = existing_site.site_name
        if existing_site is not None:
            try:
                ensure_site_name_update_confirmed(
                    site_id=indus_site_id,
                    existing_name=existing_site.site_name,
                    submitted_name=site_name,
                    confirmed=confirm_site_name_update,
                )
            except SiteNameUpdateConfirmationRequired as exc:
                raise serializers.ValidationError(
                    {
                        "site_name": exc.messages[0],
                        "confirm_site_name_update": "Confirm site name update to continue.",
                    }
                ) from exc
        attrs["site_name"] = site_name

        if start_km is not None and end_km is not None and end_km < start_km:
            raise serializers.ValidationError(
                {"end_km": "End KM must be greater than or equal to Start KM."}
            )
        if (tower_latitude is None) ^ (tower_longitude is None):
            raise serializers.ValidationError(
                "tower_latitude and tower_longitude should be sent together."
            )
        if tower_latitude is not None and (tower_latitude < -90 or tower_latitude > 90):
            raise serializers.ValidationError({"tower_latitude": "Invalid latitude."})
        if tower_longitude is not None and (tower_longitude < -180 or tower_longitude > 180):
            raise serializers.ValidationError({"tower_longitude": "Invalid longitude."})
        if driver is not None and (tower_latitude is None or tower_longitude is None):
            raise serializers.ValidationError(
                {"detail": "Current location is required for driver tower diesel filling."}
            )
        if (
            existing_site is not None
            and existing_site.latitude is not None
            and existing_site.longitude is not None
            and tower_latitude is not None
            and tower_longitude is not None
        ):
            distance_m = haversine_distance_meters(
                float(tower_latitude),
                float(tower_longitude),
                float(existing_site.latitude),
                float(existing_site.longitude),
            )
            if distance_m > 100:
                raise serializers.ValidationError(
                    {
                        "detail": (
                            "You must be within 100 meters of the saved tower "
                            "location to add filling details for this site."
                        )
                    }
                )

        # Prevent accidental duplicate submission for the same tower within 10 minutes.
        if driver is not None:
            fill_date = attrs.get("fill_date") or timezone.localdate()
            fuel_filled = attrs.get("fuel_filled")
            ten_minutes_ago = timezone.now() - timedelta(minutes=10)

            duplicate_qs = FuelRecord.objects.filter(
                entry_type=FuelRecord.EntryType.TOWER_DIESEL,
                driver=driver,
                partner=driver.transporter,
                fill_date=fill_date,
                fuel_filled=fuel_filled,
                created_at__gte=ten_minutes_ago,
            )
            if indus_site_id:
                duplicate_qs = duplicate_qs.filter(
                    Q(tower_site__indus_site_id__iexact=indus_site_id)
                    | Q(indus_site_id__iexact=indus_site_id)
                )
            else:
                duplicate_qs = duplicate_qs.filter(
                    Q(tower_site__isnull=True),
                    indus_site_id="",
                )

            if site_name:
                duplicate_qs = duplicate_qs.filter(
                    Q(tower_site__site_name__iexact=site_name)
                    | Q(site_name__iexact=site_name)
                )
            else:
                duplicate_qs = duplicate_qs.filter(site_name="")

            if duplicate_qs.exists():
                raise serializers.ValidationError(
                    {"detail": "Duplicate tower diesel entry is not allowed within 10 minutes."}
                )
        return attrs

    def create(self, validated_data):
        attendance = self.context["attendance"]
        driver = self.context["driver"]
        vehicle = attendance.vehicle
        site_id = (validated_data.get("indus_site_id") or "").strip()
        site_name = (validated_data.get("site_name") or "").strip()
        tower_latitude = validated_data.get("tower_latitude")
        tower_longitude = validated_data.get("tower_longitude")

        tower_site = (
            IndusTowerSite.objects.filter(
                partner=driver.transporter,
                indus_site_id__iexact=site_id,
            )
            .order_by("id")
            .first()
        )
        if tower_site is None:
            tower_site = IndusTowerSite.objects.create(
                partner=driver.transporter,
                indus_site_id=site_id,
                site_name=site_name,
                latitude=tower_latitude,
                longitude=tower_longitude,
            )
        else:
            fields_to_update = []
            if site_name and tower_site.site_name != site_name:
                tower_site.site_name = site_name
                fields_to_update.append("site_name")
            if tower_site.latitude is None and tower_latitude is not None:
                tower_site.latitude = tower_latitude
                fields_to_update.append("latitude")
            if tower_site.longitude is None and tower_longitude is not None:
                tower_site.longitude = tower_longitude
                fields_to_update.append("longitude")
            if fields_to_update:
                fields_to_update.append("updated_at")
                tower_site.save(update_fields=fields_to_update)
            if not site_name:
                site_name = tower_site.site_name

        # Tower diesel uses Start Day and Day End workflow for KM bounds.
        resolved_start_km = attendance.start_km
        latest_additional_trip = (
            Trip.objects.filter(
                attendance=attendance,
                is_day_trip=False,
                end_km__isnull=False,
            )
            .order_by("-ended_at", "-created_at", "-id")
            .first()
        )
        if latest_additional_trip is not None:
            resolved_end_km = latest_additional_trip.end_km
        elif attendance.end_km is not None:
            resolved_end_km = attendance.end_km
        else:
            resolved_end_km = validated_data.get("end_km", resolved_start_km)

        if resolved_end_km < resolved_start_km:
            resolved_end_km = resolved_start_km

        fuel_filled = validated_data["fuel_filled"]
        fill_date = validated_data.get("fill_date") or timezone.localdate()
        purpose = validated_data.get("purpose", "").strip() or "Diesel Filling"
        return FuelRecord.objects.create(
            attendance=attendance,
            driver=driver,
            vehicle=vehicle,
            partner=driver.transporter,
            entry_type=FuelRecord.EntryType.TOWER_DIESEL,
            liters=fuel_filled,
            fuel_filled=fuel_filled,
            amount=Decimal("0.00"),
            odometer_km=resolved_end_km,
            tower_site=tower_site,
            indus_site_id="",
            site_name="",
            purpose=purpose,
            start_km=resolved_start_km,
            end_km=resolved_end_km,
            tower_latitude=None,
            tower_longitude=None,
            fill_date=fill_date,
            date=fill_date,
            logbook_photo=validated_data["logbook_photo"],
            ocr_raw_text=validated_data.get("ocr_raw_text", ""),
            ocr_confidence=validated_data.get("ocr_confidence"),
        )
