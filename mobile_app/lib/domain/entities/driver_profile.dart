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
  });

  final AppUser user;
  final int id;
  final String licenseNumber;
  final bool isActive;
  final int? transporterId;
  final String? transporterCompanyName;
  final int? assignedVehicleId;
  final String? assignedVehicleNumber;
}
