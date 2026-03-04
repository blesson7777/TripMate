class Trip {
  const Trip({
    required this.id,
    required this.startLocation,
    required this.destination,
    required this.startKm,
    required this.endKm,
    required this.totalKm,
    required this.createdAt,
    this.purpose,
  });

  final int id;
  final String startLocation;
  final String destination;
  final int startKm;
  final int endKm;
  final int totalKm;
  final DateTime createdAt;
  final String? purpose;
}
