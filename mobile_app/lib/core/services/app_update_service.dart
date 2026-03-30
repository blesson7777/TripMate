import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import '../constants/app_distribution.dart';
import '../constants/api_constants.dart';
import '../models/app_update_info.dart';
import '../../presentation/widgets/app_update_dialog.dart';

class AppUpdateService {
  AppUpdateService._();

  static final AppUpdateService instance = AppUpdateService._();

  static const MethodChannel _updateChannel =
      MethodChannel('tripmate/update_manager');
  static const String _backgroundDownloadPrefix = 'download-manager:';

  final http.Client _httpClient = http.Client();
  final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(minutes: 10),
      sendTimeout: const Duration(minutes: 2),
    ),
  );

  final Set<AppUpdateChannel> _activeChecks = <AppUpdateChannel>{};
  bool _dialogVisible = false;

  Future<AppUpdateInfo?> checkForUpdate({
    required AppUpdateChannel channel,
  }) async {
    if (AppDistribution.isPlayStore) {
      return null;
    }
    final packageInfo = await PackageInfo.fromPlatform();
    final installedBuildNumber = int.tryParse(packageInfo.buildNumber) ?? 0;
    final endpoint = Uri.parse('${ApiConstants.baseUrl}/app-update/${channel.apiSegment}');
    debugPrint('AppUpdate check -> $endpoint');

    try {
      final response = await _httpClient.get(endpoint).timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) {
        debugPrint('AppUpdate check failed: HTTP ${response.statusCode}');
        return null;
      }

      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) {
        debugPrint('AppUpdate check failed: invalid JSON payload');
        return null;
      }

      if (decoded['available'] == false) {
        return null;
      }

      final info = AppUpdateInfo.fromJson(decoded, channel: channel);
      if (info.latestVersion.isEmpty || info.apkUrl.isEmpty) {
        return null;
      }

      if (!info.isNewerThan(
        installedVersion: packageInfo.version,
        installedBuildNumber: installedBuildNumber,
      )) {
        debugPrint(
          'AppUpdate no update -> installed=${packageInfo.version}+${packageInfo.buildNumber}, '
          'latest=${info.latestVersion}+${info.latestBuildNumber}',
        );
        return null;
      }

      debugPrint(
        'AppUpdate available -> installed=${packageInfo.version}+${packageInfo.buildNumber}, '
        'latest=${info.latestVersion}+${info.latestBuildNumber}',
      );
      return info;
    } catch (error, stackTrace) {
      debugPrint('AppUpdate check error: $error');
      debugPrintStack(stackTrace: stackTrace);
      return null;
    }
  }

  Future<void> checkAndPromptForUpdate({
    required BuildContext context,
    required AppUpdateChannel channel,
    bool forceRecheck = false,
  }) async {
    if (AppDistribution.isPlayStore) {
      return;
    }
    if (_dialogVisible) {
      return;
    }
    if (!forceRecheck && _activeChecks.contains(channel)) {
      return;
    }

    _activeChecks.add(channel);
    try {
      final info = await checkForUpdate(channel: channel);
      if (info == null || !context.mounted) {
        return;
      }

      _dialogVisible = true;
      try {
        await showDialog<void>(
          context: context,
          barrierDismissible: !info.forceUpdate,
          builder: (_) => AppUpdateDialog(
            updateInfo: info,
            updateService: this,
          ),
        );
      } finally {
        _dialogVisible = false;
      }
    } finally {
      _activeChecks.remove(channel);
    }
  }

  Future<String> downloadUpdate({
    required AppUpdateInfo updateInfo,
    required void Function(double progress) onProgress,
  }) async {
    if (AppDistribution.isPlayStore) {
      throw StateError('In-app APK updates are disabled for Play Store builds.');
    }
    if (Platform.isAndroid) {
      try {
        final reference = await _enqueueAndroidBackgroundDownload(updateInfo);
        onProgress(1);
        return reference;
      } catch (error, stackTrace) {
        debugPrint('AppUpdate DownloadManager enqueue failed: $error');
        debugPrintStack(stackTrace: stackTrace);
      }
    }

    await _ensureStoragePermissionIfNeeded();
    final directory = await _resolveDownloadDirectory();
    final file = File('${directory.path}${Platform.pathSeparator}${updateInfo.suggestedFileName()}');
    if (await file.exists()) {
      await file.delete();
    }

    debugPrint('AppUpdate download -> ${updateInfo.apkUrl} -> ${file.path}');

    await _dio.download(
      updateInfo.apkUrl,
      file.path,
      deleteOnError: true,
      onReceiveProgress: (received, total) {
        if (total <= 0) {
          onProgress(0);
          return;
        }
        onProgress(received / total);
      },
    );
    onProgress(1);
    return file.path;
  }

  bool isBackgroundManagedDownload(String reference) {
    return reference.startsWith(_backgroundDownloadPrefix);
  }

  String backgroundDownloadMessage(AppUpdateInfo updateInfo) {
    return 'Download started in background for ${updateInfo.channel.displayName}. '
        'Android will continue the download over Wi-Fi or mobile data. '
        'When the APK is ready, the installer will open or you will get a '
        'Tap to install update notification.';
  }

  Future<bool> installUpdate(String apkPath) async {
    if (AppDistribution.isPlayStore) {
      return false;
    }
    if (!Platform.isAndroid) {
      return false;
    }
    if (isBackgroundManagedDownload(apkPath)) {
      return true;
    }

    final installPermission = await Permission.requestInstallPackages.request();
    if (!installPermission.isGranted) {
      debugPrint('AppUpdate install permission denied: $installPermission');
      if (installPermission.isPermanentlyDenied) {
        await openAppSettings();
      }
      return false;
    }

    final result = await OpenFile.open(apkPath);
    debugPrint('AppUpdate install result -> ${result.type}: ${result.message}');
    return result.type == ResultType.done;
  }

  Future<Directory> _resolveDownloadDirectory() async {
    if (Platform.isAndroid) {
      final externalDirectory = await getExternalStorageDirectory();
      if (externalDirectory != null) {
        final directory = Directory(
          '${externalDirectory.path}${Platform.pathSeparator}tripmate_updates',
        );
        await directory.create(recursive: true);
        return directory;
      }
    }

    final documentsDirectory = await getApplicationDocumentsDirectory();
    final directory = Directory(
      '${documentsDirectory.path}${Platform.pathSeparator}tripmate_updates',
    );
    await directory.create(recursive: true);
    return directory;
  }

  Future<void> _ensureStoragePermissionIfNeeded() async {
    if (!Platform.isAndroid) {
      return;
    }
    try {
      final storageStatus = await Permission.storage.status;
      if (!storageStatus.isGranted && !storageStatus.isPermanentlyDenied) {
        await Permission.storage.request();
      }
    } catch (_) {
      // App-specific external storage does not require storage permission.
    }
  }

  Future<String> _enqueueAndroidBackgroundDownload(
    AppUpdateInfo updateInfo,
  ) async {
    final downloadId = await _updateChannel.invokeMethod<String>(
      'enqueueApkDownload',
      {
        'url': updateInfo.apkUrl,
        'fileName': updateInfo.suggestedFileName(),
        'title': '${updateInfo.channel.displayName} update',
        'description':
            'Downloading ${updateInfo.channel.displayName} in background.',
      },
    );
    if (downloadId == null || downloadId.trim().isEmpty) {
      throw StateError('Android background download did not return an id.');
    }
    return '$_backgroundDownloadPrefix$downloadId';
  }
}
