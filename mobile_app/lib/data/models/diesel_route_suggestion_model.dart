import '../../domain/entities/diesel_route_suggestion.dart';

class DieselRouteSuggestionModel extends DieselRouteSuggestion {
  const DieselRouteSuggestionModel({
    required super.totalKm,
    required super.mode,
    required super.usedFallback,
    required super.returnToStart,
    required super.stops,
  });

  factory DieselRouteSuggestionModel.fromJson(Map<String, dynamic> json) {
    final stopsJson = json['stops'] as List<dynamic>? ?? const [];
    return DieselRouteSuggestionModel(
      totalKm: _asDouble(json['total_km']) ?? 0,
      mode: (json['mode'] ?? 'local').toString(),
      usedFallback: json['used_fallback'] == true,
      returnToStart: json['return_to_start'] == true,
      stops: stopsJson
          .map(
            (item) => DieselRouteSuggestionStopModel.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
    );
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
}

class DieselRouteSuggestionStopModel extends DieselRouteSuggestionStop {
  const DieselRouteSuggestionStopModel({
    required super.originalIndex,
    required super.sequence,
    required super.siteId,
    required super.siteName,
    super.legKm,
    super.cumulativeKm,
    super.isReturnLeg,
  });

  factory DieselRouteSuggestionStopModel.fromJson(Map<String, dynamic> json) {
    return DieselRouteSuggestionStopModel(
      originalIndex: DieselRouteSuggestionModel._asInt(json['original_idx']),
      sequence: DieselRouteSuggestionModel._asInt(json['seq']) ?? 0,
      siteId: (json['site_id'] ?? '').toString(),
      siteName: (json['site_name'] ?? '').toString(),
      legKm: DieselRouteSuggestionModel._asDouble(json['leg_km']),
      cumulativeKm: DieselRouteSuggestionModel._asDouble(json['cumulative_km']),
      isReturnLeg: json['is_return_leg'] == true,
    );
  }
}
