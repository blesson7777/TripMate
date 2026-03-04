import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/app_user.dart';
import '../../domain/repositories/auth_repository.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider(this._authRepository);

  final AuthRepository _authRepository;

  AuthSession? _session;
  bool _isLoading = false;
  String? _error;

  AuthSession? get session => _session;
  AppUser? get user => _session?.user;
  bool get isLoggedIn => _session != null;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<bool> login({
    required String username,
    required String password,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.login(username: username, password: password);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Login failed. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void logout() {
    _authRepository.logout();
    _session = null;
    _error = null;
    notifyListeners();
  }
}
