from rest_framework import serializers

from fuel.analytics import get_vehicle_fuel_status
from tripmate.odometer_utils import get_latest_vehicle_odometer_point
from vehicles.models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    transporter_id = serializers.IntegerField(source="transporter.id", read_only=True)
    transporter_company = serializers.CharField(
        source="transporter.company_name", read_only=True
    )
    latest_odometer_km = serializers.SerializerMethodField()
    latest_odometer_source = serializers.SerializerMethodField()
    fuel_average_mileage = serializers.SerializerMethodField()
    fuel_estimated_tank_capacity_liters = serializers.SerializerMethodField()
    fuel_estimated_left_liters = serializers.SerializerMethodField()
    fuel_estimated_left_percent = serializers.SerializerMethodField()
    fuel_estimated_km_left = serializers.SerializerMethodField()
    fuel_last_fill_date = serializers.SerializerMethodField()
    fuel_estimated_days_left = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "transporter_id",
            "transporter_company",
            "vehicle_number",
            "model",
            "status",
            "vehicle_type",
            "tank_capacity_liters",
            "latest_odometer_km",
            "latest_odometer_source",
            "fuel_average_mileage",
            "fuel_estimated_tank_capacity_liters",
            "fuel_estimated_left_liters",
            "fuel_estimated_left_percent",
            "fuel_estimated_km_left",
            "fuel_last_fill_date",
            "fuel_estimated_days_left",
            "created_at",
        )

    def _latest_odometer_point(self, obj):
        cache_name = "_latest_odometer_point"
        cached = getattr(obj, cache_name, None)
        if cached is None:
            cached = get_latest_vehicle_odometer_point(obj)
            setattr(obj, cache_name, cached)
        return cached

    def get_latest_odometer_km(self, obj):
        point = self._latest_odometer_point(obj)
        return point.value if point is not None else None

    def get_latest_odometer_source(self, obj):
        point = self._latest_odometer_point(obj)
        return point.source if point is not None else None

    def _fuel_status(self, obj):
        cache_name = "_fuel_status_snapshot"
        cached = getattr(obj, cache_name, None)
        if cached is None:
            cached = get_vehicle_fuel_status(obj)
            setattr(obj, cache_name, cached)
        return cached

    def get_fuel_average_mileage(self, obj):
        snapshot = self._fuel_status(obj)
        return str(snapshot.average_mileage_km_per_liter) if snapshot else None

    def get_fuel_estimated_tank_capacity_liters(self, obj):
        snapshot = self._fuel_status(obj)
        return str(snapshot.estimated_tank_capacity_liters) if snapshot else None

    def get_fuel_estimated_left_liters(self, obj):
        snapshot = self._fuel_status(obj)
        return str(snapshot.estimated_fuel_left_liters) if snapshot else None

    def get_fuel_estimated_left_percent(self, obj):
        snapshot = self._fuel_status(obj)
        return str(snapshot.estimated_fuel_left_percent) if snapshot else None

    def get_fuel_estimated_km_left(self, obj):
        snapshot = self._fuel_status(obj)
        return snapshot.estimated_km_left if snapshot else None

    def get_fuel_last_fill_date(self, obj):
        snapshot = self._fuel_status(obj)
        return snapshot.last_fill_date.isoformat() if snapshot and snapshot.last_fill_date else None

    def get_fuel_estimated_days_left(self, obj):
        snapshot = self._fuel_status(obj)
        return str(snapshot.estimated_days_left) if snapshot and snapshot.estimated_days_left is not None else None


class VehicleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = (
            "vehicle_number",
            "model",
            "status",
            "vehicle_type",
            "tank_capacity_liters",
        )

    def validate_vehicle_number(self, value):
        normalized = value.strip().upper()
        if Vehicle.objects.filter(
            vehicle_number__iexact=normalized,
        ).exists():
            raise serializers.ValidationError(
                "A vehicle with this number already exists in the system."
            )
        return normalized

    def validate_vehicle_type(self, value):
        valid_types = {choice[0] for choice in Vehicle.Type.choices}
        if value not in valid_types:
            raise serializers.ValidationError("Invalid vehicle type.")
        return value

    def validate_tank_capacity_liters(self, value):
        if value is None:
            return value
        if value <= 0:
            raise serializers.ValidationError("Tank capacity must be greater than zero.")
        return value
