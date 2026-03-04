import '../../domain/entities/fuel_record.dart';

class FuelRecordModel extends FuelRecord {
  const FuelRecordModel({
    required super.id,
    required super.liters,
    required super.amount,
    required super.date,
    required super.vehicleNumber,
    required super.driverName,
  });

  factory FuelRecordModel.fromJson(Map<String, dynamic> json) {
    return FuelRecordModel(
      id: json['id'] as int,
      liters: double.tryParse(json['liters'].toString()) ?? 0,
      amount: double.tryParse(json['amount'].toString()) ?? 0,
      date: DateTime.parse((json['date'] ?? '').toString()),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      driverName: (json['driver_name'] ?? '').toString(),
    );
  }
}
