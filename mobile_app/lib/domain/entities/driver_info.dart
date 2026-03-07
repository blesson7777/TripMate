class DriverInfo {
  const DriverInfo({
    required this.id,
    required this.username,
    required this.phone,
    required this.licenseNumber,
    this.vehicleId,
    this.vehicleNumber,
    this.defaultServiceId,
    this.defaultServiceName,
    this.monthlySalary,
  });

  final int id;
  final String username;
  final String phone;
  final String licenseNumber;
  final int? vehicleId;
  final String? vehicleNumber;
  final int? defaultServiceId;
  final String? defaultServiceName;
  final double? monthlySalary;
}
