import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/attendance_calendar.dart';
import '../../domain/entities/driver_info.dart';
import '../../domain/entities/driver_daily_attendance.dart';
import '../../domain/entities/diesel_daily_route_plan.dart';
import '../../domain/entities/diesel_route_suggestion.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/fuel_monthly_summary.dart';
import '../../domain/entities/monthly_report.dart';
import '../../domain/entities/app_notification.dart';
import '../../domain/entities/salary_advance.dart';
import '../../domain/entities/salary_summary.dart';
import '../../domain/entities/service_item.dart';
import '../../domain/entities/tower_site_suggestion.dart';
import '../../domain/entities/trip.dart';
import '../../domain/entities/vehicle.dart';
import '../../domain/repositories/fleet_repository.dart';

class TransporterProvider extends ChangeNotifier {
  TransporterProvider(this._fleetRepository);

  final FleetRepository _fleetRepository;
  static const Duration _dashboardCacheTtl = Duration(minutes: 1);

  bool _loading = false;
  String? _error;
  DateTime? _dashboardLastLoadedAt;

  List<Vehicle> _vehicles = const [];
  List<DriverInfo> _drivers = const [];
  List<DriverDailyAttendance> _dailyAttendance = const [];
  List<Trip> _trips = const [];
  List<FuelRecord> _fuelRecords = const [];
  List<FuelRecord> _towerDieselRecords = const [];
  List<TowerSiteSuggestion> _towerSites = const [];
  DieselDailyRoutePlan? _dailyRoutePlan;
  List<AppNotification> _notifications = const [];
  int _unreadNotificationCount = 0;
  List<ServiceItem> _services = const [];
  MonthlyReport? _monthlyReport;
  DriverAttendanceCalendar? _driverAttendanceCalendar;
  FuelMonthlySummary? _fuelMonthlySummary;
  SalaryMonthlySummary? _salaryMonthlySummary;
  List<SalaryAdvance> _salaryAdvances = const [];

  bool get loading => _loading;
  String? get error => _error;
  List<Vehicle> get vehicles => _vehicles;
  List<DriverInfo> get drivers => _drivers;
  List<DriverDailyAttendance> get dailyAttendance => _dailyAttendance;
  List<Trip> get trips => _trips;
  List<FuelRecord> get fuelRecords => _fuelRecords;
  List<FuelRecord> get towerDieselRecords => _towerDieselRecords;
  List<TowerSiteSuggestion> get towerSites => _towerSites;
  DieselDailyRoutePlan? get dailyRoutePlan => _dailyRoutePlan;
  List<AppNotification> get notifications => _notifications;
  int get unreadNotificationCount => _unreadNotificationCount;
  List<ServiceItem> get services => _services;
  MonthlyReport? get monthlyReport => _monthlyReport;
  DriverAttendanceCalendar? get driverAttendanceCalendar =>
      _driverAttendanceCalendar;
  FuelMonthlySummary? get fuelMonthlySummary => _fuelMonthlySummary;
  SalaryMonthlySummary? get salaryMonthlySummary => _salaryMonthlySummary;
  List<SalaryAdvance> get salaryAdvances => _salaryAdvances;

  Future<void> loadDashboardData({
    bool force = false,
    bool prefetchHeavyData = true,
  }) async {
    if (!force && _dashboardLastLoadedAt != null) {
      final age = DateTime.now().difference(_dashboardLastLoadedAt!);
      if (age <= _dashboardCacheTtl) {
        return;
      }
    }

    await _execute(() async {
      final results = await Future.wait([
        _fleetRepository.getVehicles(),
        _fleetRepository.getDrivers(),
        _fleetRepository.getServices(includeInactive: true),
        _fleetRepository.getTrips(),
      ]);

      _vehicles = results[0] as List<Vehicle>;
      _drivers = results[1] as List<DriverInfo>;
      _services = results[2] as List<ServiceItem>;
      _trips = results[3] as List<Trip>;

      try {
        final feed = await _fleetRepository.getTransporterNotifications(limit: 40);
        _notifications = feed.items;
        _unreadNotificationCount = feed.unreadCount;
      } on ApiException {
        _notifications = const [];
        _unreadNotificationCount = 0;
      }
      _dashboardLastLoadedAt = DateTime.now();
    });

    if (prefetchHeavyData) {
      unawaited(_prefetchHeavyDashboardData(force: force));
    }
  }

  Future<void> loadMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
    int? serviceId,
    String? serviceName,
  }) async {
    await _execute(() async {
      _monthlyReport = await _fleetRepository.getMonthlyReport(
        month: month,
        year: year,
        vehicleId: vehicleId,
        serviceId: serviceId,
        serviceName: serviceName,
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
      await loadDashboardData(force: true);
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
      await loadDashboardData(force: true);
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
    int? serviceId,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.assignVehicleToDriver(
        driverId: driverId,
        vehicleId: vehicleId,
        serviceId: serviceId,
      );
      await loadDashboardData(force: true);
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

  Future<bool> removeDriverFromTransporter({
    required int driverId,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.removeDriverFromTransporter(driverId: driverId);
      await loadDashboardData(force: true);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to remove driver.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> addService({
    required String name,
    String description = '',
    bool isActive = true,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.addService(
        name: name,
        description: description,
        isActive: isActive,
      );
      await loadDashboardData(force: true);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to add service.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> updateService({
    required int serviceId,
    String? name,
    String? description,
    bool? isActive,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.updateService(
        serviceId: serviceId,
        name: name,
        description: description,
        isActive: isActive,
      );
      await loadDashboardData(force: true);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update service.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> loadDailyAttendance({DateTime? date}) async {
    await _execute(() async {
      _dailyAttendance =
          await _fleetRepository.getDailyDriverAttendance(date: date);
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
      _dailyAttendance =
          await _fleetRepository.getDailyDriverAttendance(date: date);
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

  Future<void> loadDriverAttendanceCalendar({
    required int driverId,
    required int month,
    required int year,
  }) async {
    await _execute(() async {
      _driverAttendanceCalendar =
          await _fleetRepository.getDriverAttendanceCalendar(
        driverId: driverId,
        month: month,
        year: year,
      );
    });
  }

  Future<void> loadFuelMonthlySummary({
    required int month,
    required int year,
  }) async {
    await _execute(() async {
      _fuelMonthlySummary = await _fleetRepository.getFuelMonthlySummary(
        month: month,
        year: year,
      );
    });
  }

  Future<void> loadFuelRecords({
    bool silent = false,
  }) async {
    await _execute(() async {
      _fuelRecords = await _fleetRepository.getFuelRecords();
    }, silent: silent);
  }

  Future<void> loadSalaryMonthlySummary({
    required int month,
    required int year,
  }) async {
    await _execute(() async {
      _salaryMonthlySummary = await _fleetRepository.getSalaryMonthlySummary(
        month: month,
        year: year,
      );
    });
  }

  Future<void> loadSalaryAdvances({
    required int driverId,
    required int month,
    required int year,
    bool silent = false,
  }) async {
    await _execute(() async {
      _salaryAdvances = await _fleetRepository.getSalaryAdvances(
        driverId: driverId,
        month: month,
        year: year,
      );
    }, silent: silent);
  }

  Future<bool> updateDriverMonthlySalary({
    required int driverId,
    required double monthlySalary,
    int? refreshMonth,
    int? refreshYear,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.updateDriverMonthlySalary(
        driverId: driverId,
        monthlySalary: monthlySalary,
      );
      await loadDashboardData(force: true, prefetchHeavyData: false);
      if (refreshMonth != null && refreshYear != null) {
        _salaryMonthlySummary = await _fleetRepository.getSalaryMonthlySummary(
          month: refreshMonth,
          year: refreshYear,
        );
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update monthly salary.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> payDriverSalary({
    required int driverId,
    required int month,
    required int year,
    int? clCount,
    double? monthlySalary,
    String? notes,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.payDriverSalary(
        driverId: driverId,
        month: month,
        year: year,
        clCount: clCount,
        monthlySalary: monthlySalary,
        notes: notes,
      );
      await loadDashboardData(force: true, prefetchHeavyData: false);
      _salaryMonthlySummary = await _fleetRepository.getSalaryMonthlySummary(
        month: month,
        year: year,
      );
      _salaryAdvances = await _fleetRepository.getSalaryAdvances(
        driverId: driverId,
        month: month,
        year: year,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to pay salary.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> saveSalaryAdvance({
    int? advanceId,
    required int driverId,
    required double amount,
    DateTime? advanceDate,
    String? notes,
    int? refreshMonth,
    int? refreshYear,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.saveSalaryAdvance(
        advanceId: advanceId,
        driverId: driverId,
        amount: amount,
        advanceDate: advanceDate,
        notes: notes,
      );
      if (refreshMonth != null && refreshYear != null) {
        _salaryMonthlySummary = await _fleetRepository.getSalaryMonthlySummary(
          month: refreshMonth,
          year: refreshYear,
        );
        _salaryAdvances = await _fleetRepository.getSalaryAdvances(
          driverId: driverId,
          month: refreshMonth,
          year: refreshYear,
        );
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to save salary advance.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> loadTowerDieselRecords({
    int? month,
    int? year,
    DateTime? fillDate,
    String? query,
    bool silent = false,
  }) async {
    await _execute(() async {
      _towerDieselRecords = await _fleetRepository.getTowerDieselRecords(
        month: month,
        year: year,
        fillDate: fillDate,
        query: query,
      );
    }, silent: silent);
  }

  Future<void> loadTowerSites({
    String? query,
    int limit = 40,
    bool silent = false,
  }) async {
    await _execute(() async {
      _towerSites = await _fleetRepository.getTowerSites(
        query: query,
        limit: limit,
      );
    }, silent: silent);
  }

  Future<void> loadDailyRoutePlan({
    required int vehicleId,
    DateTime? date,
    bool silent = false,
  }) async {
    await _execute(() async {
      _dailyRoutePlan = await _fleetRepository.getTowerDieselDailyRoutePlan(
        vehicleId: vehicleId,
        date: date,
      );
    }, silent: silent);
  }

  void clearDailyRoutePlan() {
    if (_dailyRoutePlan == null) {
      return;
    }
    _dailyRoutePlan = null;
    notifyListeners();
  }

  Future<bool> saveDailyRoutePlan({
    required int vehicleId,
    required DateTime date,
    required List<DieselDailyRouteStop> stops,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.saveTowerDieselDailyRoutePlan(
        vehicleId: vehicleId,
        date: date,
        stops: stops,
      );
      _dailyRoutePlan = await _fleetRepository.getTowerDieselDailyRoutePlan(
        vehicleId: vehicleId,
        date: date,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to save daily route plan.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<DieselRouteSuggestion?> suggestTowerRoute({
    double? startLatitude,
    double? startLongitude,
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
      _error = 'Unable to optimize route right now.';
      notifyListeners();
      return null;
    }
  }

  Future<bool> deleteTowerDieselRecord({
    required int recordId,
    int? month,
    int? year,
    DateTime? fillDate,
    String? query,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.deleteTowerDieselRecord(recordId: recordId);
      _towerDieselRecords = await _fleetRepository.getTowerDieselRecords(
        month: month,
        year: year,
        fillDate: fillDate,
        query: query,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to delete tower diesel record.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> loadNotifications({
    bool unreadOnly = false,
    int limit = 40,
    bool silent = false,
  }) async {
    if (!silent) {
      await _execute(() async {
        final feed = await _fleetRepository.getTransporterNotifications(
          unreadOnly: unreadOnly,
          limit: limit,
        );
        _notifications = feed.items;
        _unreadNotificationCount = feed.unreadCount;
      });
      return;
    }
    try {
      final feed = await _fleetRepository.getTransporterNotifications(
        unreadOnly: unreadOnly,
        limit: limit,
      );
      _notifications = feed.items;
      _unreadNotificationCount = feed.unreadCount;
      notifyListeners();
    } catch (_) {
      // Keep silent refresh non-intrusive on background polling.
    }
  }

  Future<bool> markNotificationsRead({
    int? notificationId,
  }) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      await _fleetRepository.markTransporterNotificationsRead(
        notificationId: notificationId,
      );
      final feed =
          await _fleetRepository.getTransporterNotifications(limit: 40);
      _notifications = feed.items;
      _unreadNotificationCount = feed.unreadCount;
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update notifications.';
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> _execute(
    Future<void> Function() action, {
    bool silent = false,
  }) async {
    if (!silent) {
      _loading = true;
      _error = null;
      notifyListeners();
    }

    try {
      await action();
    } on ApiException catch (exception) {
      _error = exception.message;
    } catch (_) {
      _error = 'Unable to load data.';
    } finally {
      if (!silent) {
        _loading = false;
        notifyListeners();
      } else {
        notifyListeners();
      }
    }
  }

  Future<void> _prefetchHeavyDashboardData({bool force = false}) async {
    if (!force && _fuelRecords.isNotEmpty && _towerDieselRecords.isNotEmpty) {
      return;
    }

    var shouldNotify = false;

    if (force || _fuelRecords.isEmpty) {
      try {
        _fuelRecords = await _fleetRepository.getFuelRecords();
        shouldNotify = true;
      } on ApiException catch (exception) {
        if (_isDieselModuleDisabled(exception)) {
          _fuelRecords = const [];
          _towerDieselRecords = const [];
          shouldNotify = true;
        }
      } catch (_) {
        // Keep background prefetch non-blocking.
      }
    }

    if (force || _towerDieselRecords.isEmpty) {
      try {
        _towerDieselRecords = await _fleetRepository.getTowerDieselRecords();
        shouldNotify = true;
      } on ApiException catch (exception) {
        if (_isDieselModuleDisabled(exception)) {
          _towerDieselRecords = const [];
          shouldNotify = true;
        }
      } catch (_) {
        // Keep background prefetch non-blocking.
      }
    }

    if (shouldNotify) {
      notifyListeners();
    }
  }

  bool _isDieselModuleDisabled(ApiException exception) {
    return exception.message.toLowerCase().contains("diesel module disabled");
  }
}
