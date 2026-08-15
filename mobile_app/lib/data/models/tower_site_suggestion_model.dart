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
    super.lastOpeningStock,
    super.lastPiuReading,
    super.lastDgHmr,
    super.lastVehicleNumber,
    super.lastDriverName,
    super.lastPurpose,
    super.latestCph,
    super.averageCph,
    super.minCph,
    super.maxCph,
    super.hasCphIssue,
    super.cphIssueReason,
    super.cphIssueCount,
    super.highCphCount,
    super.latestCphFillDate,
    super.latestCphPiuDelta,
    super.latestCphConsumedQty,
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
      lastOpeningStock: _asDouble(json['last_opening_stock']),
      lastPiuReading: _asDouble(json['last_piu_reading']),
      lastDgHmr: _asDouble(json['last_dg_hmr']),
      lastVehicleNumber: (json['last_vehicle_number'] ?? '').toString(),
      lastDriverName: (json['last_driver_name'] ?? '').toString(),
      lastPurpose: (json['last_purpose'] ?? '').toString(),
      latestCph: _asDouble(json['latest_cph']),
      averageCph: _asDouble(json['average_cph']),
      minCph: _asDouble(json['min_cph']),
      maxCph: _asDouble(json['max_cph']),
      hasCphIssue: json['has_cph_issue'] == true,
      cphIssueReason: (json['cph_issue_reason'] ?? '').toString(),
      cphIssueCount: _asInt(json['cph_issue_count']) ?? 0,
      highCphCount: _asInt(json['high_cph_count']) ?? 0,
      latestCphFillDate:
          _parseDate((json['latest_cph_fill_date'] ?? '').toString()),
      latestCphPiuDelta: _asDouble(json['latest_cph_piu_delta']),
      latestCphConsumedQty: _asDouble(json['latest_cph_consumed_qty']),
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
