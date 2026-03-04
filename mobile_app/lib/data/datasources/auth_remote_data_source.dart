import '../../core/network/api_client.dart';
import '../models/app_user_model.dart';

class AuthRemoteDataSource {
  AuthRemoteDataSource(this._apiClient);

  final ApiClient _apiClient;

  Future<AuthSessionModel> login({
    required String username,
    required String password,
  }) async {
    final response = await _apiClient.post(
      '/login',
      body: {
        'username': username,
        'password': password,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }
}
