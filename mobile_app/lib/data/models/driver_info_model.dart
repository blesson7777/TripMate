import '../../domain/entities/driver_info.dart';

class DriverInfoModel extends DriverInfo {
  const DriverInfoModel({
    required super.id,
    required super.username,
    required super.phone,
    required super.licenseNumber,
    super.vehicleId,
    super.vehicleNumber,
    super.defaultServiceId,
    super.defaultServiceName,
    super.monthlySalary,
  });

  factory DriverInfoModel.fromJson(Map<String, dynamic> json) {
    return DriverInfoModel(
      id: json['id'] as int,
      username: (json['username'] ?? '').toString(),
      phone: (json['phone'] ?? '').toString(),
      licenseNumber: (json['license_number'] ?? '').toString(),
      vehicleId: json['assigned_vehicle'] as int?,
      vehicleNumber: json['vehicle_number']?.toString(),
      defaultServiceId: json['default_service'] as int?,
      defaultServiceName: json['default_service_name']?.toString(),
      monthlySalary: _asDouble(json['monthly_salary']),
    );
  }

  static double? _asDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }
}
