class TowerSiteSuggestion {
  const TowerSiteSuggestion({
    required this.indusSiteId,
    required this.siteName,
    required this.latitude,
    required this.longitude,
    required this.distanceMeters,
    this.lastFillDate,
    this.lastFilledQuantity,
    this.lastFillRecordId,
    this.lastLogbookPhotoUrl = '',
    this.lastOpeningStock,
    this.lastPiuReading,
    this.lastDgHmr,
    this.lastVehicleNumber = '',
    this.lastDriverName = '',
    this.lastPurpose = '',
    this.latestCph,
    this.averageCph,
    this.minCph,
    this.maxCph,
    this.hasCphIssue = false,
    this.cphIssueReason = '',
    this.cphIssueCount = 0,
    this.highCphCount = 0,
    this.latestCphFillDate,
    this.latestCphPiuDelta,
    this.latestCphConsumedQty,
  });

  final String indusSiteId;
  final String siteName;
  final double latitude;
  final double longitude;
  final double distanceMeters;
  final DateTime? lastFillDate;
  final double? lastFilledQuantity;
  final int? lastFillRecordId;
  final String lastLogbookPhotoUrl;
  final double? lastOpeningStock;
  final double? lastPiuReading;
  final double? lastDgHmr;
  final String lastVehicleNumber;
  final String lastDriverName;
  final String lastPurpose;
  final double? latestCph;
  final double? averageCph;
  final double? minCph;
  final double? maxCph;
  final bool hasCphIssue;
  final String cphIssueReason;
  final int cphIssueCount;
  final int highCphCount;
  final DateTime? latestCphFillDate;
  final double? latestCphPiuDelta;
  final double? latestCphConsumedQty;
}
