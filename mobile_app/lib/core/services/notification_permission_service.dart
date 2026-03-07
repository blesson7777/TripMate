import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';

class NotificationPermissionService {
  Future<bool> ensurePermission() async {
    if (!_supportsRuntimePermissionPrompt()) {
      return true;
    }

    final status = await Permission.notification.status;
    if (_isGranted(status)) {
      return true;
    }

    final requested = await Permission.notification.request();
    return _isGranted(requested);
  }

  Future<bool> isPermissionGranted() async {
    if (!_supportsRuntimePermissionPrompt()) {
      return true;
    }
    final status = await Permission.notification.status;
    return _isGranted(status);
  }

  Future<void> openAppPermissionSettings() async {
    await openAppSettings();
  }

  bool _supportsRuntimePermissionPrompt() {
    if (kIsWeb) {
      return false;
    }
    return defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS;
  }

  bool _isGranted(PermissionStatus status) {
    return status.isGranted || status.isLimited || status.isProvisional;
  }
}
