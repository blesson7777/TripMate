class DriverInfo {
  const DriverInfo({
    required this.id,
    required this.username,
    required this.phone,
    required this.licenseNumber,
    this.vehicleId,
    this.vehicleNumber,
  });

  final int id;
  final String username;
  final String phone;
  final String licenseNumber;
  final int? vehicleId;
  final String? vehicleNumber;
}
