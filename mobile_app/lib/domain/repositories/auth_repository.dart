import '../entities/app_user.dart';

abstract class AuthRepository {
  Future<AuthSession> login({
    required String username,
    required String password,
  });

  void logout();

  AuthSession? get currentSession;
}
