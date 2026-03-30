import '../../domain/entities/driver_location_session.dart';

class DriverLocationSessionModel extends DriverLocationSession {
  const DriverLocationSessionModel({
    required super.attendanceId,
    required super.driverId,
    required super.driverName,
    required super.vehicleNumber,
    required super.serviceName,
    required super.purpose,
    required super.statusLabel,
    required super.startedAtLabel,
    required super.endedAtLabel,
    required super.startKm,
    required super.endKm,
    required super.totalKm,
    required super.pointCount,
    required super.lastSeenLabel,
  });

  factory DriverLocationSessionModel.fromJson(Map<String, dynamic> json) {
    int? parseInt(dynamic value) {
      if (value == null) {
        return null;
      }
      if (value is int) {
        return value;
      }
      return int.tryParse(value.toString());
    }

    return DriverLocationSessionModel(
      attendanceId: json['attendance_id'] as int? ?? 0,
      driverId: json['driver_id'] as int? ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      serviceName: (json['service_name'] ?? '').toString(),
      purpose: (json['purpose'] ?? '').toString(),
      statusLabel: (json['status_label'] ?? '').toString(),
      startedAtLabel: (json['started_at_label'] ?? '').toString(),
      endedAtLabel: (json['ended_at_label'] ?? '').toString(),
      startKm: parseInt(json['start_km']),
      endKm: parseInt(json['end_km']),
      totalKm: json['total_km'] as int? ?? 0,
      pointCount: json['point_count'] as int? ?? 0,
      lastSeenLabel: (json['last_seen_label'] ?? '').toString(),
    );
  }
}

