import 'dart:io';

import '../../core/network/api_client.dart';
import '../models/driver_info_model.dart';
import '../models/driver_daily_attendance_model.dart';
import '../models/fuel_record_model.dart';
import '../models/monthly_report_model.dart';
import '../models/trip_model.dart';
import '../models/vehicle_model.dart';

class FleetRemoteDataSource {
  FleetRemoteDataSource(this._apiClient);

  final ApiClient _apiClient;

  Future<void> startAttendance({
    int? vehicleId,
    required int startKm,
    required File odoStartImage,
    required double latitude,
    required double longitude,
  }) async {
    final fields = <String, String>{
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
    DateTime? date,
  }) async {
    await _apiClient.postMultipart(
      '/fuel/add',
      fields: {
        'liters': liters.toStringAsFixed(2),
        'amount': amount.toStringAsFixed(2),
        'odometer_km': odometerKm.toString(),
        if (date != null) 'date': date.toIso8601String().split('T').first,
      },
      files: {
        'meter_image': meterImage,
        'bill_image': billImage,
      },
    );
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

  Future<MonthlyReportModel> getMonthlyReport({
    required int month,
    required int year,
    int? vehicleId,
  }) async {
    final query = <String, String>{
      'month': month.toString(),
      'year': year.toString(),
      if (vehicleId != null) 'vehicle_id': vehicleId.toString(),
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
  }) async {
    await _apiClient.patch(
      '/drivers/$driverId/assign-vehicle',
      body: {
        'vehicle_id': vehicleId,
      },
    );
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
}
