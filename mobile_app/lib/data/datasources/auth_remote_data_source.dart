import '../../core/network/api_client.dart';
import '../models/app_user_model.dart';
import '../models/driver_profile_model.dart';
import '../models/public_transporter_model.dart';
import '../models/transporter_profile_model.dart';

class AuthRemoteDataSource {
  AuthRemoteDataSource(this._apiClient);

  final ApiClient _apiClient;

  Future<AuthSessionModel> login({
    required String credential,
    required String password,
  }) async {
    final response = await _apiClient.post(
      '/login',
      body: {
        'username': credential,
        'password': password,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<String?> requestPasswordResetOtp({
    required String email,
  }) async {
    final endpoints = <String>[
      '/password/request-otp',
      '/password/request-otp/',
      '/forgot-password/request-otp',
      '/forgot-password/request-otp/',
    ];

    ApiException? lastError;
    for (final endpoint in endpoints) {
      try {
        final response = await _apiClient.post(
          endpoint,
          body: {
            'email': email,
          },
        );
        final map = response as Map<String, dynamic>;
        return map['debug_otp']?.toString();
      } on ApiException catch (exception) {
        lastError = exception;
        if (exception.statusCode != 404 &&
            !exception.message.toLowerCase().contains('html')) {
          rethrow;
        }
      }
    }

    if (lastError != null) {
      throw ApiException(
        '${lastError.message} Forgot-password API route is not available on the server deployment.',
        statusCode: lastError.statusCode,
      );
    }
    throw ApiException('Unable to send OTP. Please try again.');
  }

  Future<void> resetPasswordWithOtp({
    required String email,
    required String otp,
    required String newPassword,
    required String confirmPassword,
  }) async {
    final endpoints = <String>[
      '/password/reset',
      '/password/reset/',
      '/forgot-password/reset',
      '/forgot-password/reset/',
    ];

    ApiException? lastError;
    for (final endpoint in endpoints) {
      try {
        await _apiClient.post(
          endpoint,
          body: {
            'email': email,
            'otp': otp,
            'new_password': newPassword,
            'confirm_password': confirmPassword,
          },
        );
        return;
      } on ApiException catch (exception) {
        lastError = exception;
        if (exception.statusCode != 404 &&
            !exception.message.toLowerCase().contains('html')) {
          rethrow;
        }
      }
    }

    if (lastError != null) {
      throw ApiException(
        '${lastError.message} Forgot-password reset API route is not available on the server deployment.',
        statusCode: lastError.statusCode,
      );
    }
    throw ApiException('Unable to reset password. Please try again.');
  }

  Future<AuthSessionModel> registerTransporter({
    required String username,
    required String password,
    required String companyName,
    required String email,
    required String otp,
    String? phone,
    String? address,
  }) async {
    final response = await _apiClient.post(
      '/transporter/register',
      body: {
        'username': username,
        'password': password,
        'confirm_password': password,
        'company_name': companyName,
        'email': email,
        'otp': otp,
        if (phone != null && phone.isNotEmpty) 'phone': phone,
        if (address != null && address.isNotEmpty) 'address': address,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<String?> requestTransporterOtp({
    required String email,
  }) async {
    final response = await _apiClient.post(
      '/transporter/request-otp',
      body: {
        'email': email,
      },
    );
    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<List<PublicTransporterModel>> getPublicTransporters() async {
    final response = await _apiClient.get('/transporters/public');
    final list = response as List<dynamic>;
    return list
        .map(
          (item) =>
              PublicTransporterModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<String?> requestDriverOtp({
    required String email,
  }) async {
    final response = await _apiClient.post(
      '/driver/request-otp',
      body: {
        'email': email,
      },
    );
    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<AuthSessionModel> registerDriver({
    required String username,
    required String password,
    required String email,
    required String otp,
    required String licenseNumber,
    int? transporterId,
    String? phone,
  }) async {
    final response = await _apiClient.post(
      '/driver/register',
      body: {
        'username': username,
        'password': password,
        'confirm_password': password,
        'email': email,
        'otp': otp,
        'license_number': licenseNumber,
        if (transporterId != null) 'transporter_id': transporterId,
        if (phone != null && phone.isNotEmpty) 'phone': phone,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<DriverProfileModel> getDriverProfile() async {
    final response = await _apiClient.get('/profile');
    return DriverProfileModel.fromJson(response as Map<String, dynamic>);
  }

  Future<TransporterProfileModel> getTransporterProfile() async {
    final response = await _apiClient.get('/profile');
    return TransporterProfileModel.fromJson(response as Map<String, dynamic>);
  }

  Future<AppUserModel> updateDriverProfile({
    String? username,
    String? email,
    String? phone,
    String? licenseNumber,
  }) async {
    final response = await _apiClient.patch(
      '/profile',
      body: {
        if (username != null) 'username': username,
        if (email != null) 'email': email,
        if (phone != null) 'phone': phone,
        if (licenseNumber != null) 'license_number': licenseNumber,
      },
    );

    final map = response as Map<String, dynamic>;
    return AppUserModel.fromJson(map['user'] as Map<String, dynamic>);
  }

  Future<AppUserModel> updateTransporterProfile({
    String? username,
    String? email,
    String? phone,
    String? companyName,
    String? address,
  }) async {
    final response = await _apiClient.patch(
      '/profile',
      body: {
        if (username != null) 'username': username,
        if (email != null) 'email': email,
        if (phone != null) 'phone': phone,
        if (companyName != null) 'company_name': companyName,
        if (address != null) 'address': address,
      },
    );

    final map = response as Map<String, dynamic>;
    return AppUserModel.fromJson(map['user'] as Map<String, dynamic>);
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    await _apiClient.post(
      '/profile/change-password',
      body: {
        'current_password': currentPassword,
        'new_password': newPassword,
        'confirm_password': confirmPassword,
      },
    );
  }
}
