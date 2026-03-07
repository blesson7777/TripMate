import 'dart:async';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

@pragma('vm:entry-point')
void _notificationTapBackgroundHandler(NotificationResponse response) {}

class LocalNotificationService {
  LocalNotificationService._();

  static final LocalNotificationService instance = LocalNotificationService._();

  static const AndroidNotificationChannel _channel = AndroidNotificationChannel(
    'tripmate_alerts',
    'TripMate Alerts',
    description: 'Trip, attendance, and operational alerts',
    importance: Importance.high,
  );

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  final StreamController<String?> _tapPayloadController =
      StreamController<String?>.broadcast();
  bool _initialized = false;
  String? _launchPayload;

  Stream<String?> get tapPayloadStream => _tapPayloadController.stream;

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }

    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings();
    const initSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );

    await _plugin.initialize(
      initSettings,
      onDidReceiveNotificationResponse: (response) {
        _tapPayloadController.add(response.payload);
      },
      onDidReceiveBackgroundNotificationResponse:
          _notificationTapBackgroundHandler,
    );

    final launchDetails = await _plugin.getNotificationAppLaunchDetails();
    if (launchDetails?.didNotificationLaunchApp == true) {
      final payload = launchDetails?.notificationResponse?.payload;
      _launchPayload = payload;
      _tapPayloadController.add(payload);
    }

    final androidImpl = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await androidImpl?.createNotificationChannel(_channel);

    _initialized = true;
  }

  Future<void> show({
    required int id,
    required String title,
    required String body,
    String? payload,
  }) async {
    if (!_initialized) {
      await initialize();
    }

    final details = NotificationDetails(
      android: AndroidNotificationDetails(
        _channel.id,
        _channel.name,
        channelDescription: _channel.description,
        importance: Importance.high,
        priority: Priority.high,
        ticker: 'TripMate',
      ),
      iOS: const DarwinNotificationDetails(),
    );

    await _plugin.show(id, title, body, details, payload: payload);
  }

  bool get isInitialized => _initialized;

  String? consumeLaunchPayload() {
    final payload = _launchPayload;
    _launchPayload = null;
    return payload;
  }
}
