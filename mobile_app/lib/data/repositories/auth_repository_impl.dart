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
  ) {
    _apiClient.setAuthHandlers(
      onRefreshSession: _refreshSession,
      onAuthFailure: _clearSessionSilently,
    );
  }

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
  Future<String?> requestDriverLoginOtp({
    required String credential,
    required String password,
  }) {
    return _remoteDataSource.requestDriverLoginOtp(
      credential: credential,
      password: password,
    );
  }

  @override
  Future<AuthSession> verifyDriverLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    final session = await _remoteDataSource.verifyDriverLoginOtp(
      credential: credential,
      password: password,
      otp: otp,
    );
    await _setSession(session);
    return session;
  }

  @override
  Future<String?> requestTransporterLoginOtp({
    required String credential,
    required String password,
  }) {
    return _remoteDataSource.requestTransporterLoginOtp(
      credential: credential,
      password: password,
    );
  }

  @override
  Future<AuthSession> verifyTransporterLoginOtp({
    required String credential,
    required String password,
    required String otp,
  }) async {
    final session = await _remoteDataSource.verifyTransporterLoginOtp(
      credential: credential,
      password: password,
      otp: otp,
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
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  }) async {
    final session = await _remoteDataSource.registerTransporter(
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
  Future<String?> requestProfileEmailChangeOtp({required String email}) {
    return _remoteDataSource.requestProfileEmailChangeOtp(email: email);
  }

  @override
  Future<AppUser> updateDriverProfile({
    String? username,
    String? email,
    String? emailOtp,
    String? licenseNumber,
  }) async {
    final user = await _remoteDataSource.updateDriverProfile(
      username: username,
      email: email,
      emailOtp: emailOtp,
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
    String? emailOtp,
    String? companyName,
    String? address,
    String? gstin,
    String? pan,
    String? website,
    String? logoBase64,
  }) async {
    final user = await _remoteDataSource.updateTransporterProfile(
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
  Future<String?> requestAccountDeletionOtp() {
    return _remoteDataSource.requestAccountDeletionOtp();
  }

  @override
  Future<void> requestAccountDeletion({
    required String otp,
    String? note,
  }) async {
    await _remoteDataSource.requestAccountDeletion(
      otp: otp,
      note: note,
    );
  }

  @override
  void logout() {
    final session = _session;
    if (session != null) {
      unawaited(_remoteDataSource.logout(refreshToken: session.refreshToken));
    }
    _session = null;
    _apiClient.setAccessToken(null);
    unawaited(_localDataSource.clearSession());
  }

  @override
  void clearLocalSession() {
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
      dieselReadingsEnabled: session.dieselReadingsEnabled,
      locationTrackingEnabled: session.locationTrackingEnabled,
    );
  }

  Future<void> _setSession(AuthSession session) async {
    _session = session;
    _apiClient.setAccessToken(session.accessToken);
    await _localDataSource.saveSession(_toSessionModel(session));
  }

  Future<bool> _refreshSession() async {
    final session = _session;
    if (session == null || session.refreshToken.isEmpty) {
      return false;
    }
    try {
      final refreshed = await _remoteDataSource.refreshSession(
        refreshToken: session.refreshToken,
      );
      final nextAccessToken = (refreshed['access'] ?? '').toString();
      if (nextAccessToken.isEmpty) {
        return false;
      }
      final nextRefreshToken = (refreshed['refresh'] ?? '').toString();
      final updatedSession = AuthSession(
        accessToken: nextAccessToken,
        refreshToken: nextRefreshToken.isNotEmpty
            ? nextRefreshToken
            : session.refreshToken,
        user: session.user,
        transporterId: session.transporterId,
        driverId: session.driverId,
        dieselTrackingEnabled: session.dieselTrackingEnabled,
        dieselReadingsEnabled: session.dieselReadingsEnabled,
        locationTrackingEnabled: session.locationTrackingEnabled,
      );
      await _setSession(updatedSession);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _clearSessionSilently() async {
    _session = null;
    _apiClient.setAccessToken(null);
    await _localDataSource.clearSession();
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
      dieselReadingsEnabled: session.dieselReadingsEnabled,
      locationTrackingEnabled: session.locationTrackingEnabled,
    );
  }
}
