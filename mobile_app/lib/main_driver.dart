import 'dart:async';

import 'package:flutter/material.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:provider/provider.dart';

import 'core/constants/app_distribution.dart';
import 'core/constants/api_constants.dart';
import 'core/models/app_update_info.dart';
import 'core/network/api_client.dart';
import 'core/services/app_update_service.dart';
import 'core/services/driver_diesel_session_service.dart';
import 'core/services/local_notification_service.dart';
import 'core/services/offline_tower_diesel_queue_service.dart';
import 'core/services/push_notification_service.dart';
import 'core/services/trip_tracking_service.dart';
import 'data/datasources/auth_local_data_source.dart';
import 'data/datasources/auth_remote_data_source.dart';
import 'data/datasources/fleet_remote_data_source.dart';
import 'data/repositories/auth_repository_impl.dart';
import 'data/repositories/fleet_repository_impl.dart';
import 'presentation/providers/auth_provider.dart';
import 'presentation/providers/driver_provider.dart';
import 'presentation/screens/common/driver_login_screen.dart';
import 'presentation/screens/driver/driver_dashboard_screen.dart';
import 'presentation/screens/driver/driver_notifications_screen.dart';
import 'presentation/screens/driver/end_day_screen.dart';
import 'presentation/screens/driver/fuel_entry_screen.dart';
import 'presentation/screens/driver/start_day_screen.dart';
import 'presentation/screens/driver/tower_diesel_entry_screen.dart';
import 'presentation/screens/driver/trip_history_screen.dart';
import 'presentation/theme/tripmate_theme.dart';
import 'presentation/widgets/network_connection_gate.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  await PushNotificationService.instance.initializeBase();
  await LocalNotificationService.instance.initialize();
  await DriverDieselSessionService.instance.initialize();
  await OfflineTowerDieselQueueService.instance.initialize();

  final apiClient = ApiClient(baseUrl: ApiConstants.baseUrl);
  final authRepository = AuthRepositoryImpl(
    AuthRemoteDataSource(apiClient),
    AuthLocalDataSource(),
    apiClient,
  );
  final fleetRepository = FleetRepositoryImpl(
    FleetRemoteDataSource(apiClient),
  );
  TripTrackingService.instance.configure(fleetRepository);

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthProvider(authRepository),
        ),
        ChangeNotifierProvider(
          create: (_) => DriverProvider(fleetRepository),
        ),
      ],
      child: TripMateDriverApp(apiClient: apiClient),
    ),
  );
}

class TripMateDriverApp extends StatefulWidget {
  const TripMateDriverApp({
    super.key,
    required this.apiClient,
  });

  final ApiClient apiClient;

  @override
  State<TripMateDriverApp> createState() => _TripMateDriverAppState();
}

class _TripMateDriverAppState extends State<TripMateDriverApp> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  int? _lastSyncedUserId;
  DateTime? _lastPushSyncAt;
  bool _pushSyncInFlight = false;
  Timer? _pushSyncTimer;
  StreamSubscription<Map<String, dynamic>>? _tapSubscription;
  StreamSubscription<void>? _authFailureSubscription;
  Map<String, dynamic>? _pendingTapPayload;
  bool _tapFlushScheduled = false;

  @override
  void initState() {
    super.initState();
    _tapSubscription =
        PushNotificationService.instance.tapEvents.listen(_onTapPayload);
    _authFailureSubscription =
        widget.apiClient.authFailureEvents.listen((_) {
      if (!mounted) {
        return;
      }
      final auth = context.read<AuthProvider>();
      if (!auth.isLoggedIn) {
        return;
      }
      auth.logout();
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_checkForAppUpdate());
    });
    _pushSyncTimer = Timer.periodic(const Duration(seconds: 75), (_) {
      if (!mounted) {
        return;
      }
      final auth = context.read<AuthProvider>();
      if (!auth.isLoggedIn) {
        return;
      }
      unawaited(_syncPush(auth, force: true));
    });
  }

  @override
  void dispose() {
    _pushSyncTimer?.cancel();
    _tapSubscription?.cancel();
    _authFailureSubscription?.cancel();
    super.dispose();
  }

  Future<void> _syncPush(AuthProvider auth, {bool force = false}) async {
    final user = auth.user;
    if (user == null) {
      _lastSyncedUserId = null;
      _lastPushSyncAt = null;
      return;
    }

    if (_pushSyncInFlight) {
      return;
    }

    final now = DateTime.now();
    final userChanged = _lastSyncedUserId != user.id;
    final recentlySynced = _lastPushSyncAt != null &&
        now.difference(_lastPushSyncAt!) < const Duration(seconds: 45);
    if (!force && !userChanged && recentlySynced) {
      return;
    }

    _pushSyncInFlight = true;
    _lastPushSyncAt = now;
    try {
      final synced = await PushNotificationService.instance.syncSession(
        apiClient: widget.apiClient,
        userId: user.id,
        appVariant: 'DRIVER',
      );
      if (synced) {
        _lastSyncedUserId = user.id;
      }
    } finally {
      _pushSyncInFlight = false;
    }
  }

  Future<void> _checkForAppUpdate({bool force = false}) async {
    if (AppDistribution.isPlayStore) {
      return;
    }
    if (!mounted) {
      return;
    }
    BuildContext? dialogContext = _navigatorKey.currentContext;
    if (dialogContext == null) {
      await Future<void>.delayed(const Duration(milliseconds: 500));
      if (!mounted) {
        return;
      }
      dialogContext = _navigatorKey.currentContext;
    }
    if (dialogContext == null || !dialogContext.mounted) {
      return;
    }

    await AppUpdateService.instance.checkAndPromptForUpdate(
      context: dialogContext,
      channel: AppUpdateChannel.driver,
      forceRecheck: force,
    );
  }

  int? _asInt(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value.toString());
  }

  void _onTapPayload(Map<String, dynamic> payload) {
    if (!mounted) {
      return;
    }
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) {
      _pendingTapPayload = payload;
      return;
    }
    _openNotificationTarget(payload);
  }

  void _flushPendingTapIfReady(AuthProvider auth) {
    if (!auth.isLoggedIn || _pendingTapPayload == null || _tapFlushScheduled) {
      return;
    }
    _tapFlushScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _tapFlushScheduled = false;
      if (!mounted) {
        return;
      }
      final payload = _pendingTapPayload;
      _pendingTapPayload = null;
      if (payload == null) {
        return;
      }
      _openNotificationTarget(payload);
    });
  }

  Widget? _targetPageByKey(String target) {
    switch (target) {
      case 'START_DAY':
        return const StartDayScreen();
      case 'ADD_TRIP':
        return const EndDayScreen();
      case 'END_DAY':
        return const EndDayScreen();
      case 'TRIP_HISTORY':
        return const TripHistoryScreen();
      case 'FUEL_ENTRY':
        return const FuelEntryScreen();
      case 'TOWER_DIESEL':
        return const TowerDieselEntryScreen();
      case 'NOTIFICATIONS':
        return const DriverNotificationsScreen();
      default:
        return null;
    }
  }

  void _openNotificationTarget(Map<String, dynamic> payload) {
    final auth = context.read<AuthProvider>();
    if (!auth.isLoggedIn) {
      _pendingTapPayload = payload;
      return;
    }

    final target = (payload['target'] ?? '').toString().toUpperCase().trim();
    final type =
        (payload['notification_type'] ?? '').toString().toUpperCase().trim();
    final notificationId = _asInt(payload['notification_id']);
    if (target == 'APP_UPDATE') {
      if (AppDistribution.isPlayStore) {
        return;
      }
      unawaited(_checkForAppUpdate(force: true));
      return;
    }
    // Driver notifications are acknowledgement-based: open the notifications
    // inbox and let the driver explicitly acknowledge there.
    if (notificationId != null) {
      final navigator = _navigatorKey.currentState;
      if (navigator == null) {
        _pendingTapPayload = payload;
        return;
      }
      navigator.push(
        MaterialPageRoute(builder: (_) => const DriverNotificationsScreen()),
      );
      return;
    }

    Widget? page;
    final targetPage = _targetPageByKey(target);
    if (targetPage != null) {
      page = targetPage;
    } else {
      switch (type) {
        case 'START_DAY_MISSED':
        case 'START_DAY_REMINDER':
          page = const StartDayScreen();
          break;
        case 'TRIP_OVERDUE':
          page = const EndDayScreen();
          break;
        case 'FUEL_ANOMALY':
          page = const FuelEntryScreen();
          break;
        case 'MONTH_END_REMINDER':
          page = const TripHistoryScreen();
          break;
        case 'END_DAY_REMINDER':
          page = const EndDayScreen();
          break;
        default:
          page = null;
      }
    }

    // No dedicated path: just open app and stay on current/home screen.
    if (page == null) {
      return;
    }

    final navigator = _navigatorKey.currentState;
    if (navigator == null) {
      _pendingTapPayload = payload;
      return;
    }
    navigator.push(
      MaterialPageRoute(builder: (_) => page!),
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: 'TripMate Driver',
      debugShowCheckedModeBanner: false,
      theme: TripMateTheme.transporterTheme(),
      builder: (context, child) {
        return NetworkConnectionGate(
          child: SafeArea(
            top: false,
            left: false,
            right: false,
            bottom: true,
            child: child ?? const SizedBox.shrink(),
          ),
        );
      },
      home: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          if (!auth.isReady) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (!auth.isLoggedIn) {
            unawaited(TripTrackingService.instance.stopTracking());
            return const DriverLoginScreen();
          }
          unawaited(_syncPush(auth));
          _flushPendingTapIfReady(auth);
          return const DriverDashboardScreen();
        },
      ),
    );
  }
}
