import '../../domain/entities/monthly_report.dart';

class MonthlyReportRowModel extends MonthlyReportRow {
  const MonthlyReportRowModel({
    required super.date,
    required super.startKm,
    required super.endKm,
    required super.totalKm,
  });

  factory MonthlyReportRowModel.fromJson(Map<String, dynamic> json) {
    return MonthlyReportRowModel(
      date: DateTime.parse((json['date'] ?? '').toString()),
      startKm: (json['start_km'] ?? 0) as int,
      endKm: (json['end_km'] ?? 0) as int,
      totalKm: (json['total_km'] ?? 0) as int,
    );
  }
}

class MonthlyReportModel extends MonthlyReport {
  const MonthlyReportModel({
    required super.month,
    required super.year,
    required super.totalDays,
    required super.totalKm,
    required super.rows,
  });

  factory MonthlyReportModel.fromJson(Map<String, dynamic> json) {
    final rows = (json['rows'] as List<dynamic>? ?? <dynamic>[])
        .map((item) => MonthlyReportRowModel.fromJson(item as Map<String, dynamic>))
        .toList();

    return MonthlyReportModel(
      month: (json['month'] ?? 0) as int,
      year: (json['year'] ?? 0) as int,
      totalDays: (json['total_days'] ?? 0) as int,
      totalKm: (json['total_km'] ?? 0) as int,
      rows: rows,
    );
  }
}
