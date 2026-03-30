import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../core/services/driver_diesel_session_service.dart';
import '../../domain/entities/app_user.dart';
import '../../domain/entities/driver_profile.dart';
import '../../domain/entities/public_transporter.dart';
import '../../domain/entities/transporter_profile.dart';
import '../../domain/repositories/auth_repository.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider(this._authRepository) {
    initialize();
  }

  final AuthRepository _authRepository;
  static const Duration _profileCacheTtl = Duration(minutes: 2);

  AuthSession? _session;
  bool _isLoading = false;
  bool _isReady = false;
  bool _isInitializing = false;
  String? _error;
  String? _debugOtp;
  DriverProfile? _driverProfile;
  TransporterProfile? _transporterProfile;
  DateTime? _driverProfileLoadedAt;
  DateTime? _transporterProfileLoadedAt;

  AuthSession? get session => _session;
  AppUser? get user => _session?.user;
  bool get isLoggedIn => _session != null;
  bool get isLoading => _isLoading;
  bool get isReady => _isReady;
  String? get error => _error;
  String? get debugOtp => _debugOtp;
  DriverProfile? get driverProfile => _driverProfile;
  TransporterProfile? get transporterProfile => _transporterProfile;

  Future<void> initialize() async {
    if (_isInitializing || _isReady) {
      return;
    }
    _isInitializing = true;
    notifyListeners();

    try {
      _session = await _authRepository.restoreSession();
      final restored = _session;
      if (restored != null) {
        try {
          // Validate saved JWT against current backend. If server changed
          // (new AWS deploy/secret), drop stale session and force re-login.
          if (restored.user.role == UserRole.driver) {
            final profile = await _authRepository.getDriverProfile();
            _driverProfile = profile;
            _driverProfileLoadedAt = DateTime.now();
            _session = AuthSession(
              accessToken: restored.accessToken,
              refreshToken: restored.refreshToken,
              user: restored.user,
              transporterId: restored.transporterId,
              driverId: restored.driverId,
              dieselTrackingEnabled: profile.dieselTrackingEnabled,
              dieselReadingsEnabled: profile.dieselReadingsEnabled,
              locationTrackingEnabled: profile.locationTrackingEnabled,
            );
          } else if (restored.user.role == UserRole.transporter) {
            final profile = await _authRepository.getTransporterProfile();
            _transporterProfile = profile;
            _transporterProfileLoadedAt = DateTime.now();
            _session = AuthSession(
              accessToken: restored.accessToken,
              refreshToken: restored.refreshToken,
              user: restored.user,
              transporterId: restored.transporterId,
              driverId: restored.driverId,
              dieselTrackingEnabled: profile.dieselTrackingEnabled,
              dieselReadingsEnabled: profile.dieselReadingsEnabled,
              locationTrackingEnabled: profile.locationTrackingEnabled,
            );
          }
        } on ApiException catch (exception) {
          final invalidJwt = exception.statusCode == 401;
          if (invalidJwt) {
            _authRepository.logout();
            _session = null;
            _error = 'Session expired. Please login again.';
          }
        }
      }
    } finally {
      _isInitializing = false;
      _isReady = true;
      notifyListeners();
    }
  }

  Future<bool> login({
    required String credential,
    required String password,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.login(
          credential: credential, password: password);
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

  Future<bool> requestDriverLoginOtp({
    required String credential,
    required String password,
  }) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestDriverLoginOtp(
        credential: credential,
        password: password,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send login OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> verifyDriverLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.verifyDriverLoginOtp(
        credential: credential,
        password: password,
        otp: otp,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to verify login OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> requestTransporterLoginOtp({
    required String credential,
    required String password,
  }) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestTransporterLoginOtp(
        credential: credential,
        password: password,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send login OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> verifyTransporterLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.verifyTransporterLoginOtp(
        credential: credential,
        password: password,
        otp: otp,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to verify login OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> requestPasswordResetOtp({required String email}) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestPasswordResetOtp(email: email);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> resetPasswordWithOtp({
    required String email,
    required String otp,
    required String newPassword,
    required String confirmPassword,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _authRepository.resetPasswordWithOtp(
        email: email,
        otp: otp,
        newPassword: newPassword,
        confirmPassword: confirmPassword,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to reset password. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> registerTransporter({
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
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.registerTransporter(
        username: username,
        password: password,
        companyName: companyName,
        email: email,
        otp: otp,
        phone: phone,
        address: address,
        gstin: gstin,
        pan: pan,
        website: website,
        logoBase64: logoBase64,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Registration failed. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> requestTransporterOtp({required String email}) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestTransporterOtp(email: email);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<List<PublicTransporter>> getPublicTransporters() async {
    try {
      return await _authRepository.getPublicTransporters();
    } on ApiException catch (exception) {
      _error = exception.message;
      notifyListeners();
      return const [];
    } catch (_) {
      _error = 'Unable to load transporters.';
      notifyListeners();
      return const [];
    }
  }

  Future<bool> requestDriverOtp({required String email}) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestDriverOtp(email: email);
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> registerDriver({
    required String username,
    required String password,
    required String email,
    required String otp,
    required String licenseNumber,
    int? transporterId,
    String? phone,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session = await _authRepository.registerDriver(
        username: username,
        password: password,
        email: email,
        otp: otp,
        licenseNumber: licenseNumber,
        transporterId: transporterId,
        phone: phone,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Registration failed. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> loadDriverProfile({
    bool force = false,
    bool silent = false,
  }) async {
    if (!force &&
        _driverProfile != null &&
        _driverProfileLoadedAt != null &&
        DateTime.now().difference(_driverProfileLoadedAt!) <= _profileCacheTtl) {
      return true;
    }
    if (!silent) {
      _isLoading = true;
      _error = null;
      notifyListeners();
    }

    try {
      _driverProfile = await _authRepository.getDriverProfile();
      _driverProfileLoadedAt = DateTime.now();
      final existingSession = _session;
      final profile = _driverProfile;
      if (existingSession != null && profile != null) {
        _session = AuthSession(
          accessToken: existingSession.accessToken,
          refreshToken: existingSession.refreshToken,
          user: existingSession.user,
          transporterId: existingSession.transporterId,
          driverId: existingSession.driverId,
          dieselTrackingEnabled: profile.dieselTrackingEnabled,
          dieselReadingsEnabled: profile.dieselReadingsEnabled,
          locationTrackingEnabled: profile.locationTrackingEnabled,
        );
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to load profile. Please try again.';
      return false;
    } finally {
      if (!silent) {
        _isLoading = false;
      }
      notifyListeners();
    }
  }

  Future<bool> loadTransporterProfile({
    bool force = false,
    bool silent = false,
  }) async {
    if (!force &&
        _transporterProfile != null &&
        _transporterProfileLoadedAt != null &&
        DateTime.now().difference(_transporterProfileLoadedAt!) <=
            _profileCacheTtl) {
      return true;
    }
    if (!silent) {
      _isLoading = true;
      _error = null;
      notifyListeners();
    }

    try {
      _transporterProfile = await _authRepository.getTransporterProfile();
      _transporterProfileLoadedAt = DateTime.now();
      final existingSession = _session;
      final profile = _transporterProfile;
      if (existingSession != null && profile != null) {
        _session = AuthSession(
          accessToken: existingSession.accessToken,
          refreshToken: existingSession.refreshToken,
          user: existingSession.user,
          transporterId: existingSession.transporterId,
          driverId: existingSession.driverId,
          dieselTrackingEnabled: profile.dieselTrackingEnabled,
          dieselReadingsEnabled: profile.dieselReadingsEnabled,
          locationTrackingEnabled: profile.locationTrackingEnabled,
        );
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to load profile. Please try again.';
      return false;
    } finally {
      if (!silent) {
        _isLoading = false;
      }
      notifyListeners();
    }
  }

  Future<bool> requestProfileEmailChangeOtp({required String email}) async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestProfileEmailChangeOtp(
        email: email,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send email OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> updateDriverProfile({
    required String username,
    required String email,
    String? emailOtp,
    required String licenseNumber,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedUser = await _authRepository.updateDriverProfile(
        username: username,
        email: email,
        emailOtp: emailOtp,
        licenseNumber: licenseNumber,
      );
      final existingSession = _session;
      if (existingSession != null) {
        _session = AuthSession(
          accessToken: existingSession.accessToken,
          refreshToken: existingSession.refreshToken,
          user: updatedUser,
          transporterId: existingSession.transporterId,
          driverId: existingSession.driverId,
          dieselTrackingEnabled: existingSession.dieselTrackingEnabled,
          dieselReadingsEnabled: existingSession.dieselReadingsEnabled,
          locationTrackingEnabled: existingSession.locationTrackingEnabled,
        );
      }
      _driverProfile = await _authRepository.getDriverProfile();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update profile. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> updateTransporterProfile({
    required String username,
    required String email,
    String? emailOtp,
    required String companyName,
    required String address,
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedUser = await _authRepository.updateTransporterProfile(
        username: username,
        email: email,
        emailOtp: emailOtp,
        companyName: companyName,
        address: address,
        gstin: gstin,
        pan: pan,
        website: website,
        logoBase64: logoBase64,
      );
      final existingSession = _session;
      if (existingSession != null) {
        _session = AuthSession(
          accessToken: existingSession.accessToken,
          refreshToken: existingSession.refreshToken,
          user: updatedUser,
          transporterId: existingSession.transporterId,
          driverId: existingSession.driverId,
          dieselTrackingEnabled: existingSession.dieselTrackingEnabled,
          dieselReadingsEnabled: existingSession.dieselReadingsEnabled,
          locationTrackingEnabled: existingSession.locationTrackingEnabled,
        );
      }
      _transporterProfile = await _authRepository.getTransporterProfile();
      final updatedProfile = _transporterProfile;
      final nextSession = _session;
      if (nextSession != null && updatedProfile != null) {
        _session = AuthSession(
          accessToken: nextSession.accessToken,
          refreshToken: nextSession.refreshToken,
          user: nextSession.user,
          transporterId: nextSession.transporterId,
          driverId: nextSession.driverId,
          dieselTrackingEnabled: updatedProfile.dieselTrackingEnabled,
          dieselReadingsEnabled: updatedProfile.dieselReadingsEnabled,
          locationTrackingEnabled: updatedProfile.locationTrackingEnabled,
        );
      }
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to update profile. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> changePassword({
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _authRepository.changePassword(
        currentPassword: currentPassword,
        newPassword: newPassword,
        confirmPassword: confirmPassword,
      );
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to change password. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> requestAccountDeletionOtp() async {
    _isLoading = true;
    _error = null;
    _debugOtp = null;
    notifyListeners();

    try {
      _debugOtp = await _authRepository.requestAccountDeletionOtp();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to send email OTP. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> requestAccountDeletion({
    required String otp,
    String? note,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _authRepository.requestAccountDeletion(
        otp: otp,
        note: note,
      );
      _authRepository.clearLocalSession();
      _session = null;
      _driverProfile = null;
      _transporterProfile = null;
      _driverProfileLoadedAt = null;
      _transporterProfileLoadedAt = null;
      await DriverDieselSessionService.instance.clear();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to delete the account right now. Please try again.';
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
    _driverProfile = null;
    _transporterProfile = null;
    _driverProfileLoadedAt = null;
    _transporterProfileLoadedAt = null;
    DriverDieselSessionService.instance.clear();
    notifyListeners();
  }
}
