import 'dart:async';

import '../../core/network/api_client.dart';
import '../../domain/entities/app_user.dart';
import '../../domain/entities/driver_profile.dart';
import '../../domain/entities/public_transporter.dart';
import '../../domain/entities/transporter_profile.dart';
import '../../domain/repositories/auth_repository.dart';
import '../datasources/auth_local_data_source.dart';
import '../datasources/auth_remote_data_source.dart';
import '../models/app_user_model.dart';

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(
    this._remoteDataSource,
    this._localDataSource,
    this._apiClient,
  );

  final AuthRemoteDataSource _remoteDataSource;
  final AuthLocalDataSource _localDataSource;
  final ApiClient _apiClient;
  AuthSession? _session;

  @override
  AuthSession? get currentSession => _session;

  @override
  Future<AuthSession> login({
    required String credential,
    required String password,
  }) async {
    final session = await _remoteDataSource.login(
      credential: credential,
      password: password,
    );
    await _setSession(session);
    return session;
  }

  @override
  Future<String?> requestPasswordResetOtp({required String email}) {
    return _remoteDataSource.requestPasswordResetOtp(email: email);
  }

  @override
  Future<void> resetPasswordWithOtp({
    required String email,
    required String otp,
    required String newPassword,
    required String confirmPassword,
  }) {
    return _remoteDataSource.resetPasswordWithOtp(
      email: email,
      otp: otp,
      newPassword: newPassword,
      confirmPassword: confirmPassword,
    );
  }

  @override
  Future<AuthSession> registerTransporter({
    required String username,
    required String password,
    required String companyName,
    required String email,
    required String otp,
    String? phone,
    String? address,
  }) async {
    final session = await _remoteDataSource.registerTransporter(
      username: username,
      password: password,
      companyName: companyName,
      email: email,
      otp: otp,
      phone: phone,
      address: address,
    );
    await _setSession(session);
    return session;
  }

  @override
  Future<String?> requestTransporterOtp({required String email}) {
    return _remoteDataSource.requestTransporterOtp(email: email);
  }

  @override
  Future<List<PublicTransporter>> getPublicTransporters() {
    return _remoteDataSource.getPublicTransporters();
  }

  @override
  Future<String?> requestDriverOtp({required String email}) {
    return _remoteDataSource.requestDriverOtp(email: email);
  }

  @override
  Future<AuthSession> registerDriver({
    required String username,
    required String password,
    required String email,
    required String otp,
    required String licenseNumber,
    int? transporterId,
    String? phone,
  }) async {
    final session = await _remoteDataSource.registerDriver(
      username: username,
      password: password,
      email: email,
      otp: otp,
      licenseNumber: licenseNumber,
      transporterId: transporterId,
      phone: phone,
    );
    await _setSession(session);
    return session;
  }

  @override
  Future<AuthSession?> restoreSession() async {
    final storedSession = await _localDataSource.readSession();
    if (storedSession == null) {
      return null;
    }
    _session = storedSession;
    _apiClient.setAccessToken(storedSession.accessToken);
    return storedSession;
  }

  @override
  Future<DriverProfile> getDriverProfile() {
    return _remoteDataSource.getDriverProfile();
  }

  @override
  Future<TransporterProfile> getTransporterProfile() {
    return _remoteDataSource.getTransporterProfile();
  }

  @override
  Future<AppUser> updateDriverProfile({
    String? username,
    String? email,
    String? phone,
    String? licenseNumber,
  }) async {
    final user = await _remoteDataSource.updateDriverProfile(
      username: username,
      email: email,
      phone: phone,
      licenseNumber: licenseNumber,
    );
    _replaceSessionUser(user);
    final session = _session;
    if (session != null) {
      await _localDataSource.saveSession(_toSessionModel(session));
    }
    return user;
  }

  @override
  Future<AppUser> updateTransporterProfile({
    String? username,
    String? email,
    String? phone,
    String? companyName,
    String? address,
  }) async {
    final user = await _remoteDataSource.updateTransporterProfile(
      username: username,
      email: email,
      phone: phone,
      companyName: companyName,
      address: address,
    );
    _replaceSessionUser(user);
    final session = _session;
    if (session != null) {
      await _localDataSource.saveSession(_toSessionModel(session));
    }
    return user;
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
    required String confirmPassword,
  }) {
    return _remoteDataSource.changePassword(
      currentPassword: currentPassword,
      newPassword: newPassword,
      confirmPassword: confirmPassword,
    );
  }

  @override
  void logout() {
    _session = null;
    _apiClient.setAccessToken(null);
    unawaited(_localDataSource.clearSession());
  }

  void _replaceSessionUser(AppUser user) {
    final session = _session;
    if (session == null) {
      return;
    }

    _session = AuthSession(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      user: user,
      transporterId: session.transporterId,
      driverId: session.driverId,
      dieselTrackingEnabled: session.dieselTrackingEnabled,
    );
  }

  Future<void> _setSession(AuthSession session) async {
    _session = session;
    _apiClient.setAccessToken(session.accessToken);
    await _localDataSource.saveSession(_toSessionModel(session));
  }

  AuthSessionModel _toSessionModel(AuthSession session) {
    final user = session.user;
    final userModel = user is AppUserModel
        ? user
        : AppUserModel(
            id: user.id,
            username: user.username,
            email: user.email,
            phone: user.phone,
            role: user.role,
          );
    return AuthSessionModel(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
      user: userModel,
      transporterId: session.transporterId,
      driverId: session.driverId,
      dieselTrackingEnabled: session.dieselTrackingEnabled,
    );
  }
}
