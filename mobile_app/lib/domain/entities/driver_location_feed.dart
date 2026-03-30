import 'driver_location_point.dart';
import 'driver_location_session.dart';

class DriverLocationFeed {
  const DriverLocationFeed({
    required this.date,
    required this.generatedAt,
    required this.sessions,
    required this.mapPoints,
    required this.totalSessions,
    required this.totalMarkers,
  });

  final DateTime date;
  final DateTime generatedAt;
  final List<DriverLocationSession> sessions;
  final List<DriverLocationPoint> mapPoints;
  final int totalSessions;
  final int totalMarkers;
}

