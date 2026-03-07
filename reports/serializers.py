from rest_framework import serializers


class MonthlyTripSheetRowSerializer(serializers.Serializer):
    sl_no = serializers.IntegerField()
    date = serializers.DateField()
    vehicle_number = serializers.CharField()
    service_id = serializers.IntegerField(allow_null=True)
    service_name = serializers.CharField()
    opening_km = serializers.IntegerField()
    closing_km = serializers.IntegerField()
    total_run_km = serializers.IntegerField()
    purpose = serializers.CharField()

    # Backward-compatible aliases.
    start_km = serializers.IntegerField()
    end_km = serializers.IntegerField()
    total_km = serializers.IntegerField()


class MonthlyReportSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    vehicle_id = serializers.IntegerField(allow_null=True)
    service_id = serializers.IntegerField(allow_null=True)
    service_name = serializers.CharField(allow_null=True, allow_blank=True)
    total_days = serializers.IntegerField()
    total_km = serializers.IntegerField()
    rows = MonthlyTripSheetRowSerializer(many=True)


class VehicleFuelMonthlyRowSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField()
    vehicle_number = serializers.CharField()
    fuel_fill_count = serializers.IntegerField()
    total_liters = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_km = serializers.IntegerField()
    average_mileage = serializers.DecimalField(max_digits=12, decimal_places=2)


class FuelMonthlySummarySerializer(serializers.Serializer):
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    total_vehicles_filled = serializers.IntegerField()
    total_fuel_fills = serializers.IntegerField()
    total_liters = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    overall_average_mileage = serializers.DecimalField(max_digits=12, decimal_places=2)
    rows = VehicleFuelMonthlyRowSerializer(many=True)
