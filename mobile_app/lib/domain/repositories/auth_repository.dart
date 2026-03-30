import '../entities/app_user.dart';
import '../entities/driver_profile.dart';
import '../entities/public_transporter.dart';
import '../entities/transporter_profile.dart';

abstract class AuthRepository {
  Future<AuthSession> login({
    required String credential,
    required String password,
  });

  Future<String?> requestDriverLoginOtp({
    required String credential,
    required String password,
  });

  Future<AuthSession> verifyDriverLoginOtp({
    required String credential,
    required String password,
    required String otp,
  });

  Future<String?> requestTransporterLoginOtp({
    required String credential,
    required String password,
  });

  Future<AuthSession> verifyTransporterLoginOtp({
    required String credential,
    required String password,
    required String otp,
  });

  Future<String?> requestPasswordResetOtp({
    required String email,
  });

  Future<void> resetPasswordWithOtp({
    required String email,
    required String otp,
    required String newPassword,
    required String confirmPassword,
  });

  Future<AuthSession> registerTransporter({
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
  });

  Future<String?> requestTransporterOtp({
    required String email,
  });

  Future<List<PublicTransporter>> getPublicTransporters();

  Future<String?> requestDriverOtp({
    required String email,
  });

  Future<AuthSession> registerDriver({
    required String username,
    required String password,
    required String email,
    required String otp,
    required String licenseNumber,
    int? transporterId,
    String? phone,
  });

  Future<AuthSession?> restoreSession();

  Future<DriverProfile> getDriverProfile();

  Future<TransporterProfile> getTransporterProfile();

  Future<String?> requestProfileEmailChangeOtp({
    required String email,
  });

  Future<AppUser> updateDriverProfile({
    String? username,
    String? email,
    String? emailOtp,
    String? licenseNumber,
  });

  Future<AppUser> updateTransporterProfile({
    String? username,
    String? email,
    String? emailOtp,
    String? companyName,
    String? address,
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  });

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
  });

  Future<String?> requestAccountDeletionOtp();

  Future<void> requestAccountDeletion({
    required String otp,
    String? note,
  });

  void logout();

  void clearLocalSession();

  AuthSession? get currentSession;
}
