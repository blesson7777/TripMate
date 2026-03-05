import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_user_model.dart';

class AuthLocalDataSource {
  static const String _sessionKey = 'tripmate_auth_session';

  Future<void> saveSession(AuthSessionModel session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_sessionKey, jsonEncode(session.toJson()));
  }

  Future<AuthSessionModel?> readSession() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_sessionKey);
    if (raw == null || raw.isEmpty) {
      return null;
    }

    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      return AuthSessionModel.fromJson(map);
    } catch (_) {
      await prefs.remove(_sessionKey);
      return null;
    }
  }

  Future<void> clearSession() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_sessionKey);
  }
}
