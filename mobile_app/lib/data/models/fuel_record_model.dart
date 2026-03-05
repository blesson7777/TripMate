import '../../domain/entities/fuel_record.dart';

class FuelRecordModel extends FuelRecord {
  const FuelRecordModel({
    required super.id,
    required super.liters,
    required super.amount,
    super.odometerKm,
    required super.date,
    required super.vehicleNumber,
    required super.driverName,
  });

  factory FuelRecordModel.fromJson(Map<String, dynamic> json) {
    return FuelRecordModel(
      id: json['id'] as int,
      liters: double.tryParse(json['liters'].toString()) ?? 0,
      amount: double.tryParse(json['amount'].toString()) ?? 0,
      odometerKm: int.tryParse((json['odometer_km'] ?? '').toString()),
      date: DateTime.parse((json['date'] ?? '').toString()),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      driverName: (json['driver_name'] ?? '').toString(),
    );
  }
}
