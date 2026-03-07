import '../../../domain/entities/trip.dart';

enum DriverNotificationType {
  startDayReminder,
  openTripPending,
  openTripAlert,
  endDayReminder,
}

enum DriverNotificationTarget {
  startDay,
  addTrip,
  endDay,
  tripHistory,
}

class DriverAppNotification {
  const DriverAppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.message,
    required this.target,
  });

  final String id;
  final DriverNotificationType type;
  final String title;
  final String message;
  final DriverNotificationTarget target;
}

List<DriverAppNotification> buildDriverActionNotifications({
  required List<Trip> trips,
  required DateTime now,
}) {
  final items = <DriverAppNotification>[];
  final today = now.toLocal();

  bool isSameDate(DateTime? value) {
    if (value == null) {
      return false;
    }
    final local = value.toLocal();
    return local.year == today.year &&
        local.month == today.month &&
        local.day == today.day;
  }

  final todayTrips =
      trips.where((trip) => isSameDate(trip.attendanceDate)).toList();
  final hasStartedDay = todayTrips.any((trip) => trip.isDayTrip);
  final hasOpenDay = todayTrips.any(
    (trip) => trip.isDayTrip && trip.tripStatus == 'OPEN',
  );
  final openDayTrips = todayTrips
      .where((trip) => trip.isDayTrip && trip.tripStatus == 'OPEN')
      .toList();

  if (now.hour >= 10 && !hasStartedDay) {
    items.add(
      const DriverAppNotification(
        id: 'start-day-reminder',
        type: DriverNotificationType.startDayReminder,
        title: 'Start Day Reminder',
        message: 'Mark Start Day before proceeding with trips.',
        target: DriverNotificationTarget.startDay,
      ),
    );
  }

  for (final trip in openDayTrips.take(3)) {
    final route = trip.destination.trim().isEmpty
        ? (trip.attendanceServiceName ?? 'Current duty')
        : '${trip.attendanceServiceName ?? 'Duty'} -> ${trip.destination}';
    items.add(
      DriverAppNotification(
        id: 'open-trip-${trip.id}',
        type: DriverNotificationType.openTripPending,
        title: 'Open Run Pending',
        message: 'Current active run: $route',
        target: DriverNotificationTarget.endDay,
      ),
    );
  }

  if (now.hour >= 18 && openDayTrips.isNotEmpty) {
    items.add(
      const DriverAppNotification(
        id: 'open-trip-alert',
        type: DriverNotificationType.openTripAlert,
        title: 'Run Closure Alert',
        message: 'Your current run is still open after 6:00 PM.',
        target: DriverNotificationTarget.endDay,
      ),
    );
  }

  if (now.hour >= 22 && hasOpenDay) {
    items.add(
      const DriverAppNotification(
        id: 'end-day-reminder',
        type: DriverNotificationType.endDayReminder,
        title: 'End Day Reminder',
        message: 'Your current run is still open. Mark End Day now.',
        target: DriverNotificationTarget.endDay,
      ),
    );
  }

  return items;
}
