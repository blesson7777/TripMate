import 'dart:async';
import 'dart:io';

import 'package:geolocator/geolocator.dart';

class LocationResult {
  const LocationResult({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

class LocationService {
  Future<LocationPermission> ensureTrackingPermission() async {
    var serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      await Geolocator.openLocationSettings();
      throw Exception(
        'Location services are disabled. Enable GPS for live trip tracking.',
      );
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.deniedForever) {
      await Geolocator.openAppSettings();
      throw Exception(
        'Location permission denied permanently. Allow location in app settings for trip tracking.',
      );
    }

    if (permission == LocationPermission.denied) {
      throw Exception(
          'Location permission denied. Please allow location access.');
    }

    return permission;
  }

  Future<LocationResult> getCurrentLocation() async {
    await ensureTrackingPermission();

    Position position;
    try {
      position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
    } on TimeoutException {
      final lastKnown = await Geolocator.getLastKnownPosition();
      if (lastKnown != null) {
        position = lastKnown;
      } else {
        throw Exception(
          'Could not get GPS location in time. Move to open sky and try again.',
        );
      }
    } on LocationServiceDisabledException {
      await Geolocator.openLocationSettings();
      throw Exception(
        'Location service is off. We opened location settings, please enable GPS and try again.',
      );
    } on PermissionDeniedException {
      throw Exception(
        'Location permission denied. Please allow location access and try again.',
      );
    } catch (_) {
      throw Exception(
        'Unable to get location. Please enable GPS and try again.',
      );
    }

    return LocationResult(
      latitude: position.latitude,
      longitude: position.longitude,
    );
  }

  Stream<Position> watchTripPositions() {
    final settings = Platform.isAndroid
        ? AndroidSettings(
            accuracy: LocationAccuracy.high,
            distanceFilter: 75,
            intervalDuration: const Duration(seconds: 60),
            foregroundNotificationConfig: const ForegroundNotificationConfig(
              notificationTitle: 'TripMate is monitoring your trip location',
              notificationText:
                  'Location tracking stays active while your trip is open.',
              enableWakeLock: true,
            ),
          )
        : const LocationSettings(
            accuracy: LocationAccuracy.best,
            distanceFilter: 75,
          );
    return Geolocator.getPositionStream(locationSettings: settings);
  }
}
