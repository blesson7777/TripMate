import '../../domain/entities/vehicle.dart';

class VehicleModel extends Vehicle {
  const VehicleModel({
    required super.id,
    required super.vehicleNumber,
    required super.model,
    required super.status,
  });

  factory VehicleModel.fromJson(Map<String, dynamic> json) {
    return VehicleModel(
      id: json['id'] as int,
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      model: (json['model'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
    );
  }
}
