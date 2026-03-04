import '../../domain/entities/app_user.dart';

class AppUserModel extends AppUser {
  const AppUserModel({
    required super.id,
    required super.username,
    required super.email,
    required super.phone,
    required super.role,
  });

  factory AppUserModel.fromJson(Map<String, dynamic> json) {
    return AppUserModel(
      id: json['id'] as int,
      username: (json['username'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      phone: (json['phone'] ?? '').toString(),
      role: parseUserRole((json['role'] ?? 'DRIVER').toString()),
    );
  }
}

class AuthSessionModel extends AuthSession {
  const AuthSessionModel({
    required super.accessToken,
    required super.refreshToken,
    required super.user,
    super.transporterId,
    super.driverId,
  });

  factory AuthSessionModel.fromJson(Map<String, dynamic> json) {
    return AuthSessionModel(
      accessToken: (json['access'] ?? '').toString(),
      refreshToken: (json['refresh'] ?? '').toString(),
      user: AppUserModel.fromJson(json['user'] as Map<String, dynamic>),
      transporterId: json['transporter_id'] as int?,
      driverId: json['driver_id'] as int?,
    );
  }
}
