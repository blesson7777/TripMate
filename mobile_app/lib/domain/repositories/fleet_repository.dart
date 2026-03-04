import 'dart:io';

import '../entities/driver_info.dart';
import '../entities/fuel_record.dart';
import '../entities/monthly_report.dart';
import '../entities/trip.dart';
import '../entities/vehicle.dart';

abstract class FleetRepository {
  Future<void> startAttendance({
    int? vehicleId,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  });

  Future<void> endAttendance({
    required int endKm,
    File? odoEndImage,
  });

  Future<void> addTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required int endKm,
    required String purpose,
  });

  Future<void> addFuelRecord({
    required double liters,
    required double amount,
    required File meterImage,
    required File billImage,
    DateTime? date,
  });

  Future<List<Vehicle>> getVehicles();

  Future<List<DriverInfo>> getDrivers();

  Future<List<Trip>> getTrips();

  Future<List<FuelRecord>> getFuelRecords();

  Future<MonthlyReport> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
  });
}
