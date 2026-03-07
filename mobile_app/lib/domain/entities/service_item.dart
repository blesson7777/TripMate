class ServiceItem {
  const ServiceItem({
    required this.id,
    required this.name,
    this.description = '',
    this.isActive = true,
  });

  final int id;
  final String name;
  final String description;
  final bool isActive;
}
