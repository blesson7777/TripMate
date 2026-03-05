import 'app_user.dart';

class TransporterProfile {
  const TransporterProfile({
    required this.user,
    required this.id,
    required this.companyName,
    required this.address,
  });

  final AppUser user;
  final int id;
  final String companyName;
  final String address;
}
