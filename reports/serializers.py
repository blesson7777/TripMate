from rest_framework import serializers


class MonthlyTripSheetRowSerializer(serializers.Serializer):
    date = serializers.DateField()
    start_km = serializers.IntegerField()
    end_km = serializers.IntegerField()
    total_km = serializers.IntegerField()


class MonthlyReportSerializer(serializers.Serializer):
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    vehicle_id = serializers.IntegerField(allow_null=True)
    total_days = serializers.IntegerField()
    total_km = serializers.IntegerField()
    rows = MonthlyTripSheetRowSerializer(many=True)
