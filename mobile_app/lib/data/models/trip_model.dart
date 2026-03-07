import '../../domain/entities/trip.dart';

class TripModel extends Trip {
  const TripModel({
    required super.id,
    super.attendanceId,
    super.attendanceDate,
    super.attendanceStatus,
    super.attendanceServiceId,
    super.attendanceServiceName,
    super.attendanceServicePurpose,
    super.attendanceStartedAt,
    super.attendanceEndedAt,
    super.attendanceStartKm,
    super.attendanceEndKm,
    super.attendanceLatitude,
    super.attendanceLongitude,
    super.openingOdoImage,
    super.closingOdoImage,
    super.driverName,
    super.vehicleNumber,
    super.tripStatus,
    super.isDayTrip,
    super.tripStartedAt,
    super.tripEndedAt,
    super.isLive,
    required super.startLocation,
    required super.destination,
    required super.startKm,
    required super.endKm,
    required super.totalKm,
    required super.createdAt,
    super.purpose,
  });

  factory TripModel.fromJson(Map<String, dynamic> json) {
    return TripModel(
      id: _asInt(json['id']) ?? 0,
      attendanceId: _asInt(json['attendance']),
      attendanceDate: _asDateFromDateOnly(json['attendance_date']),
      attendanceStatus: json['attendance_status']?.toString(),
      attendanceServiceId: _asInt(json['attendance_service_id']),
      attendanceServiceName: json['attendance_service_name']?.toString(),
      attendanceServicePurpose: json['attendance_service_purpose']?.toString(),
      attendanceStartedAt: _asDateTime(json['attendance_started_at']),
      attendanceEndedAt: _asDateTime(json['attendance_ended_at']),
      attendanceStartKm: _asInt(json['attendance_start_km']),
      attendanceEndKm: _asInt(json['attendance_end_km']),
      attendanceLatitude: _asDouble(json['attendance_latitude']),
      attendanceLongitude: _asDouble(json['attendance_longitude']),
      openingOdoImage: json['opening_odo_image']?.toString(),
      closingOdoImage: json['closing_odo_image']?.toString(),
      driverName: json['driver_name']?.toString(),
      vehicleNumber: json['vehicle_number']?.toString(),
      tripStatus: json['trip_status']?.toString(),
      isDayTrip: json['is_day_trip'] == true,
      tripStartedAt: _asDateTime(json['started_at']),
      tripEndedAt: _asDateTime(json['ended_at']),
      isLive: json['is_live'] == true,
      startLocation: (json['start_location'] ?? '').toString(),
      destination: (json['destination'] ?? '').toString(),
      startKm: _asInt(json['start_km']) ?? 0,
      endKm: _asInt(json['end_km']) ?? (_asInt(json['start_km']) ?? 0),
      totalKm: _asInt(json['total_km']) ?? 0,
      createdAt: _asDateTime(json['created_at']) ?? DateTime.now(),
      purpose: json['purpose']?.toString(),
    );
  }

  static int? _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    if (value is String) {
      return int.tryParse(value);
    }
    return null;
  }

  static double? _asDouble(dynamic value) {
    if (value is double) {
      return value;
    }
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
  }

  static DateTime? _asDateTime(dynamic value) {
    if (value == null) {
      return null;
    }
    final raw = value.toString();
    if (raw.isEmpty) {
      return null;
    }
    return DateTime.tryParse(raw);
  }

  static DateTime? _asDateFromDateOnly(dynamic value) {
    if (value == null) {
      return null;
    }
    final raw = value.toString();
    if (raw.isEmpty) {
      return null;
    }
    return DateTime.tryParse('${raw}T00:00:00');
  }
}
