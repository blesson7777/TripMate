class DriverLocationSession {
  const DriverLocationSession({
    required this.attendanceId,
    required this.driverId,
    required this.driverName,
    required this.vehicleNumber,
    required this.serviceName,
    required this.purpose,
    required this.statusLabel,
    required this.startedAtLabel,
    required this.endedAtLabel,
    required this.startKm,
    required this.endKm,
    required this.totalKm,
    required this.pointCount,
    required this.lastSeenLabel,
  });

  final int attendanceId;
  final int driverId;
  final String driverName;
  final String vehicleNumber;
  final String serviceName;
  final String purpose;
  final String statusLabel;
  final String startedAtLabel;
  final String endedAtLabel;
  final int? startKm;
  final int? endKm;
  final int totalKm;
  final int pointCount;
  final String lastSeenLabel;
}

