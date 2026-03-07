import 'dart:async';
import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import '../network/api_client.dart';
import 'local_notification_service.dart';

Map<String, dynamic> _payloadFromData(
  Map<String, dynamic> data, {
  String? title,
  String? body,
}) {
  final payload = <String, dynamic>{};
  data.forEach((key, value) {
    payload[key.toString()] = value;
  });
  if (title != null && title.trim().isNotEmpty && payload['title'] == null) {
    payload['title'] = title.trim();
  }
  if (body != null && body.trim().isNotEmpty && payload['message'] == null) {
    payload['message'] = body.trim();
  }
  return payload;
}

String _encodePayload(
  Map<String, dynamic> data, {
  String? title,
  String? body,
}) {
  return jsonEncode(
    _payloadFromData(
      data,
      title: title,
      body: body,
    ),
  );
}

Map<String, dynamic>? _decodePayload(String? payload) {
  final raw = payload?.trim() ?? '';
  if (raw.isEmpty) {
    return null;
  }
  try {
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    if (decoded is Map) {
      return decoded.map(
        (key, value) => MapEntry(key.toString(), value),
      );
    }
  } catch (_) {
    return null;
  }
  return null;
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } catch (_) {
    return;
  }
  await LocalNotificationService.instance.initialize();

  if (message.notification != null) {
    return;
  }

  final title = message.data['title']?.toString().trim();
  final body = message.data['message']?.toString().trim();
  if (title == null || title.isEmpty || body == null || body.isEmpty) {
    return;
  }

  await LocalNotificationService.instance.show(
    id: _notificationId(message),
    title: title,
    body: body,
    payload: _encodePayload(message.data, title: title, body: body),
  );
}

int _notificationId(RemoteMessage message) {
  final source =
      message.messageId ?? '${message.sentTime?.millisecondsSinceEpoch ?? 0}';
  return source.hashCode & 0x7fffffff;
}

class PushNotificationService {
  PushNotificationService._();

  static final PushNotificationService instance = PushNotificationService._();

  bool _initialized = false;
  bool _available = true;
  StreamSubscription<String>? _tokenRefreshSubscription;
  StreamSubscription<RemoteMessage>? _foregroundSubscription;
  StreamSubscription<RemoteMessage>? _onOpenedAppSubscription;
  StreamSubscription<String?>? _localTapSubscription;
  final StreamController<Map<String, dynamic>> _tapEventController =
      StreamController<Map<String, dynamic>>.broadcast();
  ApiClient? _apiClient;
  int? _currentUserId;
  String? _currentVariant;
  String? _lastRegisteredToken;
  int? _lastRegisteredUserId;
  String? _lastRegisteredVariant;
  String? _lastTapSignature;

  Stream<Map<String, dynamic>> get tapEvents => _tapEventController.stream;

  Future<void> initializeBase() async {
    if (_initialized) {
      return;
    }

    try {
      await Firebase.initializeApp();
    } catch (_) {
      _available = false;
      _initialized = true;
      return;
    }
    await LocalNotificationService.instance.initialize();
    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );
    await FirebaseMessaging.instance
        .setForegroundNotificationPresentationOptions(
      alert: true,
      badge: true,
      sound: true,
    );

    _foregroundSubscription =
        FirebaseMessaging.onMessage.listen((message) async {
      final title = message.notification?.title ??
          message.data['title']?.toString() ??
          'TripMate';
      final body = message.notification?.body ??
          message.data['message']?.toString() ??
          'New notification received.';
      await LocalNotificationService.instance.show(
        id: _notificationId(message),
        title: title,
        body: body,
        payload: _encodePayload(
          message.data,
          title: title,
          body: body,
        ),
      );
    });

    _onOpenedAppSubscription =
        FirebaseMessaging.onMessageOpenedApp.listen(_emitFromRemoteMessageTap);

    _localTapSubscription =
        LocalNotificationService.instance.tapPayloadStream.listen((payload) {
      final map = _decodePayload(payload);
      if (map == null) {
        return;
      }
      _emitTapEvent(map);
    });

    final localLaunchPayload =
        LocalNotificationService.instance.consumeLaunchPayload();
    if (localLaunchPayload != null && localLaunchPayload.trim().isNotEmpty) {
      final map = _decodePayload(localLaunchPayload);
      if (map != null) {
        _emitTapEvent(map);
      }
    }

    unawaited(_emitInitialMessageTap());

    _tokenRefreshSubscription =
        FirebaseMessaging.instance.onTokenRefresh.listen(
      (token) async {
        await _registerToken(token);
      },
    );
    _initialized = true;
  }

  Future<void> _emitInitialMessageTap() async {
    final message = await FirebaseMessaging.instance.getInitialMessage();
    if (message == null) {
      return;
    }
    _emitFromRemoteMessageTap(message);
  }

  void _emitFromRemoteMessageTap(RemoteMessage message) {
    final title =
        message.notification?.title ?? message.data['title']?.toString();
    final body =
        message.notification?.body ?? message.data['message']?.toString();
    final payload = _payloadFromData(
      message.data,
      title: title,
      body: body,
    );
    payload['message_id'] = message.messageId;
    payload['sent_time_ms'] = message.sentTime?.millisecondsSinceEpoch;
    _emitTapEvent(payload);
  }

  void _emitTapEvent(Map<String, dynamic> payload) {
    final signature = [
      payload['message_id']?.toString() ?? '',
      payload['notification_id']?.toString() ?? '',
      payload['notification_type']?.toString() ?? '',
      payload['type']?.toString() ?? '',
      payload['title']?.toString() ?? '',
      payload['message']?.toString() ?? '',
      payload['sent_time_ms']?.toString() ?? '',
    ].join('|');
    if (signature == _lastTapSignature) {
      return;
    }
    _lastTapSignature = signature;
    _tapEventController.add(payload);
  }

  Future<bool> syncSession({
    required ApiClient apiClient,
    required int userId,
    required String appVariant,
  }) async {
    await initializeBase();
    if (!_available) {
      return false;
    }
    _apiClient = apiClient;
    _currentUserId = userId;
    _currentVariant = appVariant.toUpperCase();

    final token = await FirebaseMessaging.instance.getToken();
    if (token == null || token.isEmpty) {
      return false;
    }
    return _registerToken(token);
  }

  Future<bool> _registerToken(String token) async {
    final apiClient = _apiClient;
    final userId = _currentUserId;
    final appVariant = _currentVariant;
    if (apiClient == null || userId == null || appVariant == null) {
      return false;
    }

    final alreadyRegistered = _lastRegisteredToken == token &&
        _lastRegisteredUserId == userId &&
        _lastRegisteredVariant == appVariant;
    if (alreadyRegistered) {
      return true;
    }

    try {
      await apiClient.post(
        '/push/register-token',
        body: {
          'token': token,
          'platform': 'ANDROID',
          'app_variant': appVariant,
        },
      );
      _lastRegisteredToken = token;
      _lastRegisteredUserId = userId;
      _lastRegisteredVariant = appVariant;
      return true;
    } catch (_) {
      // Keep login flow non-blocking if token sync fails temporarily.
      return false;
    }
  }

  void dispose() {
    _tokenRefreshSubscription?.cancel();
    _foregroundSubscription?.cancel();
    _onOpenedAppSubscription?.cancel();
    _localTapSubscription?.cancel();
    _tokenRefreshSubscription = null;
    _foregroundSubscription = null;
    _onOpenedAppSubscription = null;
    _localTapSubscription = null;
    _lastTapSignature = null;
    _initialized = false;
  }
}
