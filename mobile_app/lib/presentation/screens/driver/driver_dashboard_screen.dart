import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/services/local_notification_service.dart';
import '../../../core/services/notification_permission_service.dart';
import '../../../domain/entities/app_notification.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';
import '../../../domain/entities/trip.dart';
import '../../widgets/staggered_entrance.dart';
import 'driver_notifications_data.dart';
import 'driver_notifications_screen.dart';
import 'driver_profile_screen.dart';
import 'end_day_screen.dart';
import 'fuel_entry_screen.dart';
import 'start_day_screen.dart';
import 'tower_diesel_entry_screen.dart';
import 'tower_site_map_screen.dart';
import 'trip_history_screen.dart';

class DriverDashboardScreen extends StatefulWidget {
  const DriverDashboardScreen({super.key});

  @override
  State<DriverDashboardScreen> createState() => _DriverDashboardScreenState();
}

class _DriverDashboardScreenState extends State<DriverDashboardScreen> {
  final _notificationPermissionService = NotificationPermissionService();
  Timer? _tripPoller;
  bool _notificationPermissionDenied = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _bootstrap();
    });
    _tripPoller = Timer.periodic(const Duration(seconds: 45), (_) {
      _pollDriverUpdates();
    });
  }

  @override
  void dispose() {
    _tripPoller?.cancel();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final authProvider = context.read<AuthProvider>();
    final driverProvider = context.read<DriverProvider>();
    await Future.wait([
      authProvider.loadDriverProfile(),
      driverProvider.loadTrips(),
      driverProvider.loadDriverNotifications(limit: 40),
    ]);
    await _ensureNotificationPermission();
    if (!mounted) {
      return;
    }
    await _checkTimeBasedDriverReminders(driverProvider.trips);
    await _checkAdminBroadcastNotifications(driverProvider.serverNotifications);
  }

  Future<void> _refreshDashboard() async {
    if (!mounted) {
      return;
    }
    final authProvider = context.read<AuthProvider>();
    final driverProvider = context.read<DriverProvider>();
    await Future.wait([
      authProvider.loadDriverProfile(),
      driverProvider.loadTrips(force: true),
      driverProvider.loadDriverNotifications(limit: 40, force: true),
    ]);
    if (!mounted) {
      return;
    }
    await _checkTimeBasedDriverReminders(driverProvider.trips);
    await _checkAdminBroadcastNotifications(driverProvider.serverNotifications);
  }

  Future<void> _pollDriverUpdates() async {
    if (!mounted) {
      return;
    }
    final driverProvider = context.read<DriverProvider>();
    await Future.wait([
      driverProvider.loadTrips(silent: true),
      driverProvider.loadDriverNotifications(limit: 40, silent: true),
    ]);
    if (!mounted) {
      return;
    }
    await _checkTimeBasedDriverReminders(driverProvider.trips);
    await _checkAdminBroadcastNotifications(driverProvider.serverNotifications);
  }

  Future<void> _ensureNotificationPermission() async {
    final granted = await _notificationPermissionService.ensurePermission();
    if (!mounted) {
      return;
    }
    setState(() {
      _notificationPermissionDenied = !granted;
    });
    if (granted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text(
          'Enable notifications and background data for live trip alerts.',
        ),
        action: SnackBarAction(
          label: 'Settings',
          onPressed: _openNotificationSettings,
        ),
      ),
    );
  }

  Future<void> _openNotificationSettings() async {
    await _notificationPermissionService.openAppPermissionSettings();
    final granted = await _notificationPermissionService.isPermissionGranted();
    if (!mounted) {
      return;
    }
    setState(() {
      _notificationPermissionDenied = !granted;
    });
  }

  String _todayKey() {
    final now = DateTime.now();
    return '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
  }

  Future<void> _checkTimeBasedDriverReminders(List<Trip> trips) async {
    final now = DateTime.now();
    final prefs = await SharedPreferences.getInstance();
    final today = _todayKey();
    final reminders = buildDriverActionNotifications(
      trips: trips,
      now: now,
    );
    final hasStartDayReminder = reminders.any(
      (item) => item.type == DriverNotificationType.startDayReminder,
    );
    final hasOpenTripAlert = reminders.any(
      (item) => item.type == DriverNotificationType.openTripAlert,
    );
    final hasEndDayReminder = reminders.any(
      (item) => item.type == DriverNotificationType.endDayReminder,
    );

    if (hasStartDayReminder) {
      final shownForDate = prefs.getString('driver_start_day_reminder_shown');
      if (shownForDate != today && mounted) {
        if (!_notificationPermissionDenied) {
          await LocalNotificationService.instance.show(
            id: 700001,
            title: 'Start Day Reminder',
            body: 'Mark Start Day before proceeding with trips.',
            payload: jsonEncode(
              {
                'type': 'DRIVER_NOTIFICATION',
                'notification_type': 'START_DAY_MISSED',
                'target': 'START_DAY',
              },
            ),
          );
        }
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content:
                Text('Reminder: Mark Start Day before proceeding with trips.'),
          ),
        );
        await prefs.setString('driver_start_day_reminder_shown', today);
      }
    }

    if (hasOpenTripAlert) {
      final shownForDate = prefs.getString('driver_open_trip_alert_shown');
      if (shownForDate != today && mounted) {
        if (!_notificationPermissionDenied) {
          await LocalNotificationService.instance.show(
            id: 700002,
            title: 'Trip Closure Alert',
            body: 'One of your trips is still open after 6:00 PM.',
            payload: jsonEncode(
              {
                'type': 'DRIVER_NOTIFICATION',
                'notification_type': 'TRIP_OVERDUE',
                'target': 'ADD_TRIP',
              },
            ),
          );
        }
        if (!mounted) {
          return;
        }
        showDialog<void>(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Trip Closure Alert'),
            content: const Text(
                'One of your trips is still open after 6:00 PM. Please close it.'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('OK'),
              ),
            ],
          ),
        );
        await prefs.setString('driver_open_trip_alert_shown', today);
      }
    }

    if (hasEndDayReminder) {
      final shownForDate = prefs.getString('driver_end_day_reminder_shown');
      if (shownForDate != today && mounted) {
        if (!_notificationPermissionDenied) {
          await LocalNotificationService.instance.show(
            id: 700003,
            title: 'End Day Reminder',
            body: 'All trips are closed. Mark End Day now.',
            payload: jsonEncode(
              {
                'type': 'DRIVER_NOTIFICATION',
                'notification_type': 'END_DAY_REMINDER',
                'target': 'END_DAY',
              },
            ),
          );
        }
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Reminder: Mark End Day to complete today.'),
          ),
        );
        await prefs.setString('driver_end_day_reminder_shown', today);
      }
    }
  }

  Future<void> _checkAdminBroadcastNotifications(
    List<AppNotification> notifications,
  ) async {
    if (notifications.isEmpty) {
      return;
    }
    final latest = notifications.first;
    final prefs = await SharedPreferences.getInstance();
    final lastId = prefs.getInt('driver_last_admin_alert_id');
    if (lastId == latest.id) {
      return;
    }

    if (!_notificationPermissionDenied) {
      await LocalNotificationService.instance.show(
        id: 700200 + (latest.id % 1000),
        title: latest.title,
        body: latest.message,
        payload: jsonEncode(
          {
            'type': 'DRIVER_NOTIFICATION',
            'notification_id': latest.id,
            'notification_type': latest.notificationType,
            if (latest.target != null && latest.target!.trim().isNotEmpty)
              'target': latest.target,
          },
        ),
      );
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Admin alert: ${latest.title}')),
      );
    }
    await prefs.setInt('driver_last_admin_alert_id', latest.id);
  }

  bool _containsDieselKeyword(String? value) {
    final normalized = (value ?? '').trim().toLowerCase();
    if (normalized.isEmpty) {
      return false;
    }
    return normalized.contains('diesel');
  }

  bool _hasActiveDieselDayTrip(List<Trip> trips) {
    return trips.any((trip) {
      final isOpenDayTrip = trip.isDayTrip &&
          (trip.tripStatus ?? '').toUpperCase() == 'OPEN';
      if (!isOpenDayTrip) {
        return false;
      }
      return _containsDieselKeyword(trip.attendanceServiceName) ||
          _containsDieselKeyword(trip.attendanceServicePurpose) ||
          _containsDieselKeyword(trip.purpose);
    });
  }

  Trip? _activeDayTrip(List<Trip> trips) {
    final items = trips
        .where((trip) => trip.isDayTrip && (trip.tripStatus ?? '').toUpperCase() == 'OPEN')
        .toList()
      ..sort((a, b) {
        final aKey = a.tripStartedAt ?? a.createdAt;
        final bKey = b.tripStartedAt ?? b.createdAt;
        return bKey.compareTo(aKey);
      });
    return items.isEmpty ? null : items.first;
  }

  @override
  Widget build(BuildContext context) {
    final driverTrips = context.select((DriverProvider driver) => driver.trips);
    final tripNotifications = buildDriverActionNotifications(
      trips: driverTrips,
      now: DateTime.now(),
    );
    final unreadServerNotifications = context.select(
      (DriverProvider driver) => driver.unreadServerNotificationCount,
    );
    final notificationCount =
        tripNotifications.length + unreadServerNotifications;
    final username =
        context.select((AuthProvider auth) => auth.user?.username ?? 'Driver');
    final transporterName = context.select(
      (AuthProvider auth) =>
          auth.driverProfile?.transporterCompanyName?.trim() ?? '',
    );
    final dieselEnabled = context.select(
      (AuthProvider auth) => auth.driverProfile?.dieselTrackingEnabled ?? false,
    );
    final canOpenTowerDiesel = dieselEnabled && _hasActiveDieselDayTrip(driverTrips);
    final activeDayTrip = _activeDayTrip(driverTrips);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refreshDashboard,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Container(
                padding: const EdgeInsets.fromLTRB(18, 56, 18, 28),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      Color(0xFF0A6B6F),
                      Color(0xFF198288),
                    ],
                  ),
                  borderRadius: BorderRadius.vertical(
                    bottom: Radius.circular(34),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          padding: const EdgeInsets.all(8),
                          child: Image.asset(
                            'assets/branding/tripmate_icon.png',
                            width: 36,
                            height: 36,
                          ),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Text(
                            'TripMate Driver',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 20,
                            ),
                          ),
                        ),
                        Stack(
                          clipBehavior: Clip.none,
                          children: [
                            IconButton(
                              onPressed: () => _openPage(
                                context,
                                const DriverNotificationsScreen(),
                              ),
                              icon: const Icon(
                                Icons.notifications_none_rounded,
                                color: Colors.white,
                              ),
                            ),
                            if (notificationCount > 0)
                              Positioned(
                                right: 6,
                                top: 6,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 5,
                                    vertical: 2,
                                  ),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFE08D3C),
                                    borderRadius: BorderRadius.circular(9),
                                  ),
                                  constraints:
                                      const BoxConstraints(minWidth: 18),
                                  child: Text(
                                    notificationCount > 99
                                        ? '99+'
                                        : '$notificationCount',
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                        IconButton(
                          onPressed: () =>
                              _openPage(context, const DriverProfileScreen()),
                          icon: const Icon(Icons.account_circle_outlined,
                              color: Colors.white),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Welcome, $username',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 22,
                      ),
                    ),
                    const SizedBox(height: 4),
                    if (transporterName.isNotEmpty)
                      Text(
                        'Transporter: $transporterName',
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.9),
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    if (transporterName.isNotEmpty) const SizedBox(height: 4),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(14, 16, 14, 20),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_notificationPermissionDenied) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.orange.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.orange.withValues(alpha: 0.4),
                          ),
                        ),
                        child: Row(
                          children: [
                            const Icon(
                              Icons.notifications_off_outlined,
                              color: Color(0xFFB85C00),
                            ),
                            const SizedBox(width: 10),
                            const Expanded(
                              child: Text(
                                'Notifications are disabled. Enable notification/background access for live updates.',
                              ),
                            ),
                            TextButton(
                              onPressed: _openNotificationSettings,
                              child: const Text('Enable'),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                    Text(
                      'Actions',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 10),
                    if (activeDayTrip != null) ...[
                      Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        color: const Color(0xFFF2F9FA),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Current Active Run',
                                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                              const SizedBox(height: 8),
                              Text('Service: ${activeDayTrip.attendanceServiceName ?? '-'}'),
                              Text('Vehicle: ${activeDayTrip.vehicleNumber ?? '-'}'),
                              Text('Opening KM: ${activeDayTrip.startKm}'),
                              if (activeDayTrip.destination.trim().isNotEmpty)
                                Text('Destination: ${activeDayTrip.destination}'),
                              const SizedBox(height: 10),
                              FilledButton.icon(
                                onPressed: () => _openPage(context, const EndDayScreen()),
                                icon: const Icon(Icons.stop_circle_outlined),
                                label: const Text('Close Current Run'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                    _ActionCard(
                      title: 'Start Day',
                      subtitle: 'Attendance + odometer + location',
                      icon: Icons.play_circle_fill_rounded,
                      accent: const Color(0xFF0A6B6F),
                      delay: const Duration(milliseconds: 120),
                      onTap: () => _openPage(context, const StartDayScreen()),
                    ),
                    _ActionCard(
                      title: 'Vehicle Fuel Entry',
                      subtitle: 'Quantity + rate + odometer',
                      icon: Icons.local_gas_station_rounded,
                      accent: const Color(0xFFCF6E41),
                      delay: const Duration(milliseconds: 180),
                      onTap: () => _openPage(context, const FuelEntryScreen()),
                    ),
                    if (dieselEnabled)
                      _ActionCard(
                        title: 'Tower Diesel Filling',
                        subtitle: canOpenTowerDiesel
                            ? 'Separate tower logbook module'
                            : 'Available only during an active diesel-filling trip',
                        icon: Icons.factory_outlined,
                        accent: const Color(0xFF0F766E),
                        delay: const Duration(milliseconds: 240),
                        enabled: canOpenTowerDiesel,
                        onTap: canOpenTowerDiesel
                            ? () => _openPage(
                                  context,
                                  const TowerDieselEntryScreen(),
                                )
                            : null,
                      ),
                    if (dieselEnabled)
                      _ActionCard(
                        title: 'Tower Site Map',
                        subtitle: 'Search tower sites and navigate with maps',
                        icon: Icons.map_outlined,
                        accent: const Color(0xFF15616D),
                        delay: const Duration(milliseconds: 270),
                        onTap: () =>
                            _openPage(context, const TowerSiteMapScreen()),
                      ),
                    _ActionCard(
                      title: 'End Day',
                      subtitle: 'Close attendance with end odometer',
                      icon: Icons.stop_circle_rounded,
                      accent: const Color(0xFF228B8D),
                      delay: Duration(milliseconds: dieselEnabled ? 330 : 240),
                      onTap: () => _openPage(context, const EndDayScreen()),
                    ),
                    _ActionCard(
                      title: 'Trip History',
                      subtitle: 'Review your previous trips',
                      icon: Icons.history_rounded,
                      accent: const Color(0xFF15616D),
                      delay: Duration(milliseconds: dieselEnabled ? 390 : 300),
                      onTap: () =>
                          _openPage(context, const TripHistoryScreen()),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _openPage(BuildContext context, Widget page) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => page),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.accent,
    required this.delay,
    this.onTap,
    this.enabled = true,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final Color accent;
  final VoidCallback? onTap;
  final Duration delay;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final effectiveAccent =
        enabled ? accent : accent.withValues(alpha: 0.45);
    return StaggeredEntrance(
      delay: delay,
      child: _AnimatedPressCard(
        onTap: enabled ? onTap : null,
        child: Opacity(
          opacity: enabled ? 1 : 0.64,
          child: Card(
            margin: const EdgeInsets.only(bottom: 10),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
              child: Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          effectiveAccent,
                          effectiveAccent.withValues(alpha: 0.78),
                        ],
                      ),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Icon(icon, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          subtitle,
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: Colors.black.withValues(alpha: 0.6),
                                  ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    enabled
                        ? Icons.arrow_forward_ios_rounded
                        : Icons.lock_outline_rounded,
                    size: 16,
                    color: Colors.black.withValues(alpha: enabled ? 0.72 : 0.38),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AnimatedPressCard extends StatefulWidget {
  const _AnimatedPressCard({
    required this.onTap,
    required this.child,
  });

  final VoidCallback? onTap;
  final Widget child;

  @override
  State<_AnimatedPressCard> createState() => _AnimatedPressCardState();
}

class _AnimatedPressCardState extends State<_AnimatedPressCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedScale(
      scale: _pressed ? 0.985 : 1,
      duration: const Duration(milliseconds: 110),
      curve: Curves.easeOut,
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: widget.onTap,
        onHighlightChanged: widget.onTap == null
            ? null
            : (value) {
          setState(() {
            _pressed = value;
          });
        },
        child: widget.child,
      ),
    );
  }
}
