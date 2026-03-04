import 'dart:io';

import '../../core/network/api_client.dart';
import '../models/driver_info_model.dart';
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
      'latitude': latitude.toString(),
      'longitude': longitude.toString(),
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
    File? odoEndImage,
  }) async {
    await _apiClient.postMultipart(
      '/attendance/end',
      fields: {
        'end_km': endKm.toString(),
      },
      files: {
        'odo_end_image': odoEndImage,
      },
    );
  }

  Future<void> addTrip({
    required String startLocation,
    required String destination,
    required int startKm,
    required int endKm,
    required String purpose,
  }) async {
    await _apiClient.post(
      '/trips/create',
      body: {
        'start_location': startLocation,
        'destination': destination,
        'start_km': startKm,
        'end_km': endKm,
        'purpose': purpose,
      },
    );
  }

  Future<void> addFuelRecord({
    required double liters,
    required double amount,
    required File meterImage,
    required File billImage,
    DateTime? date,
  }) async {
    await _apiClient.postMultipart(
      '/fuel/add',
      fields: {
        'liters': liters.toString(),
        'amount': amount.toString(),
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
}
