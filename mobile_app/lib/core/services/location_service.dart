import 'dart:async';

import 'package:geolocator/geolocator.dart';

class LocationResult {
  const LocationResult({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

class LocationService {
  Future<LocationResult> getCurrentLocation() async {
    var serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      await Geolocator.openLocationSettings();
      throw Exception(
        'Location services are disabled. We opened location settings, please enable GPS and try again.',
      );
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.deniedForever) {
      await Geolocator.openAppSettings();
      throw Exception(
        'Location permission denied permanently. We opened app settings, please allow location and try again.',
      );
    }

    if (permission == LocationPermission.denied) {
      throw Exception('Location permission denied. Please allow permission.');
    }

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
    }

    return LocationResult(
      latitude: position.latitude,
      longitude: position.longitude,
    );
  }
}
