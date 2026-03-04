class MonthlyReportRow {
  const MonthlyReportRow({
    required this.date,
    required this.startKm,
    required this.endKm,
    required this.totalKm,
  });

  final DateTime date;
  final int startKm;
  final int endKm;
  final int totalKm;
}

class MonthlyReport {
  const MonthlyReport({
    required this.month,
    required this.year,
    required this.totalDays,
    required this.totalKm,
    required this.rows,
  });

  final int month;
  final int year;
  final int totalDays;
  final int totalKm;
  final List<MonthlyReportRow> rows;
}
