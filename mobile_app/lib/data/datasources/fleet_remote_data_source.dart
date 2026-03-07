import 'dart:io';

import '../../core/network/api_client.dart';
import '../models/driver_info_model.dart';
import '../models/driver_daily_attendance_model.dart';
import '../models/attendance_calendar_model.dart';
import '../models/fuel_record_model.dart';
import '../models/fuel_monthly_summary_model.dart';
import '../models/monthly_report_model.dart';
import '../models/notification_model.dart';
import '../models/salary_advance_model.dart';
import '../models/salary_summary_model.dart';
import '../models/service_item_model.dart';
import '../models/tower_site_suggestion_model.dart';
import '../models/trip_model.dart';
import '../models/vehicle_model.dart';

class FleetRemoteDataSource {
  FleetRemoteDataSource(this._apiClient);

  final ApiClient _apiClient;

  Future<void> startAttendance({
    int? vehicleId,
    int? serviceId,
    String? servicePurpose,
    String? destination,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) async {
    final fields = <String, String>{
      if (serviceId != null) 'service_id': serviceId.toString(),
      if (servicePurpose != null && servicePurpose.trim().isNotEmpty)
        'service_purpose': servicePurpose.trim(),
      if (destination != null && destination.trim().isNotEmpty)
        'destination': destination.trim(),
      'start_km': startKm.toString(),
      'latitude': latitude.toStringAsFixed(6),
      'longitude': longitude.toStringAsFixed(6),
    };

    if (vehicleId != null) {
      fields['vehicle_id'] = vehicleId.toString();
    }

    await _apiClient.postMultipart(
      '/attendance/start',
      fields: fields,
      files: {
        'odo_start_image': odoStartImage,
      },
    );
  }

  Future<void> endAttendance({
    required int endKm,
    required File odoEndImage,
    double? latitude,
    double? longitude,
  }) async {
    final fields = <String, String>{
      'end_km': endKm.toString(),
    };
    if (latitude != null && longitude != null) {
      fields['latitude'] = latitude.toStringAsFixed(6);
      fields['longitude'] = longitude.toStringAsFixed(6);
    }

    await _apiClient.postMultipart(
      '/attendance/end',
      fields: fields,
      files: {
        'odo_end_image': odoEndImage,
      },
    );
  }

  Future<void> startTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required String purpose,
    required File startOdoImage,
  }) async {
    await _apiClient.postMultipart(
      '/trips/create',
      fields: {
        'start_location': startLocation,
        'destination': destination,
        'start_km': startKm.toString(),
        'purpose': purpose,
      },
      files: {
        'start_odo_image': startOdoImage,
      },
    );
  }

  Future<void> closeTrip({
    required int tripId,
    required int endKm,
    required File endOdoImage,
  }) async {
    await _apiClient.postMultipart(
      '/trips/$tripId/close',
      fields: {
        'end_km': endKm.toString(),
      },
      files: {
        'end_odo_image': endOdoImage,
      },
    );
  }

  Future<void> addFuelRecord({
    required double liters,
    required double amount,
    required int odometerKm,
    required File meterImage,
    required File billImage,
    int? vehicleId,
    DateTime? date,
  }) async {
    await _apiClient.postMultipart(
      '/fuel/add',
      fields: {
        'entry_type': 'VEHICLE_FILLING',
        'liters': liters.toStringAsFixed(2),
        'amount': amount.toStringAsFixed(2),
        'odometer_km': odometerKm.toString(),
        if (vehicleId != null) 'vehicle_id': vehicleId.toString(),
        if (date != null) 'date': date.toIso8601String().split('T').first,
      },
      files: {
        'meter_image': meterImage,
        'bill_image': billImage,
      },
    );
  }

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
  }) async {
    await _apiClient.postMultipart(
      '/diesel/add',
      fields: {
        'indus_site_id': indusSiteId,
        'site_name': siteName,
        'fuel_filled': fuelFilled.toStringAsFixed(2),
        if (confirmSiteNameUpdate) 'confirm_site_name_update': 'true',
        if (startKm != null) 'start_km': startKm.toString(),
        if (endKm != null) 'end_km': endKm.toString(),
        if (towerLatitude != null)
          'tower_latitude': towerLatitude.toStringAsFixed(6),
        if (towerLongitude != null)
          'tower_longitude': towerLongitude.toStringAsFixed(6),
        'purpose': purpose,
        if (fillDate != null)
          'fill_date': fillDate.toIso8601String().split('T').first,
      },
      files: {
        'logbook_photo': logbookPhoto,
      },
    );
  }

  Future<List<TowerSiteSuggestionModel>> getNearbyTowerSites({
    required double latitude,
    required double longitude,
    double radiusMeters = 100,
  }) async {
    final response = await _apiClient.get(
      '/diesel/nearby-sites',
      query: {
        'latitude': latitude.toStringAsFixed(6),
        'longitude': longitude.toStringAsFixed(6),
        'radius_m': radiusMeters.toStringAsFixed(0),
      },
    );
    final map = response as Map<String, dynamic>;
    final list = map['items'] as List<dynamic>? ?? const [];
    return list
        .map(
          (item) =>
              TowerSiteSuggestionModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<TowerSiteSuggestionModel?> getTowerSiteById({
    required String indusSiteId,
  }) async {
    try {
      final response = await _apiClient.get(
        '/diesel/site-by-id',
        query: {
          'indus_site_id': indusSiteId.trim(),
        },
      );
      return TowerSiteSuggestionModel.fromJson(response as Map<String, dynamic>);
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        return null;
      }
      rethrow;
    }
  }

  Future<List<TowerSiteSuggestionModel>> getTowerSites({
    String? query,
    int? limit,
    double? latitude,
    double? longitude,
  }) async {
    final response = await _apiClient.get(
      '/diesel/sites',
      query: {
        if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
        if (limit != null) 'limit': limit.toString(),
        if (latitude != null) 'latitude': latitude.toString(),
        if (longitude != null) 'longitude': longitude.toString(),
      },
    );
    final map = response as Map<String, dynamic>;
    final list = map['items'] as List<dynamic>? ?? const [];
    return list
        .map(
          (item) =>
              TowerSiteSuggestionModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<List<FuelRecordModel>> getTowerDieselRecords({
    int? month,
    int? year,
    DateTime? fillDate,
    String? query,
  }) async {
    final response = await _apiClient.get(
      '/diesel',
      query: {
        if (month != null) 'month': month.toString(),
        if (year != null) 'year': year.toString(),
        if (fillDate != null) 'fill_date': fillDate.toIso8601String().split('T').first,
        if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
      },
    );
    final list = response as List<dynamic>;
    return list
        .map((item) => FuelRecordModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteTowerDieselRecord({
    required int recordId,
  }) async {
    await _apiClient.delete('/diesel/$recordId');
  }

  Future<List<VehicleModel>> getVehicles() async {
    final response = await _apiClient.get('/vehicles');
    final list = response as List<dynamic>;
    return list
        .map((item) => VehicleModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<DriverInfoModel>> getDrivers() async {
    final response = await _apiClient.get('/drivers');
    final list = response as List<dynamic>;
    return list
        .map((item) => DriverInfoModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<ServiceItemModel>> getServices({
    bool includeInactive = false,
  }) async {
    final response = await _apiClient.get(
      '/services',
      query: {
        if (includeInactive) 'include_inactive': 'true',
      },
    );
    final list = response as List<dynamic>;
    return list
        .map((item) => ServiceItemModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<TripModel>> getTrips() async {
    final response = await _apiClient.get('/trips');
    final list = response as List<dynamic>;
    return list
        .map((item) => TripModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<FuelRecordModel>> getFuelRecords() async {
    final response = await _apiClient.get('/fuel');
    final list = response as List<dynamic>;
    return list
        .map((item) => FuelRecordModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SalaryMonthlySummaryModel> getSalaryMonthlySummary({
    required int month,
    required int year,
  }) async {
    final response = await _apiClient.get(
      '/salary/monthly',
      query: {
        'month': month.toString(),
        'year': year.toString(),
      },
    );
    return SalaryMonthlySummaryModel.fromJson(response as Map<String, dynamic>);
  }

  Future<void> updateDriverMonthlySalary({
    required int driverId,
    required double monthlySalary,
  }) async {
    await _apiClient.patch(
      '/salary/driver/$driverId/monthly-salary',
      body: {
        'monthly_salary': monthlySalary.toStringAsFixed(2),
      },
    );
  }

  Future<DriverSalarySummaryModel> payDriverSalary({
    required int driverId,
    required int month,
    required int year,
    int? clCount,
    double? monthlySalary,
    String? notes,
  }) async {
    final response = await _apiClient.post(
      '/salary/pay',
      body: {
        'driver_id': driverId,
        'month': month,
        'year': year,
        if (clCount != null) 'cl_count': clCount,
        if (monthlySalary != null)
          'monthly_salary': monthlySalary.toStringAsFixed(2),
        if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      },
    );
    final map = response as Map<String, dynamic>;
    return DriverSalarySummaryModel.fromJson(
      map['row'] as Map<String, dynamic>,
    );
  }

  Future<List<SalaryAdvanceModel>> getSalaryAdvances({
    required int driverId,
    required int month,
    required int year,
  }) async {
    final response = await _apiClient.get(
      '/salary/advances',
      query: {
        'driver_id': driverId.toString(),
        'month': month.toString(),
        'year': year.toString(),
      },
    );
    final list = response as List<dynamic>;
    return list
        .map((item) => SalaryAdvanceModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<SalaryAdvanceModel> saveSalaryAdvance({
    int? advanceId,
    required int driverId,
    required double amount,
    DateTime? advanceDate,
    String? notes,
  }) async {
    final body = <String, dynamic>{
      'amount': amount.toStringAsFixed(2),
      if (advanceId == null) 'driver_id': driverId,
      if (advanceDate != null)
        'advance_date': advanceDate.toIso8601String().split('T').first,
      if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
    };
    final response = advanceId == null
        ? await _apiClient.post('/salary/advances', body: body)
        : await _apiClient.patch('/salary/advances/$advanceId', body: body);
    final map = response as Map<String, dynamic>;
    return SalaryAdvanceModel.fromJson(map['advance'] as Map<String, dynamic>);
  }

  Future<MonthlyReportModel> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
    int? serviceId,
    String? serviceName,
  }) async {
    final query = <String, String>{
      'month': month.toString(),
      'year': year.toString(),
      if (vehicleId != null) 'vehicle_id': vehicleId.toString(),
      if (serviceId != null) 'service_id': serviceId.toString(),
      if (serviceName != null && serviceName.trim().isNotEmpty)
        'service_name': serviceName.trim(),
    };

    final response = await _apiClient.get('/reports/monthly', query: query);
    return MonthlyReportModel.fromJson(response as Map<String, dynamic>);
  }

  Future<void> addVehicle({
    required String vehicleNumber,
    required String model,
    String status = 'ACTIVE',
  }) async {
    await _apiClient.post(
      '/vehicles',
      body: {
        'vehicle_number': vehicleNumber,
        'model': model,
        'status': status,
      },
    );
  }

  Future<void> addService({
    required String name,
    String description = '',
    bool isActive = true,
  }) async {
    await _apiClient.post(
      '/services',
      body: {
        'name': name,
        'description': description,
        'is_active': isActive,
      },
    );
  }

  Future<void> updateService({
    required int serviceId,
    String? name,
    String? description,
    bool? isActive,
  }) async {
    await _apiClient.patch(
      '/services/$serviceId',
      body: {
        if (name != null) 'name': name,
        if (description != null) 'description': description,
        if (isActive != null) 'is_active': isActive,
      },
    );
  }

  Future<String?> requestDriverAllocationOtp({
    required String email,
  }) async {
    final response = await _apiClient.post(
      '/drivers/allocation/request-otp',
      body: {
        'email': email,
      },
    );
    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<void> verifyDriverAllocationOtp({
    required String email,
    required String otp,
  }) async {
    await _apiClient.post(
      '/drivers/allocation/verify',
      body: {
        'email': email,
        'otp': otp,
      },
    );
  }

  Future<void> assignVehicleToDriver({
    required int driverId,
    int? vehicleId,
    int? serviceId,
  }) async {
    await _apiClient.patch(
      '/drivers/$driverId/assign-vehicle',
      body: {
        'vehicle_id': vehicleId,
        'service_id': serviceId,
      },
    );
  }

  Future<void> removeDriverFromTransporter({
    required int driverId,
  }) async {
    await _apiClient.delete('/drivers/$driverId/remove');
  }

  Future<List<DriverDailyAttendanceModel>> getDailyDriverAttendance({
    DateTime? date,
  }) async {
    final query = <String, String>{
      if (date != null) 'date': date.toIso8601String().split('T').first,
    };
    final response = await _apiClient.get('/attendance/daily', query: query);
    final map = response as Map<String, dynamic>;
    final list = map['items'] as List<dynamic>? ?? const [];
    return list
        .map(
          (item) =>
              DriverDailyAttendanceModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<void> markDailyDriverAttendance({
    required int driverId,
    required String status,
    DateTime? date,
  }) async {
    await _apiClient.post(
      '/attendance/daily/mark',
      body: {
        'driver_id': driverId,
        'status': status,
        if (date != null) 'date': date.toIso8601String().split('T').first,
      },
    );
  }

  Future<DriverAttendanceCalendarModel> getDriverAttendanceCalendar({
    required int driverId,
    required int month,
    required int year,
  }) async {
    final response = await _apiClient.get(
      '/attendance/driver/$driverId/calendar',
      query: {
        'month': month.toString(),
        'year': year.toString(),
      },
    );
    return DriverAttendanceCalendarModel.fromJson(
      response as Map<String, dynamic>,
    );
  }

  Future<FuelMonthlySummaryModel> getFuelMonthlySummary({
    required int month,
    required int year,
  }) async {
    final response = await _apiClient.get(
      '/reports/fuel-monthly',
      query: {
        'month': month.toString(),
        'year': year.toString(),
      },
    );
    return FuelMonthlySummaryModel.fromJson(response as Map<String, dynamic>);
  }

  Future<NotificationFeedModel> getTransporterNotifications({
    bool unreadOnly = false,
    int limit = 30,
  }) async {
    final response = await _apiClient.get(
      '/notifications',
      query: {
        if (unreadOnly) 'unread_only': 'true',
        'limit': limit.toString(),
      },
    );
    return NotificationFeedModel.fromJson(response as Map<String, dynamic>);
  }

  Future<NotificationFeedModel> getDriverNotifications({
    int limit = 30,
  }) async {
    final response = await _apiClient.get(
      '/driver/notifications',
      query: {
        'limit': limit.toString(),
      },
    );
    return NotificationFeedModel.fromJson(response as Map<String, dynamic>);
  }

  Future<void> markTransporterNotificationsRead({
    int? notificationId,
  }) async {
    await _apiClient.post(
      '/notifications/mark-read',
      body: {
        if (notificationId != null) 'notification_id': notificationId,
      },
    );
  }

  Future<void> markDriverNotificationsRead({
    int? notificationId,
  }) async {
    await _apiClient.post(
      '/driver/notifications/mark-read',
      body: {
        if (notificationId != null) 'notification_id': notificationId,
      },
    );
  }
}
