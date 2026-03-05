import 'dart:io';

import '../../domain/entities/driver_info.dart';
import '../../domain/entities/driver_daily_attendance.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/monthly_report.dart';
import '../../domain/entities/trip.dart';
import '../../domain/entities/vehicle.dart';
import '../../domain/repositories/fleet_repository.dart';
import '../datasources/fleet_remote_data_source.dart';

class FleetRepositoryImpl implements FleetRepository {
  FleetRepositoryImpl(this._remoteDataSource);

  final FleetRemoteDataSource _remoteDataSource;

  @override
  Future<void> addFuelRecord({
    required double liters,
    required double amount,
    required int odometerKm,
    required File meterImage,
    required File billImage,
    DateTime? date,
  }) {
    return _remoteDataSource.addFuelRecord(
      liters: liters,
      amount: amount,
      odometerKm: odometerKm,
      meterImage: meterImage,
      billImage: billImage,
      date: date,
    );
  }

  @override
  Future<void> startTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required String purpose,
    required File startOdoImage,
  }) {
    return _remoteDataSource.startTrip(
      startLocation: startLocation,
      destination: destination,
      startKm: startKm,
      purpose: purpose,
      startOdoImage: startOdoImage,
    );
  }

  @override
  Future<void> closeTrip({
    required int tripId,
    required int endKm,
    required File endOdoImage,
  }) {
    return _remoteDataSource.closeTrip(
      tripId: tripId,
      endKm: endKm,
      endOdoImage: endOdoImage,
    );
  }

  @override
  Future<void> endAttendance({
    required int endKm,
    required File odoEndImage,
    double? latitude,
    double? longitude,
  }) {
    return _remoteDataSource.endAttendance(
      endKm: endKm,
      odoEndImage: odoEndImage,
      latitude: latitude,
      longitude: longitude,
    );
  }

  @override
  Future<List<DriverInfo>> getDrivers() {
    return _remoteDataSource.getDrivers();
  }

  @override
  Future<void> addVehicle({
    required String vehicleNumber,
    required String model,
    String status = 'ACTIVE',
  }) {
    return _remoteDataSource.addVehicle(
      vehicleNumber: vehicleNumber,
      model: model,
      status: status,
    );
  }

  @override
  Future<String?> requestDriverAllocationOtp({required String email}) {
    return _remoteDataSource.requestDriverAllocationOtp(email: email);
  }

  @override
  Future<void> verifyDriverAllocationOtp({
    required String email,
    required String otp,
  }) {
    return _remoteDataSource.verifyDriverAllocationOtp(
      email: email,
      otp: otp,
    );
  }

  @override
  Future<void> assignVehicleToDriver({
    required int driverId,
    int? vehicleId,
  }) {
    return _remoteDataSource.assignVehicleToDriver(
      driverId: driverId,
      vehicleId: vehicleId,
    );
  }

  @override
  Future<List<DriverDailyAttendance>> getDailyDriverAttendance({
    DateTime? date,
  }) {
    return _remoteDataSource.getDailyDriverAttendance(date: date);
  }

  @override
  Future<void> markDailyDriverAttendance({
    required int driverId,
    required String status,
    DateTime? date,
  }) {
    return _remoteDataSource.markDailyDriverAttendance(
      driverId: driverId,
      status: status,
      date: date,
    );
  }

  @override
  Future<List<FuelRecord>> getFuelRecords() {
    return _remoteDataSource.getFuelRecords();
  }

  @override
  Future<MonthlyReport> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
  }) {
    return _remoteDataSource.getMonthlyReport(
      month: month,
      year: year,
      vehicleId: vehicleId,
    );
  }

  @override
  Future<List<Trip>> getTrips() {
    return _remoteDataSource.getTrips();
  }

  @override
  Future<List<Vehicle>> getVehicles() {
    return _remoteDataSource.getVehicles();
  }

  @override
  Future<void> startAttendance({
    int? vehicleId,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) {
    return _remoteDataSource.startAttendance(
      vehicleId: vehicleId,
      startKm: startKm,
      odoStartImage: odoStartImage,
      latitude: latitude,
      longitude: longitude,
    );
  }
}
