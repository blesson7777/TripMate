import '../../domain/entities/transporter_profile.dart';
import 'app_user_model.dart';

class TransporterProfileModel extends TransporterProfile {
  const TransporterProfileModel({
    required super.user,
    required super.id,
    required super.companyName,
    required super.address,
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
    );
  }
}
