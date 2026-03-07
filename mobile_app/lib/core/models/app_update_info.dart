enum AppUpdateChannel {
  driver,
  transporter,
}

extension AppUpdateChannelX on AppUpdateChannel {
  String get apiSegment => this == AppUpdateChannel.driver ? 'driver' : 'transporter';

  String get displayName =>
      this == AppUpdateChannel.driver ? 'Driver App' : 'Transporter App';

  String get uppercaseName => this == AppUpdateChannel.driver ? 'DRIVER' : 'TRANSPORTER';
}

class AppUpdateInfo {
  const AppUpdateInfo({
    required this.channel,
    required this.latestVersion,
    required this.latestBuildNumber,
    required this.apkUrl,
    required this.forceUpdate,
    required this.message,
  });

  final AppUpdateChannel channel;
  final String latestVersion;
  final int latestBuildNumber;
  final String apkUrl;
  final bool forceUpdate;
  final String message;

  factory AppUpdateInfo.fromJson(
    Map<String, dynamic> json, {
    required AppUpdateChannel channel,
  }) {
    return AppUpdateInfo(
      channel: channel,
      latestVersion: (json['latest_version'] ?? '').toString().trim(),
      latestBuildNumber: _asInt(json['latest_build_number']),
      apkUrl: (json['apk_url'] ?? '').toString().trim(),
      forceUpdate: json['force_update'] == true,
      message: (json['message'] ?? '').toString().trim(),
    );
  }

  String suggestedFileName() {
    final safeVersion = latestVersion.replaceAll(RegExp(r'[^0-9A-Za-z._-]'), '_');
    return '${channel.apiSegment}_app_v${safeVersion}_b$latestBuildNumber.apk';
  }

  bool isNewerThan({
    required String installedVersion,
    required int installedBuildNumber,
  }) {
    if (latestBuildNumber > 0 && latestBuildNumber > installedBuildNumber) {
      return true;
    }
    if (latestBuildNumber > 0 && latestBuildNumber < installedBuildNumber) {
      return false;
    }
    return _compareSemanticVersions(latestVersion, installedVersion) > 0;
  }

  static int _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static int _compareSemanticVersions(String left, String right) {
    final leftParts = _normalizedParts(left);
    final rightParts = _normalizedParts(right);
    final maxLength = leftParts.length > rightParts.length ? leftParts.length : rightParts.length;
    for (var index = 0; index < maxLength; index += 1) {
      final leftValue = index < leftParts.length ? leftParts[index] : 0;
      final rightValue = index < rightParts.length ? rightParts[index] : 0;
      if (leftValue == rightValue) {
        continue;
      }
      return leftValue > rightValue ? 1 : -1;
    }
    return 0;
  }

  static List<int> _normalizedParts(String version) {
    return version
        .split(RegExp(r'[^0-9]+'))
        .where((part) => part.isNotEmpty)
        .map((part) => int.tryParse(part) ?? 0)
        .toList();
  }
}
