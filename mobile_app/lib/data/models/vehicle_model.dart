import '../../domain/entities/vehicle.dart';

class VehicleModel extends Vehicle {
  const VehicleModel({
    required super.id,
    required super.vehicleNumber,
    required super.model,
    required super.status,
    super.latestOdometerKm,
    super.latestOdometerSource,
    super.tankCapacityLiters,
    super.fuelAverageMileage,
    super.fuelEstimatedTankCapacityLiters,
    super.fuelEstimatedLeftLiters,
    super.fuelEstimatedLeftPercent,
    super.fuelEstimatedKmLeft,
    super.fuelLastFillDate,
    super.fuelEstimatedDaysLeft,
  });

  factory VehicleModel.fromJson(Map<String, dynamic> json) {
    return VehicleModel(
      id: json['id'] as int,
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      model: (json['model'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      latestOdometerKm: _asInt(json['latest_odometer_km']),
      latestOdometerSource: json['latest_odometer_source']?.toString(),
      tankCapacityLiters: _asDouble(json['tank_capacity_liters']),
      fuelAverageMileage: _asDouble(json['fuel_average_mileage']),
      fuelEstimatedTankCapacityLiters:
          _asDouble(json['fuel_estimated_tank_capacity_liters']),
      fuelEstimatedLeftLiters: _asDouble(json['fuel_estimated_left_liters']),
      fuelEstimatedLeftPercent: _asDouble(json['fuel_estimated_left_percent']),
      fuelEstimatedKmLeft: _asInt(json['fuel_estimated_km_left']),
      fuelLastFillDate: _asDateTime(json['fuel_last_fill_date']),
      fuelEstimatedDaysLeft: _asDouble(json['fuel_estimated_days_left']),
    );
  }

  static int? _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    if (value is String) {
      return int.tryParse(value);
    }
    return null;
  }

  static double? _asDouble(dynamic value) {
    if (value is double) {
      return value;
    }
    if (value is int) {
      return value.toDouble();
    }
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
  }

  static DateTime? _asDateTime(dynamic value) {
    if (value is String && value.trim().isNotEmpty) {
      return DateTime.tryParse(value);
    }
    return null;
  }
}
