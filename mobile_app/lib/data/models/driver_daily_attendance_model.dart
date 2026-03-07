import '../../domain/entities/driver_daily_attendance.dart';

class DriverDailyAttendanceModel extends DriverDailyAttendance {
  const DriverDailyAttendanceModel({
    required super.driverId,
    required super.driverName,
    required super.licenseNumber,
    required super.date,
    required super.status,
    required super.canStartDay,
    required super.hasAttendance,
    required super.hasMark,
    super.markStatus,
    super.assignedVehicleNumber,
    super.attendanceVehicleNumber,
    super.serviceName,
    super.servicePurpose,
    super.startKm,
    super.endKm,
  });

  factory DriverDailyAttendanceModel.fromJson(Map<String, dynamic> json) {
    DateTime parseDate(dynamic value) {
      final raw = value?.toString();
      if (raw == null || raw.isEmpty) {
        return DateTime.now();
      }
      return DateTime.tryParse(raw) ?? DateTime.now();
    }

    return DriverDailyAttendanceModel(
      driverId: json['driver_id'] as int? ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      licenseNumber: (json['license_number'] ?? '').toString(),
      date: parseDate(json['date']),
      status: (json['status'] ?? '').toString(),
      markStatus: json['mark_status']?.toString(),
      canStartDay: json['can_start_day'] as bool? ?? false,
      hasAttendance: json['has_attendance'] as bool? ?? false,
      hasMark: json['has_mark'] as bool? ?? false,
      assignedVehicleNumber: json['assigned_vehicle_number']?.toString(),
      attendanceVehicleNumber: json['attendance_vehicle_number']?.toString(),
      serviceName: json['service_name']?.toString(),
      servicePurpose: json['service_purpose']?.toString(),
      startKm: json['start_km'] as int?,
      endKm: json['end_km'] as int?,
    );
  }
}
