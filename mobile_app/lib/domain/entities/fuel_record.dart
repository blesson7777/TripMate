class FuelRecord {
  const FuelRecord({
    required this.id,
    required this.entryType,
    required this.vehicleNumber,
    required this.driverName,
    required this.date,
    this.liters = 0,
    this.amount = 0,
    this.odometerKm,
    this.meterImageUrl = '',
    this.billImageUrl = '',
    this.fuelFilled = 0,
    this.piuReading,
    this.dgHmr,
    this.openingStock,
    this.startKm,
    this.endKm,
    this.runKm = 0,
    this.fillDate,
    this.indusSiteId = '',
    this.siteName = '',
    this.purpose = '',
    this.logbookPhotoUrl = '',
  });

  final int id;
  final String entryType;
  final String vehicleNumber;
  final String driverName;
  final DateTime date;

  // Vehicle fuel fields.
  final double liters;
  final double amount;
  final int? odometerKm;
  final String meterImageUrl;
  final String billImageUrl;

  // Tower diesel fields.
  final double fuelFilled;
  final double? piuReading;
  final double? dgHmr;
  final double? openingStock;
  final int? startKm;
  final int? endKm;
  final int runKm;
  final DateTime? fillDate;
  final String indusSiteId;
  final String siteName;
  final String purpose;
  final String logbookPhotoUrl;

  bool get isTowerDiesel => entryType == 'TOWER_DIESEL';
  bool get isVehicleFilling => entryType == 'VEHICLE_FILLING';
  DateTime get effectiveDate => fillDate ?? date;
}
