class AttendanceCalendarDay {
  const AttendanceCalendarDay({
    required this.date,
    required this.status,
    required this.hasAttendance,
    required this.hasMark,
    this.vehicleNumber,
    this.serviceName,
    this.startKm,
    this.endKm,
  });

  final DateTime date;
  final String status;
  final bool hasAttendance;
  final bool hasMark;
  final String? vehicleNumber;
  final String? serviceName;
  final int? startKm;
  final int? endKm;
}

class AttendanceCalendarTotals {
  const AttendanceCalendarTotals({
    required this.presentDays,
    required this.absentDays,
    required this.noDutyDays,
    required this.effectivePresentDays,
  });

  final int presentDays;
  final int absentDays;
  final int noDutyDays;
  final int effectivePresentDays;
}

class DriverAttendanceCalendar {
  const DriverAttendanceCalendar({
    required this.driverId,
    required this.driverName,
    required this.month,
    required this.year,
    required this.totals,
    required this.days,
  });

  final int driverId;
  final String driverName;
  final int month;
  final int year;
  final AttendanceCalendarTotals totals;
  final List<AttendanceCalendarDay> days;
}
