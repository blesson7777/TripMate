import '../../domain/entities/salary_summary.dart';

class DriverSalarySummaryModel extends DriverSalarySummary {
  const DriverSalarySummaryModel({
    required super.driverId,
    required super.driverName,
    required super.driverPhone,
    required super.month,
    required super.year,
    required super.monthStart,
    required super.monthEnd,
    required super.salaryDueDate,
    required super.canPay,
    required super.totalDaysInMonth,
    required super.futureDays,
    required super.presentDays,
    required super.noDutyDays,
    required super.weeklyOffDays,
    required super.leaveDays,
    required super.clCount,
    required super.paidLeaveDays,
    required super.unpaidLeaveDays,
    required super.absentDays,
    required super.paidDays,
    required super.monthlySalary,
    required super.perDaySalary,
    required super.payableAmount,
    required super.advanceAmount,
    required super.netPayableAmount,
    required super.paymentStatus,
    required super.isPaid,
    super.paidAt,
    super.paidByUsername,
    super.paymentId,
    required super.notes,
  });

  factory DriverSalarySummaryModel.fromJson(Map<String, dynamic> json) {
    return DriverSalarySummaryModel(
      driverId: _asInt(json['driver_id']) ?? 0,
      driverName: (json['driver_name'] ?? '').toString(),
      driverPhone: (json['driver_phone'] ?? '').toString(),
      month: _asInt(json['month']) ?? 0,
      year: _asInt(json['year']) ?? 0,
      monthStart: DateTime.parse((json['month_start'] ?? '').toString()),
      monthEnd: DateTime.parse((json['month_end'] ?? '').toString()),
      salaryDueDate: DateTime.parse((json['salary_due_date'] ?? '').toString()),
      canPay: json['can_pay'] == true,
      totalDaysInMonth: _asInt(json['total_days_in_month']) ?? 0,
      futureDays: _asInt(json['future_days']) ?? 0,
      presentDays: _asInt(json['present_days']) ?? 0,
      noDutyDays: _asInt(json['no_duty_days']) ?? 0,
      weeklyOffDays: _asInt(json['weekly_off_days']) ?? 0,
      leaveDays: _asInt(json['leave_days']) ?? 0,
      clCount: _asInt(json['cl_count']) ?? 0,
      paidLeaveDays: _asInt(json['paid_leave_days']) ?? 0,
      unpaidLeaveDays: _asInt(json['unpaid_leave_days']) ?? 0,
      absentDays: _asInt(json['absent_days']) ?? 0,
      paidDays: _asInt(json['paid_days']) ?? 0,
      monthlySalary: _asDouble(json['monthly_salary']),
      perDaySalary: _asDouble(json['per_day_salary']),
      payableAmount: _asDouble(json['payable_amount']),
      advanceAmount: _asDouble(json['advance_amount']),
      netPayableAmount: _asDouble(json['net_payable_amount']),
      paymentStatus: (json['payment_status'] ?? '').toString(),
      isPaid: json['is_paid'] == true,
      paidAt: json['paid_at'] == null
          ? null
          : DateTime.tryParse(json['paid_at'].toString()),
      paidByUsername: json['paid_by_username']?.toString(),
      paymentId: _asInt(json['payment_id']),
      notes: (json['notes'] ?? '').toString(),
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

class SalaryMonthlySummaryModel extends SalaryMonthlySummary {
  const SalaryMonthlySummaryModel({
    required super.month,
    required super.year,
    required super.monthStart,
    required super.monthEnd,
    required super.salaryDueDate,
    required super.totalDrivers,
    required super.paidCount,
    required super.pendingCount,
    required super.totalPayableAmount,
    required super.totalPaidAmount,
    required super.rows,
  });

  factory SalaryMonthlySummaryModel.fromJson(Map<String, dynamic> json) {
    final rows = (json['rows'] as List<dynamic>? ?? const [])
        .map((item) => DriverSalarySummaryModel.fromJson(item as Map<String, dynamic>))
        .toList();
    return SalaryMonthlySummaryModel(
      month: DriverSalarySummaryModel._asInt(json['month']) ?? 0,
      year: DriverSalarySummaryModel._asInt(json['year']) ?? 0,
      monthStart: DateTime.parse((json['month_start'] ?? '').toString()),
      monthEnd: DateTime.parse((json['month_end'] ?? '').toString()),
      salaryDueDate: DateTime.parse((json['salary_due_date'] ?? '').toString()),
      totalDrivers: DriverSalarySummaryModel._asInt(json['total_drivers']) ?? 0,
      paidCount: DriverSalarySummaryModel._asInt(json['paid_count']) ?? 0,
      pendingCount: DriverSalarySummaryModel._asInt(json['pending_count']) ?? 0,
      totalPayableAmount: DriverSalarySummaryModel._asDouble(json['total_payable_amount']),
      totalPaidAmount: DriverSalarySummaryModel._asDouble(json['total_paid_amount']),
      rows: rows,
    );
  }
}
