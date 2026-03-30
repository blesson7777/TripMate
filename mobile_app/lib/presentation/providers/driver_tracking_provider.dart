import 'package:flutter/foundation.dart';

import '../../core/network/api_client.dart';
import '../../domain/entities/driver_location_feed.dart';
import '../../domain/repositories/fleet_repository.dart';

class DriverTrackingProvider extends ChangeNotifier {
  DriverTrackingProvider(this._fleetRepository);

  final FleetRepository _fleetRepository;

  bool _loading = false;
  String? _error;
  DriverLocationFeed? _feed;

  bool get loading => _loading;
  String? get error => _error;
  DriverLocationFeed? get feed => _feed;

  Future<bool> load({
    DateTime? date,
    int? driverId,
    int? attendanceId,
    bool openOnly = false,
    bool silent = false,
  }) async {
    if (!silent) {
      _loading = true;
      _error = null;
      notifyListeners();
    }

    var didUpdate = false;
    try {
      final next = await _fleetRepository.getTransporterDriverLocations(
        date: date,
        driverId: driverId,
        attendanceId: attendanceId,
        openOnly: openOnly,
      );
      _feed = next;
      didUpdate = true;
      return true;
    } on ApiException catch (exception) {
      if (!silent) {
        _error = exception.message;
      }
      return false;
    } catch (_) {
      if (!silent) {
        _error = 'Unable to load driver tracking.';
      }
      return false;
    } finally {
      if (!silent) {
        _loading = false;
        notifyListeners();
      } else if (didUpdate) {
        notifyListeners();
      }
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}

