import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/app_distribution.dart';
import '../../../core/models/app_update_info.dart';
import '../../../core/services/app_update_service.dart';
import '../../../domain/entities/app_notification.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'attendance_screen.dart';
import 'trips_screen.dart';

class TransporterNotificationsScreen extends StatefulWidget {
  const TransporterNotificationsScreen({super.key});

  @override
  State<TransporterNotificationsScreen> createState() =>
      _TransporterNotificationsScreenState();
}

class _TransporterNotificationsScreenState
    extends State<TransporterNotificationsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadNotifications(limit: 60);
    });
  }

  Future<void> _refresh() {
    return context.read<TransporterProvider>().loadNotifications(limit: 60);
  }

  Future<void> _markAllRead() async {
    final provider = context.read<TransporterProvider>();
    final ok = await provider.markNotificationsRead();
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok
            ? 'All notifications marked as read.'
            : (provider.error ?? 'Failed')),
      ),
    );
  }

  String _formatDateTime(DateTime value) {
    final local = value.toLocal();
    final day = local.day.toString().padLeft(2, '0');
    final month = local.month.toString().padLeft(2, '0');
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '$day-$month-${local.year} $hour:$minute';
  }

  Color _accentForType(String type) {
    if (type == 'SYSTEM') {
      return const Color(0xFF0A6B6F);
    }
    switch (type) {
      case 'TRIP_STARTED':
        return const Color(0xFF1F8B6A);
      case 'TRIP_CLOSED':
        return const Color(0xFF1E6E91);
      case 'OPEN_TRIP_ALERT':
        return const Color(0xFFD46A2A);
      case 'TRIP_OVERDUE':
        return const Color(0xFFB45309);
      case 'FUEL_ANOMALY':
        return const Color(0xFFDC2626);
      case 'MONTH_END_REMINDER':
        return const Color(0xFF1D4ED8);
      case 'DIESEL_MODULE_TOGGLED':
      case 'SYSTEM_ALERT':
        return const Color(0xFF7C3AED);
      case 'START_DAY_REMINDER':
        return const Color(0xFF7C5E10);
      default:
        return const Color(0xFF4B5563);
    }
  }

  IconData _iconForType(String type) {
    if (type == 'SYSTEM') {
      return Icons.system_update_alt_rounded;
    }
    switch (type) {
      case 'TRIP_STARTED':
        return Icons.play_circle_fill_rounded;
      case 'TRIP_CLOSED':
        return Icons.check_circle_rounded;
      case 'OPEN_TRIP_ALERT':
        return Icons.warning_amber_rounded;
      case 'TRIP_OVERDUE':
        return Icons.timer_outlined;
      case 'FUEL_ANOMALY':
        return Icons.local_gas_station_rounded;
      case 'MONTH_END_REMINDER':
        return Icons.summarize_rounded;
      case 'DIESEL_MODULE_TOGGLED':
        return Icons.tune_rounded;
      case 'SYSTEM_ALERT':
        return Icons.campaign_rounded;
      case 'START_DAY_REMINDER':
        return Icons.alarm_rounded;
      default:
        return Icons.notifications_rounded;
    }
  }

  String? _linkLabelForNotification(AppNotification notification) {
    if ((notification.target ?? '').toUpperCase() == 'APP_UPDATE') {
      return AppDistribution.isPlayStore
          ? 'Managed by Play Store'
          : 'Download Update';
    }
    final type = notification.notificationType;
    switch (type) {
      case 'TRIP_STARTED':
      case 'TRIP_CLOSED':
      case 'OPEN_TRIP_ALERT':
      case 'TRIP_OVERDUE':
        return 'Open Trips';
      case 'START_DAY_REMINDER':
        return 'Open Attendance';
      case 'FUEL_ANOMALY':
        return 'Open Fuel Records';
      case 'MONTH_END_REMINDER':
        return 'Open Reports';
      case 'DIESEL_MODULE_TOGGLED':
        return 'Open Tower Diesel';
      default:
        return null;
    }
  }

  Future<void> _openTargetForNotification({
    required AppNotification notification,
    required String type,
    required String title,
    required String message,
  }) async {
    if ((notification.target ?? '').toUpperCase() == 'APP_UPDATE') {
      if (AppDistribution.isPlayStore) {
        return;
      }
      await AppUpdateService.instance.checkAndPromptForUpdate(
        context: context,
        channel: AppUpdateChannel.transporter,
        forceRecheck: true,
      );
      return;
    }
    Widget? page;
    switch (type) {
      case 'TRIP_STARTED':
      case 'TRIP_CLOSED':
      case 'OPEN_TRIP_ALERT':
      case 'TRIP_OVERDUE':
        page = const TripsScreen();
        break;
      case 'START_DAY_REMINDER':
        page = const AttendanceScreen();
        break;
      default:
        page = null;
    }
    if (!mounted) {
      return;
    }
    if (page == null) {
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      return;
    }
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => page!),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          Consumer<TransporterProvider>(
            builder: (context, provider, _) {
              return TextButton(
                onPressed:
                    provider.loading || provider.unreadNotificationCount == 0
                        ? null
                        : _markAllRead,
                child: const Text('Mark all read'),
              );
            },
          ),
        ],
      ),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.notifications.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }
          if (provider.notifications.isEmpty) {
            return RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 220),
                  Center(child: Text('No notifications yet.')),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: provider.notifications.length,
              itemBuilder: (context, index) {
                final notification = provider.notifications[index];
                final accent = _accentForType(notification.notificationType);
                return StaggeredEntrance(
                  delay: Duration(milliseconds: 50 * index),
                  child: Card(
                    margin: const EdgeInsets.only(bottom: 10),
                    color: notification.isRead ? null : const Color(0xFFF6FBFA),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(20),
                      onTap: () async {
                        if (!notification.isRead) {
                          await context
                              .read<TransporterProvider>()
                              .markNotificationsRead(
                                notificationId: notification.id,
                              );
                          if (!context.mounted) {
                            return;
                          }
                        }
                        await _openTargetForNotification(
                          notification: notification,
                          type: notification.notificationType,
                          title: notification.title,
                          message: notification.message,
                        );
                      },
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: 42,
                              height: 42,
                              decoration: BoxDecoration(
                                color: accent.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Icon(
                                  _iconForType(notification.notificationType),
                                  color: accent),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          notification.title,
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleMedium
                                              ?.copyWith(
                                                fontWeight: FontWeight.w700,
                                              ),
                                        ),
                                      ),
                                      if (!notification.isRead)
                                        Container(
                                          width: 9,
                                          height: 9,
                                          decoration: const BoxDecoration(
                                            color: Color(0xFF0A6B6F),
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Text(notification.message),
                                  const SizedBox(height: 8),
                                  Text(
                                    _formatDateTime(notification.createdAt),
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodySmall
                                        ?.copyWith(
                                          color: Colors.black
                                              .withValues(alpha: 0.58),
                                        ),
                                  ),
                                  if (_linkLabelForNotification(notification) !=
                                      null) ...[
                                    const SizedBox(height: 6),
                                    Align(
                                      alignment: Alignment.centerLeft,
                                      child: TextButton(
                                        onPressed: () async {
                                          await _openTargetForNotification(
                                            notification: notification,
                                            type: notification.notificationType,
                                            title: notification.title,
                                            message: notification.message,
                                          );
                                        },
                                        child: Text(
                                          _linkLabelForNotification(
                                                  notification) ??
                                              'Open',
                                        ),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
