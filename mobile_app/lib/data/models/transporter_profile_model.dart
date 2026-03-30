import '../../domain/entities/transporter_profile.dart';
import 'app_user_model.dart';

class TransporterProfileModel extends TransporterProfile {
  const TransporterProfileModel({
    required super.user,
    required super.id,
    required super.companyName,
    required super.address,
    required super.gstin,
    required super.pan,
    required super.website,
    required super.dieselTrackingEnabled,
    required super.dieselReadingsEnabled,
    required super.locationTrackingEnabled,
    super.logoUrl,
  });

  factory TransporterProfileModel.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'] as Map<String, dynamic>? ?? <String, dynamic>{};
    final transporterJson =
        json['transporter'] as Map<String, dynamic>? ?? <String, dynamic>{};

    return TransporterProfileModel(
      user: AppUserModel.fromJson(userJson),
      id: transporterJson['id'] as int? ?? 0,
      companyName: (transporterJson['company_name'] ?? '').toString(),
      address: (transporterJson['address'] ?? '').toString(),
      gstin: (transporterJson['gstin'] ?? '').toString(),
      pan: (transporterJson['pan'] ?? '').toString(),
      website: (transporterJson['website'] ?? '').toString(),
      dieselTrackingEnabled:
          transporterJson['diesel_tracking_enabled'] as bool? ?? false,
      dieselReadingsEnabled:
          transporterJson['diesel_readings_enabled'] as bool? ?? false,
      locationTrackingEnabled:
          transporterJson['location_tracking_enabled'] as bool? ?? true,
      logoUrl: transporterJson['logo']?.toString(),
    );
  }
}
