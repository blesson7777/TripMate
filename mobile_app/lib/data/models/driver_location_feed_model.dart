import '../../domain/entities/driver_location_feed.dart';
import 'driver_location_point_model.dart';
import 'driver_location_session_model.dart';

class DriverLocationFeedModel extends DriverLocationFeed {
  const DriverLocationFeedModel({
    required super.date,
    required super.generatedAt,
    required super.sessions,
    required super.mapPoints,
    required super.totalSessions,
    required super.totalMarkers,
  });

  factory DriverLocationFeedModel.fromJson(Map<String, dynamic> json) {
    DateTime parseDate(dynamic value) {
      final raw = value?.toString();
      if (raw == null || raw.isEmpty) {
        return DateTime.now();
      }
      final parsed = DateTime.tryParse(raw);
      if (parsed != null) {
        return parsed;
      }
      return DateTime.now();
    }

    final sessionsRaw = json['sessions'] as List<dynamic>? ?? const [];
    final pointsRaw = json['map_points'] as List<dynamic>? ?? const [];

    return DriverLocationFeedModel(
      date: parseDate(json['date']),
      generatedAt: parseDate(json['generated_at']),
      sessions: sessionsRaw
          .whereType<Map<String, dynamic>>()
          .map(DriverLocationSessionModel.fromJson)
          .toList(),
      mapPoints: pointsRaw
          .whereType<Map<String, dynamic>>()
          .map(DriverLocationPointModel.fromJson)
          .toList(),
      totalSessions: json['total_sessions'] as int? ?? sessionsRaw.length,
      totalMarkers: json['total_markers'] as int? ?? pointsRaw.length,
    );
  }
}

