class VehicleFuelMonthlyRow {
  const VehicleFuelMonthlyRow({
    required this.vehicleId,
    required this.vehicleNumber,
    required this.fuelFillCount,
    required this.totalLiters,
    required this.totalAmount,
    required this.totalKm,
    required this.averageMileage,
  });

  final int vehicleId;
  final String vehicleNumber;
  final int fuelFillCount;
  final double totalLiters;
  final double totalAmount;
  final int totalKm;
  final double averageMileage;
}

class FuelMonthlySummary {
  const FuelMonthlySummary({
    required this.month,
    required this.year,
    required this.totalVehiclesFilled,
    required this.totalFuelFills,
    required this.totalLiters,
    required this.totalAmount,
    required this.overallAverageMileage,
    required this.rows,
  });

  final int month;
  final int year;
  final int totalVehiclesFilled;
  final int totalFuelFills;
  final double totalLiters;
  final double totalAmount;
  final double overallAverageMileage;
  final List<VehicleFuelMonthlyRow> rows;
}
