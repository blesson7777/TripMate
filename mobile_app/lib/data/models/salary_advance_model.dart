import '../../domain/entities/salary_advance.dart';

class SalaryAdvanceModel extends SalaryAdvance {
  const SalaryAdvanceModel({
    required super.id,
    required super.driverId,
    required super.driverName,
    required super.amount,
    required super.advanceDate,
    required super.notes,
    super.settledPaymentId,
    super.recordedByUsername,
    required super.createdAt,
    required super.updatedAt,
  });

  factory SalaryAdvanceModel.fromJson(Map<String, dynamic> json) {
    return SalaryAdvanceModel(
      id: _asInt(json['id']) ?? 0,
      driverId: _asInt(json['driver']) ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      amount: _asDouble(json['amount']),
      advanceDate: DateTime.parse((json['advance_date'] ?? '').toString()),
      notes: (json['notes'] ?? '').toString(),
      settledPaymentId: _asInt(json['settled_payment']),
      recordedByUsername: json['recorded_by_username']?.toString(),
      createdAt: DateTime.parse((json['created_at'] ?? '').toString()),
      updatedAt: DateTime.parse((json['updated_at'] ?? '').toString()),
    );
  }

  static int? _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  static double _asDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? 0;
  }
}
