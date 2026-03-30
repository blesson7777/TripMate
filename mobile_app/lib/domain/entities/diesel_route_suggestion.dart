class DieselRouteSuggestion {
  const DieselRouteSuggestion({
    required this.totalKm,
    required this.mode,
    required this.usedFallback,
    required this.returnToStart,
    required this.stops,
  });

  final double totalKm;
  final String mode;
  final bool usedFallback;
  final bool returnToStart;
  final List<DieselRouteSuggestionStop> stops;
}

class DieselRouteSuggestionStop {
  const DieselRouteSuggestionStop({
    required this.originalIndex,
    required this.sequence,
    required this.siteId,
    required this.siteName,
    this.legKm,
    this.cumulativeKm,
    this.isReturnLeg = false,
  });

  final int? originalIndex;
  final int sequence;
  final String siteId;
  final String siteName;
  final double? legKm;
  final double? cumulativeKm;
  final bool isReturnLeg;
}
