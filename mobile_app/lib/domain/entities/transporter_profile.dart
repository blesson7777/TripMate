import 'app_user.dart';

class TransporterProfile {
  const TransporterProfile({
    required this.user,
    required this.id,
    required this.companyName,
    required this.address,
    required this.gstin,
    required this.pan,
    required this.website,
    required this.dieselTrackingEnabled,
    required this.dieselReadingsEnabled,
    required this.locationTrackingEnabled,
    this.logoUrl,
  });

  final AppUser user;
  final int id;
  final String companyName;
  final String address;
  final String gstin;
  final String pan;
  final String website;
  final bool dieselTrackingEnabled;
  final bool dieselReadingsEnabled;
  final bool locationTrackingEnabled;
  final String? logoUrl;
}
