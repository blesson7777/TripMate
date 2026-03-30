import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DriverDieselSessionService {
  DriverDieselSessionService._();

  static final DriverDieselSessionService instance =
      DriverDieselSessionService._();

  static const String _activeDieselTripKey =
      'driver_active_diesel_trip_started';

  final ValueNotifier<bool> activeDieselTripStarted = ValueNotifier(false);
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    activeDieselTripStarted.value =
        prefs.getBool(_activeDieselTripKey) ?? false;
    _initialized = true;
  }

  Future<void> setActiveDieselTripStarted(bool value) async {
    await initialize();
    if (activeDieselTripStarted.value == value) {
      return;
    }
    activeDieselTripStarted.value = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_activeDieselTripKey, value);
  }

  Future<void> clear() async {
    await setActiveDieselTripStarted(false);
  }
}
