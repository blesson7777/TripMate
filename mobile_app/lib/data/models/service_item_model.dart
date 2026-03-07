import '../../domain/entities/service_item.dart';

class ServiceItemModel extends ServiceItem {
  const ServiceItemModel({
    required super.id,
    required super.name,
    super.description,
    super.isActive,
  });

  factory ServiceItemModel.fromJson(Map<String, dynamic> json) {
    return ServiceItemModel(
      id: _asInt(json['id']) ?? 0,
      name: (json['name'] ?? '').toString(),
      description: (json['description'] ?? '').toString(),
      isActive: json['is_active'] == true,
    );
  }

  static int? _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    if (value is String) {
      return int.tryParse(value);
    }
    return null;
  }
}
