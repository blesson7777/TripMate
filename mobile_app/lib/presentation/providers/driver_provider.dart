import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../../core/services/driver_diesel_session_service.dart';
import '../../core/services/offline_tower_diesel_queue_service.dart';
import '../../core/network/api_client.dart';
import '../../domain/entities/app_notification.dart';
import '../../domain/entities/diesel_daily_route_plan.dart';
import '../../domain/entities/diesel_route_suggestion.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/service_item.dart';
import '../../domain/entities/tower_site_suggestion.dart';
import '../../domain/entities/trip.dart';
import '../../domain/entities/vehicle.dart';
import '../../domain/repositories/fleet_repository.dart';

class DriverProvider extends ChangeNotifier {
  DriverProvider(this._fleetRepository);

  final FleetRepository _fleetRepository;
  static const Duration _tripsCacheTtl = Duration(seconds: 20);
  static const Duration _notificationCacheTtl = Duration(seconds: 20);

  bool _loading = false;
  String? _error;
  DateTime? _tripsLastLoadedAt;
  DateTime? _notificationsLastLoadedAt;
  List<Vehicle> _vehicles = const [];
  List<ServiceItem> _services = const [];
  List<Trip> _trips = const [];
  List<FuelRecord> _fuelRecords = const [];
  List<FuelRecord> _towerDieselRecords = const [];
  DieselDailyRoutePlan? _dailyRoutePlan;
  List<TowerSiteSuggestion> _nearbyTowerSites = const [];
  List<TowerSiteSuggestion> _towerSites = const [];
  List<AppNotification> _serverNotifications = const [];
  int _unreadServerNotificationCount = 0;

  bool get loading => _loading;
  String? get error => _error;
  List<Vehicle> get vehicles => _vehicles;
  List<ServiceItem> get services => _services;
  List<Trip> get trips => _trips;
  List<FuelRecord> get fuelRecords => _fuelRecords;
  List<FuelRecord> get towerDieselRecords => _towerDieselRecords;
  DieselDailyRoutePlan? get dailyRoutePlan => _dailyRoutePlan;
  List<TowerSiteSuggestion> get nearbyTowerSites => _nearbyTowerSites;
  List<TowerSiteSuggestion> get towerSites => _towerSites;
  List<AppNotification> get serverNotifications => _serverNotifications;
  int get unreadServerNotificationCount => _unreadServerNotificationCount;

  bool _containsDieselKeyword(String? value) {
    final normalized = (value ?? '').trim().toLowerCase();
    if (normalized.isEmpty) {
      return false;
    }
    return normalized.contains('diesel');
  }

  bool _hasActiveDieselDayTrip(List<Trip> trips) {
    return trips.any((trip) {
      final isOpenDayTrip =
          trip.isDayTrip && (trip.tripStatus ?? '').toUpperCase() == 'OPEN';
      if (!isOpenDayTrip) {
        return false;
      }
      return _containsDieselKeyword(trip.attendanceServiceName) ||
          _containsDieselKeyword(trip.attendanceServicePurpose) ||
          _containsDieselKeyword(trip.purpose);
    });
  }

  Future<void> _syncDieselTripStateFromTrips() {
    return DriverDieselSessionService.instance
        .setActiveDieselTripStarted(_hasActiveDieselDayTrip(_trips));
  }

  Future<bool> startDay({
    int? vehicleId,
    int? serviceId,
    String? servicePurpose,
    String? destination,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) async {
    final result = await _execute(() {
      return _fleetRepository.startAttendance(
        vehicleId: vehicleId,
        serviceId: serviceId,
        servicePurpose: servicePurpose,
        destination: destination,
        startKm: startKm,
        odoStartImage: odoStartImage,
        latitude: latitude,
        longitude: longitude,
      );
    });
    if (result) {
      await loadTrips(force: true, silent: true);
    }
    return result;
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
      await loadTrips(force: true);
    }

    return result;
  }

  Future<bool> addFuelRecord({
    required double liters,
    required double amount,
    required int odometerKm,
    required File meterImage,
    required File billImage,
    int? vehicleId,
    DateTime? date,
  }) {
    return _execute(() {
      return _fleetRepository.addFuelRecord(
        liters: liters,
        amount: amount,
        odometerKm: odometerKm,
        meterImage: meterImage,
        billImage: billImage,
        vehicleId: vehicleId,
        date: date,
      );
    });
  }

  Future<bool> addTowerDieselRecord({
    required String indusSiteId,
    required String siteName,
    required double fuelFilled,
    double? piuReading,
    double? dgHmr,
    double? openingStock,
    bool confirmSiteNameUpdate = false,
    int? startKm,
    int? endKm,
    double? towerLatitude,
    double? towerLongitude,
    required String purpose,
    DateTime? fillDate,
    required File logbookPhoto,
  }) async {
    final result = await _execute(() {
      return _fleetRepository.addTowerDieselRecord(
        indusSiteId: indusSiteId,
        siteName: siteName,
        fuelFilled: fuelFilled,
        piuReading: piuReading,
        dgHmr: dgHmr,
        openingStock: openingStock,
        confirmSiteNameUpdate: confirmSiteNameUpdate,
        startKm: startKm,
        endKm: endKm,
        towerLatitude: towerLatitude,
        towerLongitude: towerLongitude,
        purpose: purpose,
        fillDate: fillDate,
        logbookPhoto: logbookPhoto,
      );
    });
    if (result) {
      unawaited(
        loadTowerDieselRecords(
          month: DateTime.now().month,
          year: DateTime.now().year,
          silent: true,
        ),
      );
    }
    return result;
  }

  Future<bool> queueTowerDieselRecord({
    required String indusSiteId,
    required String siteName,
    required double fuelFilled,
    double? piuReading,
    double? dgHmr,
    double? openingStock,
    bool confirmSiteNameUpdate = false,
    int? startKm,
    int? endKm,
    double? towerLatitude,
    double? towerLongitude,
    required String purpose,
    DateTime? fillDate,
    required File logbookPhoto,
  }) async {
    try {
      _error = null;
      notifyListeners();
      await OfflineTowerDieselQueueService.instance.enqueue(
        indusSiteId: indusSiteId,
        siteName: siteName,
        fuelFilled: fuelFilled,
        piuReading: piuReading,
        dgHmr: dgHmr,
        openingStock: openingStock,
        confirmSiteNameUpdate: confirmSiteNameUpdate,
        startKm: startKm,
        endKm: endKm,
        towerLatitude: towerLatitude,
        towerLongitude: towerLongitude,
        purpose: purpose,
        fillDate: fillDate,
        logbookPhoto: logbookPhoto,
      );
      return true;
    } catch (_) {
      _error = 'Unable to save entry offline right now.';
      notifyListeners();
      return false;
    }
  }

  Future<OfflineTowerDieselSyncResult> syncQueuedTowerDieselRecords({
    bool silent = true,
  }) async {
    if (!silent) {
      _loading = true;
      _error = null;
      notifyListeners();
    }
    try {
      final result = await OfflineTowerDieselQueueService.instance.sync(
        submit: (entry) {
          return _fleetRepository.addTowerDieselRecord(
            indusSiteId: entry.indusSiteId,
            siteName: entry.siteName,
            fuelFilled: entry.fuelFilled,
            piuReading: entry.piuReading,
            dgHmr: entry.dgHmr,
            openingStock: entry.openingStock,
            confirmSiteNameUpdate: entry.confirmSiteNameUpdate,
            startKm: entry.startKm,
            endKm: entry.endKm,
            towerLatitude: entry.towerLatitude,
            towerLongitude: entry.towerLongitude,
            purpose: entry.purpose,
            fillDate: entry.fillDate,
            logbookPhoto: File(entry.logbookPhotoPath),
          );
        },
      );
      if (result.syncedCount > 0) {
        await loadTowerDieselRecords(
          month: DateTime.now().month,
          year: DateTime.now().year,
          silent: true,
        );
      }
      return result;
    } finally {
      if (!silent) {
        _loading = false;
        notifyListeners();
      }
    }
  }

  Future<bool> endDay({
    required int endKm,
    required File odoEndImage,
    bool confirmLargeRun = false,
    double? latitude,
    double? longitude,
  }) {
    return _execute(() async {
      return _fleetRepository.endAttendance(
        endKm: endKm,
        odoEndImage: odoEndImage,
        confirmLargeRun: confirmLargeRun,
        latitude: latitude,
        longitude: longitude,
      );
    }).then((result) async {
      if (result) {
        await loadTrips(force: true, silent: true);
      }
      return result;
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
      await loadTrips(force: true);
    }
    return result;
  }

  Future<void> loadTrips({
    bool force = false,
    bool silent = false,
  }) async {
    if (!force && _tripsLastLoadedAt != null) {
      final age = DateTime.now().difference(_tripsLastLoadedAt!);
      if (age <= _tripsCacheTtl) {
        return;
      }
    }
    await _execute(() async {
      _trips = await _fleetRepository.getTrips();
      _tripsLastLoadedAt = DateTime.now();
      await _syncDieselTripStateFromTrips();
    }, notifyOnSuccess: true, silent: silent);
  }

  Future<void> loadVehicles() async {
    await _execute(() async {
      _vehicles = await _fleetRepository.getVehicles();
    }, notifyOnSuccess: true);
  }

  Future<void> loadServices() async {
    await _execute(() async {
      _services = await _fleetRepository.getServices();
    }, notifyOnSuccess: true);
  }

  Future<void> loadFuelRecords() async {
    await _execute(() async {
      _fuelRecords = await _fleetRepository.getFuelRecords();
    }, notifyOnSuccess: true);
  }

  Future<void> loadTowerDieselRecords({
    int? month,
    int? year,
    bool silent = false,
  }) async {
    await _execute(() async {
      _towerDieselRecords = await _fleetRepository.getTowerDieselRecords(
        month: month,
        year: year,
      );
    }, notifyOnSuccess: true, silent: silent);
  }

  Future<void> loadNearbyTowerSites({
    required double latitude,
    required double longitude,
    double radiusMeters = 100,
  }) async {
    await _execute(() async {
      _nearbyTowerSites = await _fleetRepository.getNearbyTowerSites(
        latitude: latitude,
        longitude: longitude,
        radiusMeters: radiusMeters,
      );
    }, notifyOnSuccess: true);
  }

  Future<TowerSiteSuggestion?> findTowerSiteById({
    required String indusSiteId,
  }) async {
    try {
      return await _fleetRepository.getTowerSiteById(indusSiteId: indusSiteId);
    } on ApiException catch (exception) {
      _error = exception.message;
      notifyListeners();
      return null;
    } catch (_) {
      _error = 'Unable to fetch tower details.';
      notifyListeners();
      return null;
    }
  }

  Future<DieselRouteSuggestion?> suggestTowerRoute({
    required double startLatitude,
    required double startLongitude,
    required List<DieselDailyRouteStop> stops,
    bool returnToStart = false,
  }) async {
    try {
      _error = null;
      notifyListeners();
      return await _fleetRepository.optimizeTowerRoute(
        startLatitude: startLatitude,
        startLongitude: startLongitude,
        stops: stops,
        returnToStart: returnToStart,
      );
    } on ApiException catch (exception) {
      _error = exception.message;
      notifyListeners();
      return null;
    } catch (_) {
      _error = 'Unable to suggest a better route right now.';
      notifyListeners();
      return null;
    }
  }

  Future<void> loadTowerSites({
    String? query,
    int limit = 250,
    double? latitude,
    double? longitude,
  }) async {
    await _execute(() async {
      _towerSites = await _fleetRepository.getTowerSites(
        query: query,
        limit: limit,
        latitude: latitude,
        longitude: longitude,
      );
    }, notifyOnSuccess: true);
  }

  Future<void> loadDailyRoutePlan({
    DateTime? date,
    int? vehicleId,
    bool silent = false,
  }) async {
    await _execute(() async {
      _dailyRoutePlan = await _fleetRepository.getTowerDieselDailyRoutePlan(
        date: date,
        vehicleId: vehicleId,
      );
    }, notifyOnSuccess: true, silent: silent);
  }

  void clearDailyRoutePlan() {
    if (_dailyRoutePlan == null) {
      return;
    }
    _dailyRoutePlan = null;
    notifyListeners();
  }

  Future<void> loadDriverNotifications({
    int limit = 40,
    bool force = false,
    bool silent = false,
  }) async {
    if (!force && _notificationsLastLoadedAt != null) {
      final age = DateTime.now().difference(_notificationsLastLoadedAt!);
      if (age <= _notificationCacheTtl) {
        return;
      }
    }
    await _execute(() async {
      final feed = await _fleetRepository.getDriverNotifications(limit: limit);
      _serverNotifications = feed.items;
      _unreadServerNotificationCount = feed.unreadCount;
      _notificationsLastLoadedAt = DateTime.now();
    }, notifyOnSuccess: true, silent: silent);
  }

  Future<bool> markDriverNotificationsRead({
    int? notificationId,
  }) async {
    final result = await _execute(() async {
      await _fleetRepository.markDriverNotificationsRead(
        notificationId: notificationId,
      );
      final feed = await _fleetRepository.getDriverNotifications(limit: 40);
      _serverNotifications = feed.items;
      _unreadServerNotificationCount = feed.unreadCount;
      _notificationsLastLoadedAt = DateTime.now();
    });
    return result;
  }

  Future<bool> deleteTowerDieselRecord({
    required int recordId,
    int? month,
    int? year,
  }) async {
    final result = await _execute(() {
      return _fleetRepository.deleteTowerDieselRecord(recordId: recordId);
    });
    if (result) {
      unawaited(
        loadTowerDieselRecords(
          month: month,
          year: year,
          silent: true,
        ),
      );
    }
    return result;
  }

  Future<bool> _execute(
    Future<void> Function() action, {
    bool notifyOnSuccess = false,
    bool silent = false,
  }) async {
    if (!silent) {
      _loading = true;
      _error = null;
      notifyListeners();
    }

    try {
      await action();
      if (notifyOnSuccess) {
        notifyListeners();
      }
      return true;
    } on ApiException catch (exception) {
      if (!silent) {
        _error = exception.message;
        notifyListeners();
      }
      return false;
    } catch (_) {
      if (!silent) {
        _error = 'Operation failed. Please retry.';
        notifyListeners();
      }
      return false;
    } finally {
      if (!silent) {
        _loading = false;
        notifyListeners();
      }
    }
  }
}
