import '../../domain/entities/driver_location_point.dart';

class DriverLocationPointModel extends DriverLocationPoint {
  const DriverLocationPointModel({
    required super.attendanceId,
    required super.driverId,
    required super.driverName,
    required super.vehicleNumber,
    required super.transporterName,
    required super.serviceName,
    required super.purpose,
    required super.pointType,
    required super.pointLabel,
    required super.latitude,
    required super.longitude,
    super.recordedAt,
    super.timeLabel,
    super.statusLabel,
    super.accuracyMeters,
    super.speedKph,
  });

  factory DriverLocationPointModel.fromJson(Map<String, dynamic> json) {
    DateTime? parseDateTime(dynamic value) {
      final raw = value?.toString();
      if (raw == null || raw.isEmpty) {
        return null;
      }
      return DateTime.tryParse(raw);
    }

    double parseDouble(dynamic value, {double fallback = 0}) {
      if (value == null) {
        return fallback;
      }
      if (value is num) {
        return value.toDouble();
      }
      return double.tryParse(value.toString()) ?? fallback;
    }

    return DriverLocationPointModel(
      attendanceId: json['attendance_id'] as int? ?? 0,
      driverId: json['driver_id'] as int? ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      transporterName: (json['transporter_name'] ?? '').toString(),
      serviceName: (json['service_name'] ?? '').toString(),
      purpose: (json['purpose'] ?? '').toString(),
      pointType: (json['point_type'] ?? '').toString(),
      pointLabel: (json['point_label'] ?? '').toString(),
      latitude: parseDouble(json['latitude']),
      longitude: parseDouble(json['longitude']),
      recordedAt: parseDateTime(json['recorded_at']),
      timeLabel: json['time_label']?.toString(),
      statusLabel: json['status_label']?.toString(),
      accuracyMeters: json['accuracy_m'] == null ? null : parseDouble(json['accuracy_m']),
      speedKph: json['speed_kph'] == null ? null : parseDouble(json['speed_kph']),
    );
  }
}

