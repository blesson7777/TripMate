enum UserRole { admin, transporter, driver }

UserRole parseUserRole(String role) {
  switch (role.toUpperCase()) {
    case 'ADMIN':
      return UserRole.admin;
    case 'TRANSPORTER':
      return UserRole.transporter;
    default:
      return UserRole.driver;
  }
}

class AppUser {
  const AppUser({
    required this.id,
    required this.username,
    required this.email,
    required this.phone,
    required this.role,
  });

  final int id;
  final String username;
  final String email;
  final String phone;
  final UserRole role;
}

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
    this.transporterId,
    this.driverId,
    this.dieselTrackingEnabled = false,
    this.dieselReadingsEnabled = false,
    this.locationTrackingEnabled = true,
  });

  final String accessToken;
  final String refreshToken;
  final AppUser user;
  final int? transporterId;
  final int? driverId;
  final bool dieselTrackingEnabled;
  final bool dieselReadingsEnabled;
  final bool locationTrackingEnabled;
}
