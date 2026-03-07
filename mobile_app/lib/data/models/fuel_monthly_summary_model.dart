import '../../domain/entities/fuel_monthly_summary.dart';

class VehicleFuelMonthlyRowModel extends VehicleFuelMonthlyRow {
  const VehicleFuelMonthlyRowModel({
    required super.vehicleId,
    required super.vehicleNumber,
    required super.fuelFillCount,
    required super.totalLiters,
    required super.totalAmount,
    required super.totalKm,
    required super.averageMileage,
  });

  factory VehicleFuelMonthlyRowModel.fromJson(Map<String, dynamic> json) {
    return VehicleFuelMonthlyRowModel(
      vehicleId: _asInt(json['vehicle_id']) ?? 0,
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      fuelFillCount: _asInt(json['fuel_fill_count']) ?? 0,
      totalLiters: _asDouble(json['total_liters']) ?? 0,
      totalAmount: _asDouble(json['total_amount']) ?? 0,
      totalKm: _asInt(json['total_km']) ?? 0,
      averageMileage: _asDouble(json['average_mileage']) ?? 0,
    );
  }
}

class FuelMonthlySummaryModel extends FuelMonthlySummary {
  const FuelMonthlySummaryModel({
    required super.month,
    required super.year,
    required super.totalVehiclesFilled,
    required super.totalFuelFills,
    required super.totalLiters,
    required super.totalAmount,
    required super.overallAverageMileage,
    required super.rows,
  });

  factory FuelMonthlySummaryModel.fromJson(Map<String, dynamic> json) {
    final rows = (json['rows'] as List<dynamic>? ?? const <dynamic>[])
        .map((item) => VehicleFuelMonthlyRowModel.fromJson(item as Map<String, dynamic>))
        .toList();
    return FuelMonthlySummaryModel(
      month: _asInt(json['month']) ?? 0,
      year: _asInt(json['year']) ?? 0,
      totalVehiclesFilled: _asInt(json['total_vehicles_filled']) ?? 0,
      totalFuelFills: _asInt(json['total_fuel_fills']) ?? 0,
      totalLiters: _asDouble(json['total_liters']) ?? 0,
      totalAmount: _asDouble(json['total_amount']) ?? 0,
      overallAverageMileage: _asDouble(json['overall_average_mileage']) ?? 0,
      rows: rows,
    );
  }
}

int? _asInt(dynamic value) {
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

double? _asDouble(dynamic value) {
  if (value is double) {
    return value;
  }
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value);
  }
  return null;
}
