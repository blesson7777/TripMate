import 'app_notification.dart';

class NotificationFeed {
  const NotificationFeed({
    required this.unreadCount,
    required this.items,
  });

  final int unreadCount;
  final List<AppNotification> items;
}
