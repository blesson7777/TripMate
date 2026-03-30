class DieselDailyRoutePlan {
  const DieselDailyRoutePlan({
    required this.id,
    required this.planDate,
    required this.status,
    required this.transporterId,
    required this.transporterName,
    required this.vehicleId,
    required this.vehicleNumber,
    required this.stops,
    this.startPoint,
    this.estimatedDistanceKm,
    required this.totalPlannedQty,
    required this.filledStopsCount,
    required this.pendingStopsCount,
  });

  final int id;
  final DateTime planDate;
  final String status;
  final int transporterId;
  final String transporterName;
  final int vehicleId;
  final String vehicleNumber;
  final DieselDailyRouteStartPoint? startPoint;
  final List<DieselDailyRouteStop> stops;
  final double? estimatedDistanceKm;
  final double totalPlannedQty;
  final int filledStopsCount;
  final int pendingStopsCount;

  int get mappedStopsCount => stops
      .where((stop) => stop.latitude != null && stop.longitude != null)
      .length;
}

class DieselDailyRouteStartPoint {
  const DieselDailyRouteStartPoint({
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  final String name;
  final double latitude;
  final double longitude;
}

class DieselDailyRouteStop {
  const DieselDailyRouteStop({
    required this.sequence,
    required this.indusSiteId,
    required this.siteName,
    required this.plannedQty,
    this.latitude,
    this.longitude,
    required this.notes,
    required this.isFilled,
    this.filledRecordId,
    this.filledQty,
    this.filledAt,
    this.filledBy = '',
  });

  final int sequence;
  final String indusSiteId;
  final String siteName;
  final double plannedQty;
  final double? latitude;
  final double? longitude;
  final String notes;
  final bool isFilled;
  final int? filledRecordId;
  final double? filledQty;
  final DateTime? filledAt;
  final String filledBy;

  bool get hasCoordinates => latitude != null && longitude != null;
}
