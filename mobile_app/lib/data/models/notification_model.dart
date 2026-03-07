import '../../domain/entities/app_notification.dart';
import '../../domain/entities/notification_feed.dart';

class AppNotificationModel extends AppNotification {
  const AppNotificationModel({
    required super.id,
    required super.notificationType,
    required super.title,
    required super.message,
    super.target,
    super.driverId,
    super.driverName,
    super.tripId,
    required super.isRead,
    required super.createdAt,
  });

  factory AppNotificationModel.fromJson(Map<String, dynamic> json) {
    return AppNotificationModel(
      id: _asInt(json['id']) ?? 0,
      notificationType: (json['notification_type'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      message: (json['message'] ?? '').toString(),
      target: json['target']?.toString(),
      driverId: _asInt(json['driver']),
      driverName: json['driver_name']?.toString(),
      tripId: _asInt(json['trip']),
      isRead: json['is_read'] == true,
      createdAt: _asDate(json['created_at']) ?? DateTime.now(),
    );
  }

  static int? _asInt(dynamic value) {
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

  static DateTime? _asDate(dynamic value) {
    if (value == null) {
      return null;
    }
    return DateTime.tryParse(value.toString());
  }
}

class NotificationFeedModel extends NotificationFeed {
  const NotificationFeedModel({
    required super.unreadCount,
    required super.items,
  });

  factory NotificationFeedModel.fromJson(Map<String, dynamic> json) {
    final list = json['items'] as List<dynamic>? ?? const [];
    return NotificationFeedModel(
      unreadCount: AppNotificationModel._asInt(json['unread_count']) ?? 0,
      items: list
          .map(
            (item) =>
                AppNotificationModel.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
    );
  }
}
