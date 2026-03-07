class MonthlyReportRow {
  const MonthlyReportRow({
    required this.slNo,
    required this.date,
    required this.vehicleNumber,
    required this.serviceName,
    this.serviceId,
    required this.openingKm,
    required this.closingKm,
    required this.totalRunKm,
    required this.purpose,
    required this.startKm,
    required this.endKm,
    required this.totalKm,
  });

  final int slNo;
  final DateTime date;
  final String vehicleNumber;
  final int? serviceId;
  final String serviceName;
  final int openingKm;
  final int closingKm;
  final int totalRunKm;
  final String purpose;
  final int startKm;
  final int endKm;
  final int totalKm;
}

class MonthlyReport {
  const MonthlyReport({
    required this.month,
    required this.year,
    this.vehicleId,
    this.serviceId,
    this.serviceName,
    required this.totalDays,
    required this.totalKm,
    required this.rows,
  });

  final int month;
  final int year;
  final int? vehicleId;
  final int? serviceId;
  final String? serviceName;
  final int totalDays;
  final int totalKm;
  final List<MonthlyReportRow> rows;
}
