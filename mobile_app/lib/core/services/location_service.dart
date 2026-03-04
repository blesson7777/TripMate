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
      throw Exception('Location services are disabled.');
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      throw Exception('Location permission denied.');
    }

    final position = await Geolocator.getCurrentPosition();
    return LocationResult(
      latitude: position.latitude,
      longitude: position.longitude,
    );
  }
}
