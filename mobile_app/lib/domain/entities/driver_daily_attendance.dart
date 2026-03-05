class DriverDailyAttendance {
  const DriverDailyAttendance({
    required this.driverId,
    required this.driverName,
    required this.licenseNumber,
    required this.date,
    required this.status,
    required this.canStartDay,
    required this.hasAttendance,
    required this.hasMark,
    this.markStatus,
    this.assignedVehicleNumber,
    this.attendanceVehicleNumber,
    this.startKm,
    this.endKm,
  });

  final int driverId;
  final String driverName;
  final String licenseNumber;
  final DateTime date;
  final String status;
  final String? markStatus;
  final bool canStartDay;
  final bool hasAttendance;
  final bool hasMark;
  final String? assignedVehicleNumber;
  final String? attendanceVehicleNumber;
  final int? startKm;
  final int? endKm;
}
