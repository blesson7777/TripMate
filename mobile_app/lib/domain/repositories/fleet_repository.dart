import 'dart:io';

import '../entities/driver_info.dart';
import '../entities/driver_daily_attendance.dart';
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
    required File odoEndImage,
    double? latitude,
    double? longitude,
  });

  Future<void> startTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required String purpose,
    required File startOdoImage,
  });

  Future<void> closeTrip({
    required int tripId,
    required int endKm,
    required File endOdoImage,
  });

  Future<void> addFuelRecord({
    required double liters,
    required double amount,
    required int odometerKm,
    required File meterImage,
    required File billImage,
    DateTime? date,
  });

  Future<List<Vehicle>> getVehicles();

  Future<List<DriverInfo>> getDrivers();

  Future<void> addVehicle({
    required String vehicleNumber,
    required String model,
    String status,
  });

  Future<String?> requestDriverAllocationOtp({
    required String email,
  });

  Future<void> verifyDriverAllocationOtp({
    required String email,
    required String otp,
  });

  Future<void> assignVehicleToDriver({
    required int driverId,
    int? vehicleId,
  });

  Future<List<DriverDailyAttendance>> getDailyDriverAttendance({
    DateTime? date,
  });

  Future<void> markDailyDriverAttendance({
    required int driverId,
    required String status,
    DateTime? date,
  });

  Future<List<Trip>> getTrips();

  Future<List<FuelRecord>> getFuelRecords();

  Future<MonthlyReport> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
  });
}
