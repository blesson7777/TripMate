class FuelRecord {
  const FuelRecord({
    required this.id,
    required this.liters,
    required this.amount,
    required this.date,
    required this.vehicleNumber,
    required this.driverName,
  });

  final int id;
  final double liters;
  final double amount;
  final DateTime date;
  final String vehicleNumber;
  final String driverName;
}
