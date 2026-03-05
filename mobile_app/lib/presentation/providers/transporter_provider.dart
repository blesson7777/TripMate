import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/driver_info.dart';
import '../../domain/entities/driver_daily_attendance.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/monthly_report.dart';
import '../../domain/entities/trip.dart';
import '../../domain/entities/vehicle.dart';
import '../../domain/repositories/fleet_repository.dart';

class TransporterProvider extends ChangeNotifier {
  TransporterProvider(this._fleetRepository);

  final FleetRepository _fleetRepository;

  bool _loading = false;
  String? _error;

  List<Vehicle> _vehicles = const [];
  List<DriverInfo> _drivers = const [];
  List<DriverDailyAttendance> _dailyAttendance = const [];
  List<Trip> _trips = const [];
  List<FuelRecord> _fuelRecords = const [];
  MonthlyReport? _monthlyReport;

  bool get loading => _loading;
  String? get error => _error;
  List<Vehicle> get vehicles => _vehicles;
  List<DriverInfo> get drivers => _drivers;
  List<DriverDailyAttendance> get dailyAttendance => _dailyAttendance;
  List<Trip> get trips => _trips;
  List<FuelRecord> get fuelRecords => _fuelRecords;
  MonthlyReport? get monthlyReport => _monthlyReport;

  Future<void> loadDashboardData() async {
    await _execute(() async {
      final results = await Future.wait([
        _fleetRepository.getVehicles(),
        _fleetRepository.getDrivers(),
        _fleetRepository.getTrips(),
        _fleetRepository.getFuelRecords(),
      ]);

      _vehicles = results[0] as List<Vehicle>;
      _drivers = results[1] as List<DriverInfo>;
      _trips = results[2] as List<Trip>;
      _fuelRecords = results[3] as List<FuelRecord>;
    });
  }

  Future<void> loadMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
  }) async {
    await _execute(() async {
      _monthlyReport = await _fleetRepository.getMonthlyReport(
        month: month,
        year: year,
        vehicleId: vehicleId,
      );
    });
  }

  Future<bool> addVehicle({
    required String vehicleNumber,
    required String model,
    String status = 'ACTIVE',
  }) async {
    try {
      await _fleetRepository.addVehicle(
        vehicleNumber: vehicleNumber,
        model: model,
        status: status,
      );
      await loadDashboardData();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      notifyListeners();
      return false;
    } catch (_) {
      _error = 'Unable to add vehicle.';
      notifyListeners();
      return false;
    }
  }

  Future<bool> requestDriverAllocationOtp({
    required String email,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.requestDriverAllocationOtp(email: email);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send OTP.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> verifyDriverAllocationOtp({
    required String email,
    required String otp,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.verifyDriverAllocationOtp(email: email, otp: otp);
      await loadDashboardData();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to verify OTP.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> assignVehicleToDriver({
    required int driverId,
    int? vehicleId,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.assignVehicleToDriver(
        driverId: driverId,
        vehicleId: vehicleId,
      );
      await loadDashboardData();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to assign vehicle.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> loadDailyAttendance({DateTime? date}) async {
    await _execute(() async {
      _dailyAttendance = await _fleetRepository.getDailyDriverAttendance(date: date);
    });
  }

  Future<bool> markDriverAttendance({
    required int driverId,
    required String status,
    DateTime? date,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.markDailyDriverAttendance(
        driverId: driverId,
        status: status,
        date: date,
      );
      _dailyAttendance = await _fleetRepository.getDailyDriverAttendance(date: date);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update attendance mark.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> _execute(Future<void> Function() action) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await action();
    } on ApiException catch (exception) {
      _error = exception.message;
    } catch (_) {
      _error = 'Unable to load data.';
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}
