import '../../domain/entities/attendance_calendar.dart';

class AttendanceCalendarDayModel extends AttendanceCalendarDay {
  const AttendanceCalendarDayModel({
    required super.date,
    required super.status,
    required super.hasAttendance,
    required super.hasMark,
    super.vehicleNumber,
    super.serviceName,
    super.startKm,
    super.endKm,
  });

  factory AttendanceCalendarDayModel.fromJson(Map<String, dynamic> json) {
    return AttendanceCalendarDayModel(
      date: DateTime.parse((json['date'] ?? '').toString()),
      status: (json['status'] ?? '').toString(),
      hasAttendance: json['has_attendance'] == true,
      hasMark: json['has_mark'] == true,
      vehicleNumber: json['vehicle_number']?.toString(),
      serviceName: json['service_name']?.toString(),
      startKm: _asInt(json['start_km']),
      endKm: _asInt(json['end_km']),
    );
  }
}

class AttendanceCalendarTotalsModel extends AttendanceCalendarTotals {
  const AttendanceCalendarTotalsModel({
    required super.presentDays,
    required super.absentDays,
    required super.noDutyDays,
    required super.effectivePresentDays,
  });

  factory AttendanceCalendarTotalsModel.fromJson(Map<String, dynamic> json) {
    return AttendanceCalendarTotalsModel(
      presentDays: _asInt(json['present_days']) ?? 0,
      absentDays: _asInt(json['absent_days']) ?? 0,
      noDutyDays: _asInt(json['no_duty_days']) ?? 0,
      effectivePresentDays: _asInt(json['effective_present_days']) ?? 0,
    );
  }
}

class DriverAttendanceCalendarModel extends DriverAttendanceCalendar {
  const DriverAttendanceCalendarModel({
    required super.driverId,
    required super.driverName,
    required super.month,
    required super.year,
    required super.totals,
    required super.days,
  });

  factory DriverAttendanceCalendarModel.fromJson(Map<String, dynamic> json) {
    final totals =
        json['totals'] as Map<String, dynamic>? ?? const <String, dynamic>{};
    final days = (json['days'] as List<dynamic>? ?? const <dynamic>[])
        .map((item) => AttendanceCalendarDayModel.fromJson(item as Map<String, dynamic>))
        .toList();
    return DriverAttendanceCalendarModel(
      driverId: _asInt(json['driver_id']) ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      month: _asInt(json['month']) ?? 0,
      year: _asInt(json['year']) ?? 0,
      totals: AttendanceCalendarTotalsModel.fromJson(totals),
      days: days,
    );
  }
}

int? _asInt(dynamic value) {
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
