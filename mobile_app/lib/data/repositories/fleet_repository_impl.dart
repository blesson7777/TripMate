import 'dart:io';

import '../../domain/entities/driver_info.dart';
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
    required File meterImage,
    required File billImage,
    DateTime? date,
  }) {
    return _remoteDataSource.addFuelRecord(
      liters: liters,
      amount: amount,
      meterImage: meterImage,
      billImage: billImage,
      date: date,
    );
  }

  @override
  Future<void> addTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required int endKm,
    required String purpose,
  }) {
    return _remoteDataSource.addTrip(
      startLocation: startLocation,
      destination: destination,
      startKm: startKm,
      endKm: endKm,
      purpose: purpose,
    );
  }

  @override
  Future<void> endAttendance({
    required int endKm,
    File? odoEndImage,
  }) {
    return _remoteDataSource.endAttendance(endKm: endKm, odoEndImage: odoEndImage);
  }

  @override
  Future<List<DriverInfo>> getDrivers() {
    return _remoteDataSource.getDrivers();
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
