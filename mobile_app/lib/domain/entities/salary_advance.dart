class SalaryAdvance {
  const SalaryAdvance({
    required this.id,
    required this.driverId,
    required this.driverName,
    required this.amount,
    required this.advanceDate,
    required this.notes,
    this.settledPaymentId,
    this.recordedByUsername,
    required this.createdAt,
    required this.updatedAt,
  });

  final int id;
  final int driverId;
  final String driverName;
  final double amount;
  final DateTime advanceDate;
  final String notes;
  final int? settledPaymentId;
  final String? recordedByUsername;
  final DateTime createdAt;
  final DateTime updatedAt;
}
