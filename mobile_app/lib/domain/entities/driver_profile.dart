import 'app_user.dart';

class DriverProfile {
  const DriverProfile({
    required this.user,
    required this.id,
    required this.licenseNumber,
    required this.isActive,
    this.transporterId,
    this.transporterCompanyName,
    this.assignedVehicleId,
    this.assignedVehicleNumber,
    this.defaultServiceId,
    this.defaultServiceName,
    required this.dieselTrackingEnabled,
    required this.dieselReadingsEnabled,
    required this.locationTrackingEnabled,
  });

  final AppUser user;
  final int id;
  final String licenseNumber;
  final bool isActive;
  final int? transporterId;
  final String? transporterCompanyName;
  final int? assignedVehicleId;
  final String? assignedVehicleNumber;
  final int? defaultServiceId;
  final String? defaultServiceName;
  final bool dieselTrackingEnabled;
  final bool dieselReadingsEnabled;
  final bool locationTrackingEnabled;
}
