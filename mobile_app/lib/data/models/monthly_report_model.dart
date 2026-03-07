import '../../domain/entities/monthly_report.dart';

class MonthlyReportRowModel extends MonthlyReportRow {
  const MonthlyReportRowModel({
    required super.slNo,
    required super.date,
    required super.vehicleNumber,
    super.serviceId,
    required super.serviceName,
    required super.openingKm,
    required super.closingKm,
    required super.totalRunKm,
    required super.purpose,
    required super.startKm,
    required super.endKm,
    required super.totalKm,
  });

  factory MonthlyReportRowModel.fromJson(Map<String, dynamic> json) {
    return MonthlyReportRowModel(
      slNo: _asInt(json['sl_no']) ?? 0,
      date: DateTime.parse((json['date'] ?? '').toString()),
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      serviceId: _asInt(json['service_id']),
      serviceName: (json['service_name'] ?? '').toString(),
      openingKm: _asInt(json['opening_km']) ?? 0,
      closingKm: _asInt(json['closing_km']) ?? 0,
      totalRunKm: _asInt(json['total_run_km']) ?? 0,
      purpose: (json['purpose'] ?? '').toString(),
      startKm: _asInt(json['start_km']) ?? 0,
      endKm: _asInt(json['end_km']) ?? 0,
      totalKm: _asInt(json['total_km']) ?? 0,
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
}

class MonthlyReportModel extends MonthlyReport {
  const MonthlyReportModel({
    required super.month,
    required super.year,
    super.vehicleId,
    super.serviceId,
    super.serviceName,
    required super.totalDays,
    required super.totalKm,
    required super.rows,
  });

  factory MonthlyReportModel.fromJson(Map<String, dynamic> json) {
    final rows = (json['rows'] as List<dynamic>? ?? <dynamic>[])
        .map((item) => MonthlyReportRowModel.fromJson(item as Map<String, dynamic>))
        .toList();

    return MonthlyReportModel(
      month: MonthlyReportRowModel._asInt(json['month']) ?? 0,
      year: MonthlyReportRowModel._asInt(json['year']) ?? 0,
      vehicleId: MonthlyReportRowModel._asInt(json['vehicle_id']),
      serviceId: MonthlyReportRowModel._asInt(json['service_id']),
      serviceName: json['service_name']?.toString(),
      totalDays: MonthlyReportRowModel._asInt(json['total_days']) ?? 0,
      totalKm: MonthlyReportRowModel._asInt(json['total_km']) ?? 0,
      rows: rows,
    );
  }
}
