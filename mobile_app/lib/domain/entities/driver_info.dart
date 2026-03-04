class DriverInfo {
  const DriverInfo({
    required this.id,
    required this.username,
    required this.phone,
    required this.licenseNumber,
    this.vehicleNumber,
  });

  final int id;
  final String username;
  final String phone;
  final String licenseNumber;
  final String? vehicleNumber;
}
