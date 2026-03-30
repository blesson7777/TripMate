import 'dart:io';

import 'package:flutter/services.dart';

import '../constants/api_constants.dart';

class NativeTripTrackingService {
  NativeTripTrackingService._();

  static const MethodChannel _channel =
      MethodChannel('tripmate/trip_tracking_service');

  static Future<bool> start() async {
    if (!Platform.isAndroid) {
      return false;
    }
    try {
      await _channel.invokeMethod<void>(
        'start',
        {
          'baseUrl': ApiConstants.baseUrl,
        },
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) {
      return;
    }
    try {
      await _channel.invokeMethod<void>('stop');
    } catch (_) {
      // Best-effort.
    }
  }
}

