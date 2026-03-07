class AppNotification {
  const AppNotification({
    required this.id,
    required this.notificationType,
    required this.title,
    required this.message,
    this.target,
    this.driverId,
    this.driverName,
    this.tripId,
    required this.isRead,
    required this.createdAt,
  });

  final int id;
  final String notificationType;
  final String title;
  final String message;
  final String? target;
  final int? driverId;
  final String? driverName;
  final int? tripId;
  final bool isRead;
  final DateTime createdAt;
}
