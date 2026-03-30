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
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': credential,
        'password': password,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<String?> requestDriverLoginOtp({
    required String credential,
    required String password,
  }) async {
    final response = await _apiClient.post(
      '/driver/login/request-otp',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': credential,
        'password': password,
      },
    );

    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<AuthSessionModel> verifyDriverLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    final response = await _apiClient.post(
      '/driver/login/verify-otp',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': credential,
        'password': password,
        'otp': otp.trim(),
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<String?> requestTransporterLoginOtp({
    required String credential,
    required String password,
  }) async {
    final response = await _apiClient.post(
      '/transporter/login/request-otp',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': credential,
        'password': password,
      },
    );

    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<AuthSessionModel> verifyTransporterLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    final response = await _apiClient.post(
      '/transporter/login/verify-otp',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': credential,
        'password': password,
        'otp': otp.trim(),
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
          includeAuth: false,
          allowAuthRetry: false,
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
        'Unable to send OTP. Please try again.',
        statusCode: lastError.statusCode,
        debugMessage: lastError.debugMessage ?? lastError.message,
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
          includeAuth: false,
          allowAuthRetry: false,
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
        'Unable to reset password. Please try again.',
        statusCode: lastError.statusCode,
        debugMessage: lastError.debugMessage ?? lastError.message,
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
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  }) async {
    final response = await _apiClient.post(
      '/transporter/register',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': username,
        'password': password,
        'confirm_password': password,
        'company_name': companyName,
        'email': email,
        'otp': otp.trim(),
        if (phone != null && phone.isNotEmpty) 'phone': phone,
        if (address != null && address.isNotEmpty) 'address': address,
        if (gstin != null && gstin.isNotEmpty) 'gstin': gstin,
        if (pan != null && pan.isNotEmpty) 'pan': pan,
        if (website != null && website.isNotEmpty) 'website': website,
        if (logoBase64 != null && logoBase64.isNotEmpty)
          'logo_base64': logoBase64,
      },
    );

    return AuthSessionModel.fromJson(response as Map<String, dynamic>);
  }

  Future<String?> requestTransporterOtp({
    required String email,
  }) async {
    final response = await _apiClient.post(
      '/transporter/request-otp',
      includeAuth: false,
      allowAuthRetry: false,
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
      includeAuth: false,
      allowAuthRetry: false,
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
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'username': username,
        'password': password,
        'confirm_password': password,
        'email': email,
        'otp': otp.trim(),
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

  Future<String?> requestProfileEmailChangeOtp({
    required String email,
  }) async {
    final response = await _apiClient.post(
      '/profile/request-email-otp',
      body: {
        'email': email,
      },
    );
    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<AppUserModel> updateDriverProfile({
    String? username,
    String? email,
    String? emailOtp,
    String? licenseNumber,
  }) async {
    final response = await _apiClient.patch(
      '/profile',
      body: {
        if (username != null) 'username': username,
        if (email != null) 'email': email,
        if (emailOtp != null && emailOtp.isNotEmpty) 'email_otp': emailOtp,
        if (licenseNumber != null) 'license_number': licenseNumber,
      },
    );

    final map = response as Map<String, dynamic>;
    return AppUserModel.fromJson(map['user'] as Map<String, dynamic>);
  }

  Future<AppUserModel> updateTransporterProfile({
    String? username,
    String? email,
    String? emailOtp,
    String? companyName,
    String? address,
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  }) async {
    final response = await _apiClient.patch(
      '/profile',
      body: {
        if (username != null) 'username': username,
        if (email != null) 'email': email,
        if (emailOtp != null && emailOtp.isNotEmpty) 'email_otp': emailOtp,
        if (companyName != null) 'company_name': companyName,
        if (address != null) 'address': address,
        if (gstin != null) 'gstin': gstin,
        if (pan != null) 'pan': pan,
        if (website != null) 'website': website,
        if (logoBase64 != null) 'logo_base64': logoBase64,
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

  Future<String?> requestAccountDeletionOtp() async {
    final response = await _apiClient.post(
      '/profile/request-account-deletion-otp',
      body: const {},
    );
    final map = response as Map<String, dynamic>;
    return map['debug_otp']?.toString();
  }

  Future<void> requestAccountDeletion({
    required String otp,
    String? note,
  }) async {
    await _apiClient.post(
      '/profile/account-deletion',
      body: {
        'otp': otp,
        if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
      },
    );
  }

  Future<Map<String, dynamic>> refreshSession({
    required String refreshToken,
  }) async {
    final response = await _apiClient.post(
      '/token/refresh',
      includeAuth: false,
      allowAuthRetry: false,
      body: {
        'refresh': refreshToken,
      },
    );
    return response as Map<String, dynamic>;
  }

  Future<void> logout({
    required String refreshToken,
  }) async {
    await _apiClient.post(
      '/logout',
      allowAuthRetry: false,
      body: {
        'refresh': refreshToken,
      },
    );
  }
}
