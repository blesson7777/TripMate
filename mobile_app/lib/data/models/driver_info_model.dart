import '../../domain/entities/driver_info.dart';

class DriverInfoModel extends DriverInfo {
  const DriverInfoModel({
    required super.id,
    required super.username,
    required super.phone,
    required super.licenseNumber,
    super.vehicleNumber,
  });

  factory DriverInfoModel.fromJson(Map<String, dynamic> json) {
    return DriverInfoModel(
      id: json['id'] as int,
      username: (json['username'] ?? '').toString(),
      phone: (json['phone'] ?? '').toString(),
      licenseNumber: (json['license_number'] ?? '').toString(),
      vehicleNumber: json['vehicle_number']?.toString(),
    );
  }
}
