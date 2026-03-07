class Vehicle {
  const Vehicle({
    required this.id,
    required this.vehicleNumber,
    required this.model,
    required this.status,
    this.latestOdometerKm,
    this.latestOdometerSource,
    this.tankCapacityLiters,
    this.fuelAverageMileage,
    this.fuelEstimatedTankCapacityLiters,
    this.fuelEstimatedLeftLiters,
    this.fuelEstimatedLeftPercent,
    this.fuelEstimatedKmLeft,
    this.fuelLastFillDate,
    this.fuelEstimatedDaysLeft,
  });

  final int id;
  final String vehicleNumber;
  final String model;
  final String status;
  final int? latestOdometerKm;
  final String? latestOdometerSource;
  final double? tankCapacityLiters;
  final double? fuelAverageMileage;
  final double? fuelEstimatedTankCapacityLiters;
  final double? fuelEstimatedLeftLiters;
  final double? fuelEstimatedLeftPercent;
  final int? fuelEstimatedKmLeft;
  final DateTime? fuelLastFillDate;
  final double? fuelEstimatedDaysLeft;
}
