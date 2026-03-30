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


class TransporterBillRecipientSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
    address = serializers.CharField()


class TransporterBankDetailsSerializer(serializers.Serializer):
    bank_name = serializers.CharField(allow_blank=True, required=False)
    branch = serializers.CharField(allow_blank=True, required=False)
    account_no = serializers.CharField(allow_blank=True, required=False)
    ifsc_code = serializers.CharField(allow_blank=True, required=False)


class TransporterBillHeaderDetailsSerializer(serializers.Serializer):
    company_name = serializers.CharField(allow_blank=True, required=False)
    contact_name = serializers.CharField(allow_blank=True, required=False)
    phone = serializers.CharField(allow_blank=True, required=False)
    email = serializers.CharField(allow_blank=True, required=False)
    gstin = serializers.CharField(allow_blank=True, required=False)
    pan = serializers.CharField(allow_blank=True, required=False)
    website = serializers.CharField(allow_blank=True, required=False)
    biller_name = serializers.CharField(allow_blank=True, required=False)


class VehicleMonthlyRunBillPdfRequestSerializer(serializers.Serializer):
    bill_no = serializers.CharField(required=False, allow_blank=True)
    recipient_id = serializers.IntegerField(required=False, allow_null=True)
    to_name = serializers.CharField(required=False, allow_blank=True)
    to_address = serializers.CharField(required=False, allow_blank=True)

    vehicle_number = serializers.CharField()
    service_name = serializers.CharField(required=False, allow_blank=True)

    month = serializers.IntegerField(required=False, allow_null=True)
    year = serializers.IntegerField(required=False, allow_null=True)
    bill_date = serializers.DateField(required=False, allow_null=True)

    base_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    extra_km = serializers.IntegerField(required=False, allow_null=True)
    extra_rate = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    bank_details = TransporterBankDetailsSerializer(required=False)
    header_details = TransporterBillHeaderDetailsSerializer(required=False)


class TransporterVehicleBillListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    bill_no = serializers.CharField()
    bill_date = serializers.DateField(allow_null=True)
    month = serializers.IntegerField(allow_null=True)
    year = serializers.IntegerField(allow_null=True)
    vehicle_number = serializers.CharField()
    service_name = serializers.CharField(allow_blank=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    created_at = serializers.DateTimeField()
