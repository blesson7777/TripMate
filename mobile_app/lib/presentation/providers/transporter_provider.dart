import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/driver_info.dart';
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
  List<Trip> _trips = const [];
  List<FuelRecord> _fuelRecords = const [];
  MonthlyReport? _monthlyReport;

  bool get loading => _loading;
  String? get error => _error;
  List<Vehicle> get vehicles => _vehicles;
  List<DriverInfo> get drivers => _drivers;
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
