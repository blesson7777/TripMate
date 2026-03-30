import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class QueuedTowerDieselEntry {
  const QueuedTowerDieselEntry({
    required this.id,
    required this.indusSiteId,
    required this.siteName,
    required this.fuelFilled,
    required this.confirmSiteNameUpdate,
    required this.purpose,
    required this.logbookPhotoPath,
    required this.createdAt,
    this.piuReading,
    this.dgHmr,
    this.openingStock,
    this.startKm,
    this.endKm,
    this.towerLatitude,
    this.towerLongitude,
    this.fillDate,
  });

  factory QueuedTowerDieselEntry.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic value) {
      final raw = value?.toString().trim() ?? '';
      if (raw.isEmpty) {
        return null;
      }
      return DateTime.tryParse(raw);
    }

    double? parseDouble(dynamic value) {
      if (value == null) {
        return null;
      }
      if (value is num) {
        return value.toDouble();
      }
      return double.tryParse(value.toString());
    }

    int? parseInt(dynamic value) {
      if (value == null) {
        return null;
      }
      if (value is num) {
        return value.toInt();
      }
      return int.tryParse(value.toString());
    }

    return QueuedTowerDieselEntry(
      id: json['id']?.toString() ?? '',
      indusSiteId: json['indus_site_id']?.toString() ?? '',
      siteName: json['site_name']?.toString() ?? '',
      fuelFilled: parseDouble(json['fuel_filled']) ?? 0,
      piuReading: parseDouble(json['piu_reading']),
      dgHmr: parseDouble(json['dg_hmr']),
      openingStock: parseDouble(json['opening_stock']),
      confirmSiteNameUpdate: json['confirm_site_name_update'] == true,
      startKm: parseInt(json['start_km']),
      endKm: parseInt(json['end_km']),
      towerLatitude: parseDouble(json['tower_latitude']),
      towerLongitude: parseDouble(json['tower_longitude']),
      purpose: json['purpose']?.toString() ?? 'Diesel Filling',
      fillDate: parseDate(json['fill_date']),
      logbookPhotoPath: json['logbook_photo_path']?.toString() ?? '',
      createdAt: parseDate(json['created_at']) ?? DateTime.now(),
    );
  }

  final String id;
  final String indusSiteId;
  final String siteName;
  final double fuelFilled;
  final double? piuReading;
  final double? dgHmr;
  final double? openingStock;
  final bool confirmSiteNameUpdate;
  final int? startKm;
  final int? endKm;
  final double? towerLatitude;
  final double? towerLongitude;
  final String purpose;
  final DateTime? fillDate;
  final String logbookPhotoPath;
  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'indus_site_id': indusSiteId,
      'site_name': siteName,
      'fuel_filled': fuelFilled,
      if (piuReading != null) 'piu_reading': piuReading,
      if (dgHmr != null) 'dg_hmr': dgHmr,
      if (openingStock != null) 'opening_stock': openingStock,
      'confirm_site_name_update': confirmSiteNameUpdate,
      if (startKm != null) 'start_km': startKm,
      if (endKm != null) 'end_km': endKm,
      if (towerLatitude != null) 'tower_latitude': towerLatitude,
      if (towerLongitude != null) 'tower_longitude': towerLongitude,
      'purpose': purpose,
      if (fillDate != null) 'fill_date': fillDate!.toIso8601String(),
      'logbook_photo_path': logbookPhotoPath,
      'created_at': createdAt.toIso8601String(),
    };
  }
}

class OfflineTowerDieselSyncResult {
  const OfflineTowerDieselSyncResult({
    required this.syncedCount,
    required this.remainingCount,
  });

  final int syncedCount;
  final int remainingCount;
}

class OfflineTowerDieselQueueService {
  OfflineTowerDieselQueueService._();

  static final OfflineTowerDieselQueueService instance =
      OfflineTowerDieselQueueService._();

  static const String _queueKey = 'offline_tower_diesel_queue_v1';

  final ValueNotifier<int> pendingCount = ValueNotifier(0);
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }
    final queue = await _readQueue();
    pendingCount.value = queue.length;
    _initialized = true;
  }

  Future<List<QueuedTowerDieselEntry>> loadQueue() async {
    await initialize();
    return _readQueue();
  }

  Future<QueuedTowerDieselEntry> enqueue({
    required String indusSiteId,
    required String siteName,
    required double fuelFilled,
    double? piuReading,
    double? dgHmr,
    double? openingStock,
    bool confirmSiteNameUpdate = false,
    int? startKm,
    int? endKm,
    double? towerLatitude,
    double? towerLongitude,
    required String purpose,
    DateTime? fillDate,
    required File logbookPhoto,
  }) async {
    await initialize();
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    final copiedPhotoPath = await _persistPhoto(logbookPhoto, id);
    final queue = await _readQueue();
    final entry = QueuedTowerDieselEntry(
      id: id,
      indusSiteId: indusSiteId,
      siteName: siteName,
      fuelFilled: fuelFilled,
      piuReading: piuReading,
      dgHmr: dgHmr,
      openingStock: openingStock,
      confirmSiteNameUpdate: confirmSiteNameUpdate,
      startKm: startKm,
      endKm: endKm,
      towerLatitude: towerLatitude,
      towerLongitude: towerLongitude,
      purpose: purpose,
      fillDate: fillDate,
      logbookPhotoPath: copiedPhotoPath,
      createdAt: DateTime.now(),
    );
    queue.add(entry);
    await _saveQueue(queue);
    return entry;
  }

  Future<OfflineTowerDieselSyncResult> sync({
    required Future<void> Function(QueuedTowerDieselEntry entry) submit,
  }) async {
    await initialize();
    final queue = await _readQueue();
    if (queue.isEmpty) {
      return const OfflineTowerDieselSyncResult(
        syncedCount: 0,
        remainingCount: 0,
      );
    }

    final remaining = <QueuedTowerDieselEntry>[];
    var syncedCount = 0;
    for (final entry in queue) {
      final imageFile = File(entry.logbookPhotoPath);
      if (!imageFile.existsSync()) {
        remaining.add(entry);
        continue;
      }
      try {
        await submit(entry);
        syncedCount += 1;
        await _deleteFileIfExists(entry.logbookPhotoPath);
      } catch (_) {
        remaining.add(entry);
      }
    }

    await _saveQueue(remaining);
    return OfflineTowerDieselSyncResult(
      syncedCount: syncedCount,
      remainingCount: remaining.length,
    );
  }

  Future<void> clear() async {
    await initialize();
    final queue = await _readQueue();
    for (final entry in queue) {
      await _deleteFileIfExists(entry.logbookPhotoPath);
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_queueKey);
    pendingCount.value = 0;
  }

  Future<List<QueuedTowerDieselEntry>> _readQueue() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_queueKey);
    if (raw == null || raw.trim().isEmpty) {
      return const [];
    }

    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return decoded
          .map(
            (item) => QueuedTowerDieselEntry.fromJson(
              item as Map<String, dynamic>,
            ),
          )
          .toList(growable: true);
    } catch (_) {
      await prefs.remove(_queueKey);
      return const [];
    }
  }

  Future<void> _saveQueue(List<QueuedTowerDieselEntry> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _queueKey,
      jsonEncode(entries.map((entry) => entry.toJson()).toList()),
    );
    pendingCount.value = entries.length;
  }

  Future<String> _persistPhoto(File source, String entryId) async {
    if (!await source.exists()) {
      throw const FileSystemException('Logbook photo not found.');
    }

    final extension = _fileExtension(source.path);
    final bytes = await source.readAsBytes();

    for (final directory in await _storageDirectories()) {
      try {
        final queueDirectory = Directory(
          '${directory.path}${Platform.pathSeparator}offline_tower_diesel',
        );
        if (!queueDirectory.existsSync()) {
          await queueDirectory.create(recursive: true);
        }
        final targetPath =
            '${queueDirectory.path}${Platform.pathSeparator}tower_diesel_$entryId$extension';
        final targetFile = File(targetPath);
        await targetFile.writeAsBytes(bytes, flush: true);
        return targetFile.path;
      } catch (_) {
        continue;
      }
    }

    return source.path;
  }

  Future<List<Directory>> _storageDirectories() async {
    final directories = <Directory>[];
    try {
      directories.add(await getApplicationDocumentsDirectory());
    } catch (_) {
      // Try the next location.
    }
    try {
      directories.add(await getTemporaryDirectory());
    } catch (_) {
      // Keep fallback best effort.
    }
    return directories;
  }

  String _fileExtension(String path) {
    final separatorIndex = path.lastIndexOf('.');
    if (separatorIndex == -1) {
      return '.jpg';
    }
    final extension = path.substring(separatorIndex).trim();
    if (extension.isEmpty || extension.length > 8) {
      return '.jpg';
    }
    return extension;
  }

  Future<void> _deleteFileIfExists(String path) async {
    try {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    } catch (_) {
      // Keep cleanup best effort.
    }
  }
}
