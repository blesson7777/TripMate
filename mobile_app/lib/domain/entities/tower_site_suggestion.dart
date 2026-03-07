class TowerSiteSuggestion {
  const TowerSiteSuggestion({
    required this.indusSiteId,
    required this.siteName,
    required this.latitude,
    required this.longitude,
    required this.distanceMeters,
    this.lastFillDate,
    this.lastFilledQuantity,
  });

  final String indusSiteId;
  final String siteName;
  final double latitude;
  final double longitude;
  final double distanceMeters;
  final DateTime? lastFillDate;
  final double? lastFilledQuantity;
}
