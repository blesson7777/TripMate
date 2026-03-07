import '../../domain/entities/driver_profile.dart';
import 'app_user_model.dart';

class DriverProfileModel extends DriverProfile {
  const DriverProfileModel({
    required super.user,
    required super.id,
    required super.licenseNumber,
    required super.isActive,
    super.transporterId,
    super.transporterCompanyName,
    super.assignedVehicleId,
    super.assignedVehicleNumber,
    super.defaultServiceId,
    super.defaultServiceName,
    required super.dieselTrackingEnabled,
  });

  factory DriverProfileModel.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'] as Map<String, dynamic>? ?? <String, dynamic>{};
    final driverJson =
        json['driver'] as Map<String, dynamic>? ?? <String, dynamic>{};
    final transporterJson =
        driverJson['transporter'] as Map<String, dynamic>? ?? <String, dynamic>{};
    final vehicleJson = driverJson['assigned_vehicle'] as Map<String, dynamic>?;
    final serviceJson = driverJson['default_service'] as Map<String, dynamic>?;

    return DriverProfileModel(
      user: AppUserModel.fromJson(userJson),
      id: driverJson['id'] as int? ?? 0,
      licenseNumber: (driverJson['license_number'] ?? '').toString(),
      isActive: driverJson['is_active'] as bool? ?? true,
      transporterId: transporterJson['id'] as int?,
      transporterCompanyName: transporterJson['company_name']?.toString(),
      assignedVehicleId: vehicleJson?['id'] as int?,
      assignedVehicleNumber: vehicleJson?['vehicle_number']?.toString(),
      defaultServiceId: serviceJson?['id'] as int?,
      defaultServiceName: serviceJson?['name']?.toString(),
      dieselTrackingEnabled:
          transporterJson['diesel_tracking_enabled'] as bool? ?? false,
    );
  }
}
