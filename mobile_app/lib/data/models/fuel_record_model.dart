import '../../domain/entities/fuel_record.dart';

class FuelRecordModel extends FuelRecord {
  const FuelRecordModel({
    required super.id,
    required super.entryType,
    required super.vehicleNumber,
    required super.driverName,
    required super.date,
    super.liters,
    super.amount,
    super.odometerKm,
    super.meterImageUrl,
    super.billImageUrl,
    super.fuelFilled,
    super.piuReading,
    super.dgHmr,
    super.openingStock,
    super.startKm,
    super.endKm,
    super.runKm,
    super.fillDate,
    super.indusSiteId,
    super.siteName,
    super.purpose,
    super.logbookPhotoUrl,
  });

  factory FuelRecordModel.fromJson(Map<String, dynamic> json) {
    final date = _parseDate(
      (json['date'] ?? json['fill_date'] ?? '').toString(),
    );
    final fillDateRaw = (json['fill_date'] ?? '').toString();
    return FuelRecordModel(
      id: _asInt(json['id']) ?? 0,
      entryType:
          (json['entry_type'] ?? 'VEHICLE_FILLING').toString().toUpperCase(),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      driverName: (json['driver_name'] ?? '').toString(),
      date: date,
      liters: _asDouble(json['liters']) ?? 0,
      amount: _asDouble(json['amount']) ?? 0,
      odometerKm: _asInt(json['odometer_km']),
      meterImageUrl: (json['meter_image_url'] ?? '').toString(),
      billImageUrl: (json['bill_image_url'] ?? '').toString(),
      fuelFilled:
          _asDouble(json['fuel_filled']) ?? _asDouble(json['liters']) ?? 0,
      piuReading: _asDouble(json['piu_reading']),
      dgHmr: _asDouble(json['dg_hmr']),
      openingStock: _asDouble(json['opening_stock']),
      startKm: _asInt(json['start_km']),
      endKm: _asInt(json['end_km']),
      runKm: _asInt(json['run_km']) ?? 0,
      fillDate: fillDateRaw.isEmpty ? null : _parseDate(fillDateRaw),
      indusSiteId: (json['indus_site_id'] ?? '').toString(),
      siteName: (json['site_name'] ?? '').toString(),
      purpose: (json['purpose'] ?? '').toString(),
      logbookPhotoUrl: (json['logbook_photo_url'] ?? '').toString(),
    );
  }

  static int? _asInt(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is int) {
      return value;
    }
    return int.tryParse(value.toString());
  }

  static double? _asDouble(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is double) {
      return value;
    }
    if (value is int) {
      return value.toDouble();
    }
    return double.tryParse(value.toString());
  }

  static DateTime _parseDate(String raw) {
    final parsed = DateTime.tryParse(raw);
    if (parsed != null) {
      return parsed;
    }
    return DateTime.now();
  }
}
