import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/app_distribution.dart';
import '../../../core/models/app_update_info.dart';
import '../../../core/services/app_update_service.dart';
import '../../../domain/entities/app_notification.dart';
import '../../providers/driver_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'driver_notifications_data.dart';
import 'end_day_screen.dart';
import 'start_day_screen.dart';
import 'trip_history_screen.dart';

class DriverNotificationsScreen extends StatefulWidget {
  const DriverNotificationsScreen({super.key});

  @override
  State<DriverNotificationsScreen> createState() =>
      _DriverNotificationsScreenState();
}

class _DriverNotificationsScreenState extends State<DriverNotificationsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<DriverProvider>();
      provider.loadTrips();
      provider.loadDriverNotifications(limit: 40);
    });
  }

  Future<void> _refresh() async {
    final provider = context.read<DriverProvider>();
    await provider.loadTrips();
    await provider.loadDriverNotifications(limit: 40);
  }

  Future<void> _acknowledgeServerNotification(AppNotification item) async {
    if (item.isRead) {
      return;
    }
    final provider = context.read<DriverProvider>();
    final ok = await provider.markDriverNotificationsRead(
      notificationId: item.id,
    );
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'Notification acknowledged.' : (provider.error ?? 'Failed'),
        ),
      ),
    );
  }

  Future<void> _markAllRead() async {
    final provider = context.read<DriverProvider>();
    final ok = await provider.markDriverNotificationsRead();
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'All notifications marked as read.' : (provider.error ?? 'Failed'),
        ),
      ),
    );
  }

  Color _accent(DriverNotificationType type) {
    switch (type) {
      case DriverNotificationType.startDayReminder:
        return const Color(0xFF0F766E);
      case DriverNotificationType.openTripPending:
        return const Color(0xFFD97706);
      case DriverNotificationType.openTripAlert:
        return const Color(0xFFB45309);
      case DriverNotificationType.endDayReminder:
        return const Color(0xFF1D4ED8);
    }
  }

  IconData _icon(DriverNotificationType type) {
    switch (type) {
      case DriverNotificationType.startDayReminder:
        return Icons.play_circle_outline_rounded;
      case DriverNotificationType.openTripPending:
        return Icons.timelapse_rounded;
      case DriverNotificationType.openTripAlert:
        return Icons.warning_amber_rounded;
      case DriverNotificationType.endDayReminder:
        return Icons.stop_circle_outlined;
    }
  }

  void _openTarget(DriverNotificationTarget target) {
    Widget page;
    switch (target) {
      case DriverNotificationTarget.startDay:
        page = const StartDayScreen();
        break;
      case DriverNotificationTarget.addTrip:
        page = const EndDayScreen();
        break;
      case DriverNotificationTarget.endDay:
        page = const EndDayScreen();
        break;
      case DriverNotificationTarget.tripHistory:
        page = const TripHistoryScreen();
        break;
    }

    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => page),
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

  Future<void> _handleServerNotificationTap(AppNotification item) async {
    if (!item.isRead) {
      await _acknowledgeServerNotification(item);
    }
    if (!mounted) {
      return;
    }
    if ((item.target ?? '').toUpperCase() == 'APP_UPDATE') {
      if (AppDistribution.isPlayStore) {
        return;
      }
      await AppUpdateService.instance.checkAndPromptForUpdate(
        context: context,
        channel: AppUpdateChannel.driver,
        forceRecheck: true,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          Consumer<DriverProvider>(
            builder: (context, provider, _) {
              return TextButton(
                onPressed: provider.loading || provider.unreadServerNotificationCount == 0
                    ? null
                    : _markAllRead,
                child: const Text('Mark all read'),
              );
            },
          ),
        ],
      ),
      body: Consumer<DriverProvider>(
        builder: (context, provider, _) {
          final reminderItems = buildDriverActionNotifications(
            trips: provider.trips,
            now: DateTime.now(),
          );
          final serverItems = provider.serverNotifications;

          if (provider.loading &&
              provider.trips.isEmpty &&
              serverItems.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          if (reminderItems.isEmpty && serverItems.isEmpty) {
            return RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 220),
                  Center(child: Text('No notifications right now.')),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                if (serverItems.isNotEmpty) ...[
                  Text(
                    'Driver Alerts',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  ...List.generate(serverItems.length, (index) {
                    final item = serverItems[index];
                    return StaggeredEntrance(
                      delay: Duration(milliseconds: 40 * index),
                      child: Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        color: item.isRead ? null : const Color(0xFFF6FBFA),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(20),
                          onTap: () => _handleServerNotificationTap(item),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      width: 42,
                                      height: 42,
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF7C3AED)
                                            .withValues(alpha: 0.14),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Icon(
                                        (item.target ?? '').toUpperCase() == 'APP_UPDATE'
                                            ? Icons.system_update_alt_rounded
                                            : Icons.campaign_rounded,
                                        color: const Color(0xFF7C3AED),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Text(
                                        item.title,
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                    if (!item.isRead)
                                      Container(
                                        width: 8,
                                        height: 8,
                                        margin: const EdgeInsets.only(top: 6),
                                        decoration: const BoxDecoration(
                                          color: Color(0xFF0A6B6F),
                                          shape: BoxShape.circle,
                                        ),
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Text(item.message),
                                const SizedBox(height: 4),
                                Text(
                                  _formatDateTime(item.createdAt),
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodySmall
                                      ?.copyWith(color: Colors.black54),
                                ),
                                const SizedBox(height: 10),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: (item.target ?? '').toUpperCase() == 'APP_UPDATE'
                                      ? (AppDistribution.isPlayStore
                                          ? const Chip(
                                              label: Text('Managed by Play Store'),
                                              visualDensity: VisualDensity.compact,
                                            )
                                          : FilledButton.tonal(
                                              onPressed: () =>
                                                  _handleServerNotificationTap(item),
                                              child: const Text('Open Update'),
                                            ))
                                      : item.isRead
                                          ? const Chip(
                                              label: Text('Acknowledged'),
                                              visualDensity: VisualDensity.compact,
                                            )
                                          : FilledButton.tonal(
                                              onPressed: () =>
                                                  _acknowledgeServerNotification(item),
                                              child: const Text('Acknowledge'),
                                            ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                  const SizedBox(height: 10),
                ],
                if (reminderItems.isNotEmpty) ...[
                  Text(
                    'Trip Reminders',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  ...List.generate(reminderItems.length, (index) {
                    final item = reminderItems[index];
                    final accent = _accent(item.type);
                    return StaggeredEntrance(
                      delay: Duration(milliseconds: 40 * index),
                      child: Card(
                        margin: const EdgeInsets.only(bottom: 10),
                        child: ListTile(
                          onTap: () => _openTarget(item.target),
                          leading: Container(
                            width: 42,
                            height: 42,
                            decoration: BoxDecoration(
                              color: accent.withValues(alpha: 0.14),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(_icon(item.type), color: accent),
                          ),
                          title: Text(
                            item.title,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(item.message),
                          trailing: const Icon(
                            Icons.arrow_forward_ios_rounded,
                            size: 16,
                          ),
                        ),
                      ),
                    );
                  }),
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}
