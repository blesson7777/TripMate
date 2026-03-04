import '../../domain/entities/trip.dart';

class TripModel extends Trip {
  const TripModel({
    required super.id,
    required super.startLocation,
    required super.destination,
    required super.startKm,
    required super.endKm,
    required super.totalKm,
    required super.createdAt,
    super.purpose,
  });

  factory TripModel.fromJson(Map<String, dynamic> json) {
    return TripModel(
      id: json['id'] as int,
      startLocation: (json['start_location'] ?? '').toString(),
      destination: (json['destination'] ?? '').toString(),
      startKm: (json['start_km'] ?? 0) as int,
      endKm: (json['end_km'] ?? 0) as int,
      totalKm: (json['total_km'] ?? 0) as int,
      createdAt: DateTime.parse((json['created_at'] ?? '').toString()),
      purpose: json['purpose']?.toString(),
    );
  }
}
