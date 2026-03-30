import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../network/api_client.dart';
import '../../domain/entities/trip.dart';
import '../../domain/repositories/fleet_repository.dart';
import 'location_service.dart';
import 'native_trip_tracking_service.dart';

class TripTrackingService {
  TripTrackingService._();

  static final TripTrackingService instance = TripTrackingService._();

  static const Duration _minUploadInterval = Duration(seconds: 60);
  static const double _minUploadDistanceMeters = 75;
  static const Duration _minStationaryUploadInterval = Duration(minutes: 5);
  static const double _movingSpeedThresholdMps = 1.0; // ~3.6 km/h
  static const double _movingDistanceFallbackMeters = 200;

  final LocationService _locationService = LocationService();

  FleetRepository? _fleetRepository;
  StreamSubscription<Position>? _positionSubscription;
  int? _trackedAttendanceId;
  DateTime? _lastUploadAt;
  Position? _lastUploadedPosition;
  bool _nativeServiceActive = false;
  bool _startInFlight = false;
  bool _uploadInFlight = false;

  bool get isTracking =>
      _trackedAttendanceId != null &&
      (_positionSubscription != null || _nativeServiceActive);
  int? get trackedAttendanceId => _trackedAttendanceId;

  void configure(FleetRepository repository) {
    _fleetRepository = repository;
  }

  Future<void> syncWithTrips(
    List<Trip> trips, {
    required bool locationTrackingEnabled,
  }) async {
    if (!locationTrackingEnabled) {
      await stopTracking();
      return;
    }

    final activeTrip = _activeDayTrip(trips);
    if (activeTrip == null || activeTrip.attendanceId == null) {
      await stopTracking();
      return;
    }

    final attendanceId = activeTrip.attendanceId!;
    if (_trackedAttendanceId == attendanceId &&
        (_positionSubscription != null || _nativeServiceActive)) {
      return;
    }

    await _startTracking(attendanceId: attendanceId);
  }

  Future<void> stopTracking() async {
    await _positionSubscription?.cancel();
    _positionSubscription = null;
    if (_nativeServiceActive) {
      await NativeTripTrackingService.stop();
    }
    _nativeServiceActive = false;
    _trackedAttendanceId = null;
    _lastUploadAt = null;
    _lastUploadedPosition = null;
  }

  Future<void> _startTracking({required int attendanceId}) async {
    if (_startInFlight) {
      return;
    }
    if (_fleetRepository == null) {
      debugPrint('Trip tracking skipped: fleet repository is not configured.');
      return;
    }

    _startInFlight = true;
    try {
      await _locationService.ensureTrackingPermission();
      await _positionSubscription?.cancel();
      _positionSubscription = null;
      _nativeServiceActive = false;

      if (Platform.isAndroid) {
        final nativeStarted = await NativeTripTrackingService.start();
        if (nativeStarted) {
          _trackedAttendanceId = attendanceId;
          _nativeServiceActive = true;
          _lastUploadAt = null;
          _lastUploadedPosition = null;
          return;
        }
      }

      _positionSubscription = _locationService.watchTripPositions().listen(
            _handlePosition,
            onError: (Object error, StackTrace stackTrace) {
              debugPrint('Trip tracking stream error: $error');
            },
          );
      _trackedAttendanceId = attendanceId;
      _lastUploadAt = null;
      _lastUploadedPosition = null;
    } catch (error) {
      debugPrint('Trip tracking start failed: $error');
      await stopTracking();
    } finally {
      _startInFlight = false;
    }
  }

  Future<void> _handlePosition(Position position) async {
    final repository = _fleetRepository;
    final trackedAttendanceId = _trackedAttendanceId;
    if (repository == null || trackedAttendanceId == null) {
      return;
    }
    if (_uploadInFlight) {
      return;
    }

    if (!_shouldUpload(position)) {
      return;
    }

    _uploadInFlight = true;
    try {
      final speedKph = position.speed >= 0 ? position.speed * 3.6 : null;
      await repository.recordAttendanceLocation(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyMeters: position.accuracy.isFinite ? position.accuracy : null,
        speedKph: speedKph != null && speedKph.isFinite ? speedKph : null,
        recordedAt: position.timestamp,
      );
      _lastUploadAt = DateTime.now();
      _lastUploadedPosition = position;
    } on ApiException catch (error) {
      debugPrint('Trip tracking upload failed: $error');
      final message = error.message.toLowerCase();
      if (message.contains('disabled') ||
          message.contains('no active run found')) {
        await stopTracking();
      }
    } catch (error) {
      debugPrint('Trip tracking upload failed: $error');
    } finally {
      _uploadInFlight = false;
    }
  }

  bool _shouldUpload(Position position) {
    final lastUploadAt = _lastUploadAt;
    final lastUploadedPosition = _lastUploadedPosition;
    if (lastUploadAt == null || lastUploadedPosition == null) {
      return true;
    }

    final elapsed = DateTime.now().difference(lastUploadAt);
    final distance = Geolocator.distanceBetween(
      lastUploadedPosition.latitude,
      lastUploadedPosition.longitude,
      position.latitude,
      position.longitude,
    );

    final currentAccuracy =
        position.accuracy.isFinite ? position.accuracy : 0;
    final lastAccuracy = lastUploadedPosition.accuracy.isFinite
        ? lastUploadedPosition.accuracy
        : 0;
    final effectiveMinDistance = math.max(
      _minUploadDistanceMeters,
      currentAccuracy + lastAccuracy,
    );

    final speedMps = (position.speed.isFinite && position.speed >= 0)
        ? position.speed
        : null;
    final isMoving = (speedMps != null && speedMps >= _movingSpeedThresholdMps) ||
        distance >= math.max(effectiveMinDistance, _movingDistanceFallbackMeters);

    final minInterval =
        isMoving ? _minUploadInterval : _minStationaryUploadInterval;

    if (isMoving) {
      if (distance >= effectiveMinDistance) {
        return true;
      }
      return elapsed >= minInterval;
    }
    return elapsed >= minInterval;
  }

  Trip? _activeDayTrip(List<Trip> trips) {
    final dayTrips = trips
        .where((trip) =>
            trip.isDayTrip &&
            trip.tripStatus == 'OPEN' &&
            trip.attendanceId != null)
        .toList()
      ..sort((a, b) {
        final aKey = a.tripStartedAt ?? a.attendanceStartedAt ?? a.createdAt;
        final bKey = b.tripStartedAt ?? b.attendanceStartedAt ?? b.createdAt;
        return bKey.compareTo(aKey);
      });
    return dayTrips.isEmpty ? null : dayTrips.first;
  }
}
