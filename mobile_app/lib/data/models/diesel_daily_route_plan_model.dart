import '../../domain/entities/diesel_daily_route_plan.dart';

class DieselDailyRoutePlanModel extends DieselDailyRoutePlan {
  const DieselDailyRoutePlanModel({
    required super.id,
    required super.planDate,
    required super.status,
    required super.transporterId,
    required super.transporterName,
    required super.vehicleId,
    required super.vehicleNumber,
    required super.stops,
    super.startPoint,
    super.estimatedDistanceKm,
    required super.totalPlannedQty,
    required super.filledStopsCount,
    required super.pendingStopsCount,
  });

  factory DieselDailyRoutePlanModel.fromJson(Map<String, dynamic> json) {
    final stopsJson = json['stops'] as List<dynamic>? ?? const [];
    return DieselDailyRoutePlanModel(
      id: _asInt(json['id']) ?? 0,
      planDate: DateTime.tryParse((json['plan_date'] ?? '').toString()) ??
          DateTime.now(),
      status: (json['status'] ?? '').toString(),
      transporterId: _asInt(json['transporter_id']) ?? 0,
      transporterName: (json['transporter_name'] ?? '').toString(),
      vehicleId: _asInt(json['vehicle_id']) ?? 0,
      vehicleNumber: (json['vehicle_number'] ?? '').toString(),
      startPoint: _parseStartPoint(json['start_point']),
      stops: stopsJson
          .map(
            (item) => DieselDailyRouteStopModel.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: false),
      estimatedDistanceKm: _asDouble(json['estimated_distance_km']),
      totalPlannedQty: _asDouble(json['total_planned_qty']) ?? 0,
      filledStopsCount: _asInt(json['filled_stops_count']) ?? 0,
      pendingStopsCount: _asInt(json['pending_stops_count']) ?? 0,
    );
  }

  static DieselDailyRouteStartPointModel? _parseStartPoint(dynamic value) {
    if (value is! Map<String, dynamic>) {
      return null;
    }
    return DieselDailyRouteStartPointModel.fromJson(value);
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

class DieselDailyRouteStartPointModel extends DieselDailyRouteStartPoint {
  const DieselDailyRouteStartPointModel({
    required super.name,
    required super.latitude,
    required super.longitude,
  });

  factory DieselDailyRouteStartPointModel.fromJson(Map<String, dynamic> json) {
    return DieselDailyRouteStartPointModel(
      name: (json['name'] ?? '').toString(),
      latitude: DieselDailyRoutePlanModel._asDouble(json['latitude']) ?? 0,
      longitude: DieselDailyRoutePlanModel._asDouble(json['longitude']) ?? 0,
    );
  }
}

class DieselDailyRouteStopModel extends DieselDailyRouteStop {
  const DieselDailyRouteStopModel({
    required super.sequence,
    required super.indusSiteId,
    required super.siteName,
    required super.plannedQty,
    super.latitude,
    super.longitude,
    required super.notes,
    required super.isFilled,
    super.filledRecordId,
    super.filledQty,
    super.filledAt,
    super.filledBy,
  });

  factory DieselDailyRouteStopModel.fromJson(Map<String, dynamic> json) {
    return DieselDailyRouteStopModel(
      sequence: DieselDailyRoutePlanModel._asInt(json['sequence']) ?? 0,
      indusSiteId: (json['indus_site_id'] ?? '').toString(),
      siteName: (json['site_name'] ?? '').toString(),
      plannedQty: DieselDailyRoutePlanModel._asDouble(json['planned_qty']) ?? 0,
      latitude: DieselDailyRoutePlanModel._asDouble(json['latitude']),
      longitude: DieselDailyRoutePlanModel._asDouble(json['longitude']),
      notes: (json['notes'] ?? '').toString(),
      isFilled: json['is_filled'] == true,
      filledRecordId:
          DieselDailyRoutePlanModel._asInt(json['filled_record_id']),
      filledQty: DieselDailyRoutePlanModel._asDouble(json['filled_qty']),
      filledAt: _parseDate((json['filled_at'] ?? '').toString()),
      filledBy: (json['filled_by'] ?? '').toString(),
    );
  }

  static DateTime? _parseDate(String raw) {
    if (raw.trim().isEmpty) {
      return null;
    }
    return DateTime.tryParse(raw);
  }
}
