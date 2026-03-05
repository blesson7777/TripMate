import '../../domain/entities/public_transporter.dart';

class PublicTransporterModel extends PublicTransporter {
  const PublicTransporterModel({
    required super.id,
    required super.companyName,
    required super.address,
  });

  factory PublicTransporterModel.fromJson(Map<String, dynamic> json) {
    return PublicTransporterModel(
      id: (json['id'] ?? 0) as int,
      companyName: (json['company_name'] ?? '').toString(),
      address: (json['address'] ?? '').toString(),
    );
  }
}
