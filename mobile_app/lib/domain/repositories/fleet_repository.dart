import 'dart:io';

import '../entities/driver_info.dart';
import '../entities/driver_daily_attendance.dart';
import '../entities/attendance_calendar.dart';
import '../entities/fuel_record.dart';
import '../entities/fuel_monthly_summary.dart';
import '../entities/monthly_report.dart';
import '../entities/notification_feed.dart';
import '../entities/salary_advance.dart';
import '../entities/salary_summary.dart';
import '../entities/service_item.dart';
import '../entities/tower_site_suggestion.dart';
import '../entities/trip.dart';
import '../entities/vehicle.dart';

abstract class FleetRepository {
  Future<void> startAttendance({
    int? vehicleId,
    int? serviceId,
    String? servicePurpose,
    String? destination,
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
    int? vehicleId,
    DateTime? date,
  });

  Future<void> addTowerDieselRecord({
    required String indusSiteId,
    required String siteName,
    required double fuelFilled,
    bool confirmSiteNameUpdate = false,
    int? startKm,
    int? endKm,
    double? towerLatitude,
    double? towerLongitude,
    required String purpose,
    DateTime? fillDate,
    required File logbookPhoto,
  });

  Future<List<TowerSiteSuggestion>> getNearbyTowerSites({
    required double latitude,
    required double longitude,
    double radiusMeters,
  });

  Future<TowerSiteSuggestion?> getTowerSiteById({
    required String indusSiteId,
  });

  Future<List<TowerSiteSuggestion>> getTowerSites({
    String? query,
    int? limit,
    double? latitude,
    double? longitude,
  });

  Future<List<FuelRecord>> getTowerDieselRecords({
    int? month,
    int? year,
    DateTime? fillDate,
    String? query,
  });

  Future<void> deleteTowerDieselRecord({
    required int recordId,
  });

  Future<List<Vehicle>> getVehicles();

  Future<List<DriverInfo>> getDrivers();

  Future<List<ServiceItem>> getServices({bool includeInactive = false});

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
    int? serviceId,
  });

  Future<void> removeDriverFromTransporter({
    required int driverId,
  });

  Future<void> addService({
    required String name,
    String description,
    bool isActive,
  });

  Future<void> updateService({
    required int serviceId,
    String? name,
    String? description,
    bool? isActive,
  });

  Future<List<DriverDailyAttendance>> getDailyDriverAttendance({
    DateTime? date,
  });

  Future<DriverAttendanceCalendar> getDriverAttendanceCalendar({
    required int driverId,
    required int month,
    required int year,
  });

  Future<void> markDailyDriverAttendance({
    required int driverId,
    required String status,
    DateTime? date,
  });

  Future<List<Trip>> getTrips();

  Future<List<FuelRecord>> getFuelRecords();

  Future<FuelMonthlySummary> getFuelMonthlySummary({
    required int month,
    required int year,
  });

  Future<NotificationFeed> getTransporterNotifications({
    bool unreadOnly,
    int limit,
  });

  Future<NotificationFeed> getDriverNotifications({
    int limit,
  });

  Future<void> markDriverNotificationsRead({
    int? notificationId,
  });

  Future<void> markTransporterNotificationsRead({
    int? notificationId,
  });

  Future<MonthlyReport> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
    int? serviceId,
    String? serviceName,
  });

  Future<SalaryMonthlySummary> getSalaryMonthlySummary({
    required int month,
    required int year,
  });

  Future<void> updateDriverMonthlySalary({
    required int driverId,
    required double monthlySalary,
  });

  Future<DriverSalarySummary> payDriverSalary({
    required int driverId,
    required int month,
    required int year,
    int? clCount,
    double? monthlySalary,
    String? notes,
  });

  Future<List<SalaryAdvance>> getSalaryAdvances({
    required int driverId,
    required int month,
    required int year,
  });

  Future<SalaryAdvance> saveSalaryAdvance({
    int? advanceId,
    required int driverId,
    required double amount,
    DateTime? advanceDate,
    String? notes,
  });
}
