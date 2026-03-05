import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
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

  AuthSession? _session;
  bool _isLoading = false;
  bool _isReady = false;
  bool _isInitializing = false;
  String? _error;
  String? _debugOtp;
  DriverProfile? _driverProfile;
  TransporterProfile? _transporterProfile;

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
    } finally {
      _isInitializing = false;
      _isReady = true;
      notifyListeners();
    }
  }

  Future<bool> login({
    required String username,
    required String password,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _session =
          await _authRepository.login(username: username, password: password);
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

  Future<bool> registerTransporter({
    required String username,
    required String password,
    required String companyName,
    required String email,
    required String otp,
    String? phone,
    String? address,
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

  Future<bool> loadDriverProfile() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _driverProfile = await _authRepository.getDriverProfile();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to load profile. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> loadTransporterProfile() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _transporterProfile = await _authRepository.getTransporterProfile();
      return true;
    } on ApiException catch (exception) {
      _error = exception.message;
      return false;
    } catch (_) {
      _error = 'Unable to load profile. Please try again.';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> updateDriverProfile({
    required String username,
    required String email,
    required String phone,
    required String licenseNumber,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedUser = await _authRepository.updateDriverProfile(
        username: username,
        email: email,
        phone: phone,
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
    required String phone,
    required String companyName,
    required String address,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final updatedUser = await _authRepository.updateTransporterProfile(
        username: username,
        email: email,
        phone: phone,
        companyName: companyName,
        address: address,
      );
      final existingSession = _session;
      if (existingSession != null) {
        _session = AuthSession(
          accessToken: existingSession.accessToken,
          refreshToken: existingSession.refreshToken,
          user: updatedUser,
          transporterId: existingSession.transporterId,
          driverId: existingSession.driverId,
        );
      }
      _transporterProfile = await _authRepository.getTransporterProfile();
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

  void logout() {
    _authRepository.logout();
    _session = null;
    _error = null;
    _driverProfile = null;
    _transporterProfile = null;
    notifyListeners();
  }
}
