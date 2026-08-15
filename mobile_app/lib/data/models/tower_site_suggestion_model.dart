import '../../domain/entities/tower_site_suggestion.dart';

class TowerSiteSuggestionModel extends TowerSiteSuggestion {
  const TowerSiteSuggestionModel({
    required super.indusSiteId,
    required super.siteName,
    required super.latitude,
    required super.longitude,
    required super.distanceMeters,
    super.lastFillDate,
    super.lastFilledQuantity,
    super.lastFillRecordId,
    super.lastLogbookPhotoUrl,
  });

  factory TowerSiteSuggestionModel.fromJson(Map<String, dynamic> json) {
    return TowerSiteSuggestionModel(
      indusSiteId: (json['indus_site_id'] ?? '').toString(),
      siteName: (json['site_name'] ?? '').toString(),
      latitude: _asDouble(json['latitude']) ?? 0,
      longitude: _asDouble(json['longitude']) ?? 0,
      distanceMeters: _asDouble(json['distance_m']) ?? 0,
      lastFillDate: _parseDate((json['last_fill_date'] ?? '').toString()),
      lastFilledQuantity: _asDouble(json['last_filled_quantity']),
      lastFillRecordId: _asInt(json['last_fill_record_id']),
      lastLogbookPhotoUrl: (json['last_logbook_photo_url'] ?? '').toString(),
    );
  }

  static double? _asDouble(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is double) {
      return value;
    }
    if (value is int) {
      return value.toDouble();
    }
    return double.tryParse(value.toString());
  }

  static int? _asInt(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is int) {
      return value;
    }
    return int.tryParse(value.toString());
  }

  static DateTime? _parseDate(String raw) {
    if (raw.isEmpty) {
      return null;
    }
    return DateTime.tryParse(raw);
  }
}
