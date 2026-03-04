import '../../core/network/api_client.dart';
import '../../domain/entities/app_user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../datasources/auth_remote_data_source.dart';

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(this._remoteDataSource, this._apiClient);

  final AuthRemoteDataSource _remoteDataSource;
  final ApiClient _apiClient;
  AuthSession? _session;

  @override
  AuthSession? get currentSession => _session;

  @override
  Future<AuthSession> login({
    required String username,
    required String password,
  }) async {
    final session = await _remoteDataSource.login(
      username: username,
      password: password,
    );
    _session = session;
    _apiClient.setAccessToken(session.accessToken);
    return session;
  }

  @override
  void logout() {
    _session = null;
    _apiClient.setAccessToken(null);
  }
}
