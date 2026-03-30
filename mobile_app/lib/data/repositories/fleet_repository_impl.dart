import 'dart:io';

import '../../domain/entities/diesel_daily_route_plan.dart';
import '../../domain/entities/diesel_route_suggestion.dart';
import '../../domain/entities/driver_info.dart';
import '../../domain/entities/driver_daily_attendance.dart';
import '../../domain/entities/attendance_calendar.dart';
import '../../domain/entities/driver_location_feed.dart';
import '../../domain/entities/fuel_record.dart';
import '../../domain/entities/fuel_monthly_summary.dart';
import '../../domain/entities/monthly_report.dart';
import '../../domain/entities/notification_feed.dart';
import '../../domain/entities/salary_advance.dart';
import '../../domain/entities/salary_summary.dart';
import '../../domain/entities/service_item.dart';
import '../../domain/entities/tower_site_suggestion.dart';
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
    int? vehicleId,
    DateTime? date,
  }) {
    return _remoteDataSource.addFuelRecord(
      liters: liters,
      amount: amount,
      odometerKm: odometerKm,
      meterImage: meterImage,
      billImage: billImage,
      vehicleId: vehicleId,
      date: date,
    );
  }

  @override
  Future<void> addTowerDieselRecord({
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
  }) {
    return _remoteDataSource.addTowerDieselRecord(
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
  }

  @override
  Future<List<TowerSiteSuggestion>> getNearbyTowerSites({
    required double latitude,
    required double longitude,
    double radiusMeters = 100,
  }) {
    return _remoteDataSource.getNearbyTowerSites(
      latitude: latitude,
      longitude: longitude,
      radiusMeters: radiusMeters,
    );
  }

  @override
  Future<DieselDailyRoutePlan?> getTowerDieselDailyRoutePlan({
    DateTime? date,
    int? vehicleId,
  }) {
    return _remoteDataSource.getTowerDieselDailyRoutePlan(
      date: date,
      vehicleId: vehicleId,
    );
  }

  @override
  Future<void> saveTowerDieselDailyRoutePlan({
    required int vehicleId,
    required DateTime date,
    required List<DieselDailyRouteStop> stops,
    String status = 'PUBLISHED',
  }) {
    return _remoteDataSource.saveTowerDieselDailyRoutePlan(
      vehicleId: vehicleId,
      date: date,
      stops: stops,
      status: status,
    );
  }

  @override
  Future<DieselRouteSuggestion> optimizeTowerRoute({
    double? startLatitude,
    double? startLongitude,
    required List<DieselDailyRouteStop> stops,
    bool returnToStart = false,
  }) {
    return _remoteDataSource.optimizeTowerRoute(
      startLatitude: startLatitude,
      startLongitude: startLongitude,
      stops: stops,
      returnToStart: returnToStart,
    );
  }

  @override
  Future<TowerSiteSuggestion?> getTowerSiteById({
    required String indusSiteId,
  }) {
    return _remoteDataSource.getTowerSiteById(indusSiteId: indusSiteId);
  }

  @override
  Future<List<TowerSiteSuggestion>> getTowerSites({
    String? query,
    int? limit,
    double? latitude,
    double? longitude,
  }) {
    return _remoteDataSource.getTowerSites(
      query: query,
      limit: limit,
      latitude: latitude,
      longitude: longitude,
    );
  }

  @override
  Future<List<FuelRecord>> getTowerDieselRecords({
    int? month,
    int? year,
    DateTime? fillDate,
    String? query,
  }) {
    return _remoteDataSource.getTowerDieselRecords(
      month: month,
      year: year,
      fillDate: fillDate,
      query: query,
    );
  }

  @override
  Future<void> deleteTowerDieselRecord({
    required int recordId,
  }) {
    return _remoteDataSource.deleteTowerDieselRecord(recordId: recordId);
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
    bool confirmLargeRun = false,
    double? latitude,
    double? longitude,
  }) {
    return _remoteDataSource.endAttendance(
      endKm: endKm,
      odoEndImage: odoEndImage,
      confirmLargeRun: confirmLargeRun,
      latitude: latitude,
      longitude: longitude,
    );
  }

  @override
  Future<void> recordAttendanceLocation({
    required double latitude,
    required double longitude,
    double? accuracyMeters,
    double? speedKph,
    DateTime? recordedAt,
  }) {
    return _remoteDataSource.recordAttendanceLocation(
      latitude: latitude,
      longitude: longitude,
      accuracyMeters: accuracyMeters,
      speedKph: speedKph,
      recordedAt: recordedAt,
    );
  }

  @override
  Future<DriverLocationFeed> getTransporterDriverLocations({
    DateTime? date,
    int? driverId,
    int? attendanceId,
    bool openOnly = false,
  }) {
    return _remoteDataSource.getTransporterDriverLocations(
      date: date,
      driverId: driverId,
      attendanceId: attendanceId,
      openOnly: openOnly,
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
    int? serviceId,
  }) {
    return _remoteDataSource.assignVehicleToDriver(
      driverId: driverId,
      vehicleId: vehicleId,
      serviceId: serviceId,
    );
  }

  @override
  Future<void> removeDriverFromTransporter({
    required int driverId,
  }) {
    return _remoteDataSource.removeDriverFromTransporter(driverId: driverId);
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
  Future<DriverAttendanceCalendar> getDriverAttendanceCalendar({
    required int driverId,
    required int month,
    required int year,
  }) {
    return _remoteDataSource.getDriverAttendanceCalendar(
      driverId: driverId,
      month: month,
      year: year,
    );
  }

  @override
  Future<List<FuelRecord>> getFuelRecords() {
    return _remoteDataSource.getFuelRecords();
  }

  @override
  Future<FuelMonthlySummary> getFuelMonthlySummary({
    required int month,
    required int year,
  }) {
    return _remoteDataSource.getFuelMonthlySummary(month: month, year: year);
  }

  @override
  Future<NotificationFeed> getTransporterNotifications({
    bool unreadOnly = false,
    int limit = 30,
  }) {
    return _remoteDataSource.getTransporterNotifications(
      unreadOnly: unreadOnly,
      limit: limit,
    );
  }

  @override
  Future<NotificationFeed> getDriverNotifications({
    int limit = 30,
  }) {
    return _remoteDataSource.getDriverNotifications(limit: limit);
  }

  @override
  Future<void> markTransporterNotificationsRead({
    int? notificationId,
  }) {
    return _remoteDataSource.markTransporterNotificationsRead(
      notificationId: notificationId,
    );
  }

  @override
  Future<void> markDriverNotificationsRead({
    int? notificationId,
  }) {
    return _remoteDataSource.markDriverNotificationsRead(
      notificationId: notificationId,
    );
  }

  @override
  Future<MonthlyReport> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
    int? serviceId,
    String? serviceName,
  }) {
    return _remoteDataSource.getMonthlyReport(
      month: month,
      year: year,
      vehicleId: vehicleId,
      serviceId: serviceId,
      serviceName: serviceName,
    );
  }

  @override
  Future<SalaryMonthlySummary> getSalaryMonthlySummary({
    required int month,
    required int year,
  }) {
    return _remoteDataSource.getSalaryMonthlySummary(month: month, year: year);
  }

  @override
  Future<void> updateDriverMonthlySalary({
    required int driverId,
    required double monthlySalary,
  }) {
    return _remoteDataSource.updateDriverMonthlySalary(
      driverId: driverId,
      monthlySalary: monthlySalary,
    );
  }

  @override
  Future<DriverSalarySummary> payDriverSalary({
    required int driverId,
    required int month,
    required int year,
    int? clCount,
    double? monthlySalary,
    String? notes,
  }) {
    return _remoteDataSource.payDriverSalary(
      driverId: driverId,
      month: month,
      year: year,
      clCount: clCount,
      monthlySalary: monthlySalary,
      notes: notes,
    );
  }

  @override
  Future<List<SalaryAdvance>> getSalaryAdvances({
    required int driverId,
    required int month,
    required int year,
  }) {
    return _remoteDataSource.getSalaryAdvances(
      driverId: driverId,
      month: month,
      year: year,
    );
  }

  @override
  Future<SalaryAdvance> saveSalaryAdvance({
    int? advanceId,
    required int driverId,
    required double amount,
    DateTime? advanceDate,
    String? notes,
  }) {
    return _remoteDataSource.saveSalaryAdvance(
      advanceId: advanceId,
      driverId: driverId,
      amount: amount,
      advanceDate: advanceDate,
      notes: notes,
    );
  }

  @override
  Future<List<Trip>> getTrips() {
    return _remoteDataSource.getTrips();
  }

  @override
  Future<List<ServiceItem>> getServices({bool includeInactive = false}) {
    return _remoteDataSource.getServices(includeInactive: includeInactive);
  }

  @override
  Future<List<Vehicle>> getVehicles() {
    return _remoteDataSource.getVehicles();
  }

  @override
  Future<void> startAttendance({
    int? vehicleId,
    int? serviceId,
    String? servicePurpose,
    String? destination,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) {
    return _remoteDataSource.startAttendance(
      vehicleId: vehicleId,
      serviceId: serviceId,
      servicePurpose: servicePurpose,
      destination: destination,
      startKm: startKm,
      odoStartImage: odoStartImage,
      latitude: latitude,
      longitude: longitude,
    );
  }

  @override
  Future<void> addService({
    required String name,
    String description = '',
    bool isActive = true,
  }) {
    return _remoteDataSource.addService(
      name: name,
      description: description,
      isActive: isActive,
    );
  }

  @override
  Future<void> updateService({
    required int serviceId,
    String? name,
    String? description,
    bool? isActive,
  }) {
    return _remoteDataSource.updateService(
      serviceId: serviceId,
      name: name,
      description: description,
      isActive: isActive,
    );
  }
}
