import 'dart:io';

import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/trip.dart';
import '../../domain/entities/vehicle.dart';
import '../../domain/repositories/fleet_repository.dart';

class DriverProvider extends ChangeNotifier {
  DriverProvider(this._fleetRepository);

  final FleetRepository _fleetRepository;

  bool _loading = false;
  String? _error;
  List<Vehicle> _vehicles = const [];
  List<Trip> _trips = const [];
  List<FuelRecord> _fuelRecords = const [];

  bool get loading => _loading;
  String? get error => _error;
  List<Vehicle> get vehicles => _vehicles;
  List<Trip> get trips => _trips;
  List<FuelRecord> get fuelRecords => _fuelRecords;

  Future<bool> startDay({
    int? vehicleId,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) async {
    return _execute(() {
      return _fleetRepository.startAttendance(
        vehicleId: vehicleId,
        startKm: startKm,
        odoStartImage: odoStartImage,
        latitude: latitude,
        longitude: longitude,
      );
    });
  }

  Future<bool> startTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required String purpose,
    required File startOdoImage,
  }) async {
    final result = await _execute(() {
      return _fleetRepository.startTrip(
        startLocation: startLocation,
        destination: destination,
        startKm: startKm,
        purpose: purpose,
        startOdoImage: startOdoImage,
      );
    });

    if (result) {
      await loadTrips();
    }

    return result;
  }

  Future<bool> addFuelRecord({
    required double liters,
    required double amount,
    required int odometerKm,
    required File meterImage,
    required File billImage,
  }) {
    return _execute(() {
      return _fleetRepository.addFuelRecord(
        liters: liters,
        amount: amount,
        odometerKm: odometerKm,
        meterImage: meterImage,
        billImage: billImage,
      );
    });
  }

  Future<bool> endDay({
    required int endKm,
    required File odoEndImage,
    double? latitude,
    double? longitude,
  }) {
    return _execute(() {
      return _fleetRepository.endAttendance(
        endKm: endKm,
        odoEndImage: odoEndImage,
        latitude: latitude,
        longitude: longitude,
      );
    });
  }

  Future<bool> closeTrip({
    required int tripId,
    required int endKm,
    required File endOdoImage,
  }) async {
    final result = await _execute(() {
      return _fleetRepository.closeTrip(
        tripId: tripId,
        endKm: endKm,
        endOdoImage: endOdoImage,
      );
    });

    if (result) {
      await loadTrips();
    }
    return result;
  }

  Future<void> loadTrips() async {
    await _execute(() async {
      _trips = await _fleetRepository.getTrips();
    }, notifyOnSuccess: true);
  }

  Future<void> loadVehicles() async {
    await _execute(() async {
      _vehicles = await _fleetRepository.getVehicles();
    }, notifyOnSuccess: true);
  }

  Future<void> loadFuelRecords() async {
    await _execute(() async {
      _fuelRecords = await _fleetRepository.getFuelRecords();
    }, notifyOnSuccess: true);
  }

  Future<bool> _execute(
    Future<void> Function() action, {
    bool notifyOnSuccess = false,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await action();
      if (notifyOnSuccess) {
        notifyListeners();
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      notifyListeners();
      return false;
    } catch (_) {
      _error = 'Operation failed. Please retry.';
      notifyListeners();
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}
