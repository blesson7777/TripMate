class DriverLocationPoint {
  const DriverLocationPoint({
    required this.attendanceId,
    required this.driverId,
    required this.driverName,
    required this.vehicleNumber,
    required this.transporterName,
    required this.serviceName,
    required this.purpose,
    required this.pointType,
    required this.pointLabel,
    required this.latitude,
    required this.longitude,
    this.recordedAt,
    this.timeLabel,
    this.statusLabel,
    this.accuracyMeters,
    this.speedKph,
  });

  final int attendanceId;
  final int driverId;
  final String driverName;
  final String vehicleNumber;
  final String transporterName;
  final String serviceName;
  final String purpose;
  final String pointType;
  final String pointLabel;
  final double latitude;
  final double longitude;
  final DateTime? recordedAt;
  final String? timeLabel;
  final String? statusLabel;
  final double? accuracyMeters;
  final double? speedKph;
}

