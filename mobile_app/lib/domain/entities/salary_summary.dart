class DriverSalarySummary {
  const DriverSalarySummary({
    required this.driverId,
    required this.driverName,
    required this.driverPhone,
    required this.month,
    required this.year,
    required this.monthStart,
    required this.monthEnd,
    required this.salaryDueDate,
    required this.canPay,
    required this.totalDaysInMonth,
    required this.futureDays,
    required this.presentDays,
    required this.noDutyDays,
    required this.weeklyOffDays,
    required this.leaveDays,
    required this.clCount,
    required this.paidLeaveDays,
    required this.unpaidLeaveDays,
    required this.absentDays,
    required this.paidDays,
    required this.monthlySalary,
    required this.perDaySalary,
    required this.payableAmount,
    required this.advanceAmount,
    required this.netPayableAmount,
    required this.paymentStatus,
    required this.isPaid,
    this.paidAt,
    this.paidByUsername,
    this.paymentId,
    required this.notes,
  });

  final int driverId;
  final String driverName;
  final String driverPhone;
  final int month;
  final int year;
  final DateTime monthStart;
  final DateTime monthEnd;
  final DateTime salaryDueDate;
  final bool canPay;
  final int totalDaysInMonth;
  final int futureDays;
  final int presentDays;
  final int noDutyDays;
  final int weeklyOffDays;
  final int leaveDays;
  final int clCount;
  final int paidLeaveDays;
  final int unpaidLeaveDays;
  final int absentDays;
  final int paidDays;
  final double monthlySalary;
  final double perDaySalary;
  final double payableAmount;
  final double advanceAmount;
  final double netPayableAmount;
  final String paymentStatus;
  final bool isPaid;
  final DateTime? paidAt;
  final String? paidByUsername;
  final int? paymentId;
  final String notes;
}

class SalaryMonthlySummary {
  const SalaryMonthlySummary({
    required this.month,
    required this.year,
    required this.monthStart,
    required this.monthEnd,
    required this.salaryDueDate,
    required this.totalDrivers,
    required this.paidCount,
    required this.pendingCount,
    required this.totalPayableAmount,
    required this.totalPaidAmount,
    required this.rows,
  });

  final int month;
  final int year;
  final DateTime monthStart;
  final DateTime monthEnd;
  final DateTime salaryDueDate;
  final int totalDrivers;
  final int paidCount;
  final int pendingCount;
  final double totalPayableAmount;
  final double totalPaidAmount;
  final List<DriverSalarySummary> rows;
}
