import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/driver_location_feed.dart';
import '../../../domain/entities/driver_location_point.dart';
import '../../../domain/entities/driver_location_session.dart';
import '../../../domain/entities/driver_info.dart';
import '../../providers/driver_tracking_provider.dart';
import '../../providers/transporter_provider.dart';

class DriverTrackingScreen extends StatefulWidget {
  const DriverTrackingScreen({super.key});

  @override
  State<DriverTrackingScreen> createState() => _DriverTrackingScreenState();
}

class _DriverTrackingScreenState extends State<DriverTrackingScreen>
    with WidgetsBindingObserver {
  static const LatLng _fallbackCenter = LatLng(10.8505, 76.2711);
  static const Duration _pollInterval = Duration(seconds: 30);

  static const double _stopRadiusMeters = 100;
  static const int _stopMinMinutes = 5;

  final MapController _mapController = MapController();
  final Distance _distance = const Distance();

  Timer? _poller;

  DateTime _selectedDate = DateTime.now();
  int? _selectedDriverId;
  bool _openOnly = false;

  int? _selectedAttendanceId;
  bool _followEnabled = false;
  bool _followSuspended = false;
  bool _fullScreen = false;
  bool _initialFitDone = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    _poller?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _startPolling();
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached) {
      _poller?.cancel();
      _poller = null;
    }
  }

  Future<void> _bootstrap() async {
    if (!mounted) {
      return;
    }
    await context
        .read<TransporterProvider>()
        .loadDashboardData(prefetchHeavyData: false);
    if (!mounted) {
      return;
    }
    await _loadTracking(forceFit: true);
    _startPolling();
  }

  void _startPolling() {
    _poller?.cancel();
    _poller = Timer.periodic(_pollInterval, (_) {
      if (!mounted) {
        return;
      }
      unawaited(_loadTracking(silent: true));
    });
  }

  Future<void> _loadTracking({bool silent = false, bool forceFit = false}) async {
    final tracking = context.read<DriverTrackingProvider>();
    final ok = await tracking.load(
      date: _selectedDate,
      driverId: _selectedDriverId,
      openOnly: _openOnly,
      silent: silent,
    );
    if (!mounted) {
      return;
    }

    final feed = tracking.feed;
    if (feed == null) {
      return;
    }

    _ensureSelection(feed.sessions);

    if ((!_initialFitDone || forceFit) && feed.mapPoints.isNotEmpty) {
      _initialFitDone = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _fitToBounds(feed);
      });
      return;
    }

    if (ok) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _maybeFollow(feed);
      });
    }
  }

  void _ensureSelection(List<DriverLocationSession> sessions) {
    if (sessions.isEmpty) {
      if (_selectedAttendanceId != null) {
        setState(() {
          _selectedAttendanceId = null;
        });
      }
      return;
    }

    final existing = _selectedAttendanceId;
    if (existing != null && sessions.any((item) => item.attendanceId == existing)) {
      return;
    }

    final open = sessions.where((item) => item.statusLabel == 'Open').toList();
    final next = (open.isNotEmpty ? open.first : sessions.first).attendanceId;
    setState(() {
      _selectedAttendanceId = next;
      _followSuspended = false;
    });
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 1),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedDate = picked;
      _initialFitDone = false;
    });
    await _loadTracking(forceFit: true);
  }

  double _distanceMeters(LatLng a, LatLng b) {
    return _distance.as(LengthUnit.Meter, a, b);
  }

  double _routeDistanceKm(List<LatLng> points) {
    if (points.length < 2) {
      return 0;
    }
    var meters = 0.0;
    for (var i = 1; i < points.length; i++) {
      meters += _distanceMeters(points[i - 1], points[i]);
    }
    return meters / 1000;
  }

  double _bearingDegrees(LatLng from, LatLng to) {
    final lat1 = from.latitudeInRad;
    final lat2 = to.latitudeInRad;
    final dLon = (to.longitudeInRad - from.longitudeInRad);
    final y = math.sin(dLon) * math.cos(lat2);
    final x = math.cos(lat1) * math.sin(lat2) -
        math.sin(lat1) * math.cos(lat2) * math.cos(dLon);
    final brng = math.atan2(y, x);
    return (brng * 180 / math.pi + 360) % 360;
  }

  bool _isMapReady() {
    try {
      _mapController.camera;
      return true;
    } catch (_) {
      return false;
    }
  }

  double _safeCurrentZoom({double fallback = 11.5}) {
    try {
      final zoom = _mapController.camera.zoom;
      return zoom.isFinite ? zoom : fallback;
    } catch (_) {
      return fallback;
    }
  }

  Color _colorForAttendance(int attendanceId) {
    const palette = [
      Color(0xFF0A6B6F),
      Color(0xFF2563EB),
      Color(0xFFE11D48),
      Color(0xFFE08D3C),
      Color(0xFF8B5CF6),
      Color(0xFF14B8A6),
      Color(0xFF65A30D),
      Color(0xFF0EA5E9),
    ];
    return palette[attendanceId.abs() % palette.length];
  }

  bool _isValidCoordinate(double latitude, double longitude) {
    if (!latitude.isFinite || !longitude.isFinite) {
      return false;
    }
    if (latitude < -90 || latitude > 90) {
      return false;
    }
    if (longitude < -180 || longitude > 180) {
      return false;
    }
    return true;
  }

  List<DriverLocationPoint> _pointsForAttendance(
    List<DriverLocationPoint> points,
    int attendanceId,
  ) {
    final list = points
        .where(
          (p) =>
              p.attendanceId == attendanceId &&
              _isValidCoordinate(p.latitude, p.longitude),
        )
        .toList();
    list.sort((a, b) {
      final left = a.recordedAt?.millisecondsSinceEpoch ?? 0;
      final right = b.recordedAt?.millisecondsSinceEpoch ?? 0;
      return left.compareTo(right);
    });
    return list;
  }

  _ProcessedRoute _processRoute(List<DriverLocationPoint> points) {
    if (points.isEmpty) {
      return const _ProcessedRoute(route: [], stops: []);
    }

    final route = <LatLng>[];
    final stops = <_StopInfo>[];

    var cluster = <DriverLocationPoint>[];
    var latSum = 0.0;
    var lonSum = 0.0;
    LatLng? centroid;
    DateTime? startAt;
    DateTime? endAt;

    void startCluster(DriverLocationPoint point) {
      cluster = [point];
      latSum = point.latitude;
      lonSum = point.longitude;
      centroid = LatLng(point.latitude, point.longitude);
      startAt = point.recordedAt;
      endAt = point.recordedAt;
    }

    void extendCluster(DriverLocationPoint point) {
      cluster.add(point);
      latSum += point.latitude;
      lonSum += point.longitude;
      centroid = LatLng(latSum / cluster.length, lonSum / cluster.length);
      if (point.recordedAt != null) {
        endAt = point.recordedAt;
      }
    }

    void flushCluster() {
      if (cluster.isEmpty) {
        return;
      }
      final durationMinutes = (startAt != null && endAt != null)
          ? endAt!.difference(startAt!).inMinutes
          : 0;
      final isStop = durationMinutes >= _stopMinMinutes;
      if (isStop && centroid != null) {
        stops.add(
          _StopInfo(
            point: centroid!,
            durationMinutes: durationMinutes.toDouble(),
            firstPoint: cluster.first,
            lastPoint: cluster.last,
          ),
        );
        route.add(centroid!);
      } else {
        for (final point in cluster) {
          route.add(LatLng(point.latitude, point.longitude));
        }
      }

      cluster = [];
      latSum = 0;
      lonSum = 0;
      centroid = null;
      startAt = null;
      endAt = null;
    }

    for (final point in points) {
      if (cluster.isEmpty) {
        startCluster(point);
        continue;
      }
      final center = centroid;
      if (center != null) {
        final meters = _distanceMeters(
          center,
          LatLng(point.latitude, point.longitude),
        );
        if (meters <= _stopRadiusMeters) {
          extendCluster(point);
          continue;
        }
      }
      flushCluster();
      startCluster(point);
    }
    flushCluster();

    if (route.isEmpty) {
      return _ProcessedRoute(route: route, stops: stops);
    }

    final compressed = <LatLng>[route.first];
    for (var i = 1; i < route.length; i++) {
      final prev = compressed.last;
      final next = route[i];
      if (_distanceMeters(prev, next) < 0.1) {
        continue;
      }
      compressed.add(next);
    }
    return _ProcessedRoute(route: compressed, stops: stops);
  }

  double? _effectiveSpeedKph(
    DriverLocationPoint? previous,
    DriverLocationPoint current,
  ) {
    final sensor = current.speedKph;
    if (sensor != null && sensor.isFinite) {
      return sensor;
    }
    final prevTime = previous?.recordedAt;
    final currTime = current.recordedAt;
    if (previous == null || prevTime == null || currTime == null) {
      return null;
    }
    final seconds = currTime.difference(prevTime).inMilliseconds / 1000;
    if (seconds <= 0) {
      return null;
    }
    if (!_isValidCoordinate(previous.latitude, previous.longitude) ||
        !_isValidCoordinate(current.latitude, current.longitude)) {
      return null;
    }
    final meters = _distanceMeters(
      LatLng(previous.latitude, previous.longitude),
      LatLng(current.latitude, current.longitude),
    );
    return (meters / seconds) * 3.6;
  }

  void _fitToBounds(DriverLocationFeed feed, {int attempt = 0}) {
    final selected = _selectedAttendanceId;
    final points = feed.mapPoints
        .where((point) => selected == null || point.attendanceId == selected)
        .where((point) => _isValidCoordinate(point.latitude, point.longitude))
        .map((point) => LatLng(point.latitude, point.longitude))
        .toList();
    if (points.isEmpty) {
      return;
    }

    if (!_isMapReady()) {
      if (attempt >= 6) {
        return;
      }
      Future.delayed(const Duration(milliseconds: 160), () {
        if (!mounted) {
          return;
        }
        _fitToBounds(feed, attempt: attempt + 1);
      });
      return;
    }

    if (points.length == 1) {
      try {
        _mapController.move(points.first, _safeCurrentZoom(fallback: 14.5));
      } catch (_) {
        // Ignore map controller readiness issues.
      }
      return;
    }

    try {
      _mapController.fitCamera(
        CameraFit.bounds(
          bounds: LatLngBounds.fromPoints(points),
          padding: const EdgeInsets.fromLTRB(30, 110, 30, 240),
          maxZoom: 16,
        ),
      );
    } catch (_) {
      if (attempt >= 6) {
        return;
      }
      Future.delayed(const Duration(milliseconds: 160), () {
        if (!mounted) {
          return;
        }
        _fitToBounds(feed, attempt: attempt + 1);
      });
    }
  }

  DriverLocationPoint? _lastPointForAttendance(
    List<DriverLocationPoint> points,
    int attendanceId,
  ) {
    DriverLocationPoint? last;
    for (final point in points) {
      if (point.attendanceId != attendanceId) {
        continue;
      }
      if (!_isValidCoordinate(point.latitude, point.longitude)) {
        continue;
      }
      if (last == null) {
        last = point;
        continue;
      }
      final left = last.recordedAt?.millisecondsSinceEpoch ?? 0;
      final right = point.recordedAt?.millisecondsSinceEpoch ?? 0;
      if (right >= left) {
        last = point;
      }
    }
    return last;
  }

  void _maybeFollow(DriverLocationFeed feed) {
    final selected = _selectedAttendanceId;
    if (!_followEnabled || _followSuspended || selected == null) {
      return;
    }
    final last = _lastPointForAttendance(feed.mapPoints, selected);
    if (last == null) {
      return;
    }
    if (!_isValidCoordinate(last.latitude, last.longitude)) {
      return;
    }
    try {
      _mapController.move(
        LatLng(last.latitude, last.longitude),
        _safeCurrentZoom(),
      );
    } catch (_) {
      // Ignore map controller readiness issues.
    }
  }

  Future<void> _openRunsSheet(DriverLocationFeed feed) async {
    final sessions = feed.sessions;
    if (sessions.isEmpty) {
      return;
    }
    final selected = _selectedAttendanceId;

    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 18),
            itemCount: sessions.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final session = sessions[index];
              final attendanceId = session.attendanceId;
              final isSelected = selected == attendanceId;
              final color = _colorForAttendance(attendanceId);
              return ListTile(
                onTap: () {
                  Navigator.pop(context);
                  setState(() {
                    _selectedAttendanceId = attendanceId;
                    _followSuspended = false;
                  });
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (!mounted) {
                      return;
                    }
                    _fitToBounds(feed);
                    _maybeFollow(feed);
                  });
                },
                leading: Container(
                  width: 14,
                  height: 14,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
                title: Text(
                  '${session.vehicleNumber} — ${session.driverName}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                subtitle: Text(
                  '${session.serviceName} • ${session.statusLabel} • Last: ${session.lastSeenLabel}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: isSelected
                    ? const Icon(Icons.check_circle, color: Color(0xFF0A6B6F))
                    : null,
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildSelectedOverlay(DriverLocationFeed feed) {
    final selected = _selectedAttendanceId;
    if (selected == null) {
      return const SizedBox.shrink();
    }

    DriverLocationSession? session;
    for (final item in feed.sessions) {
      if (item.attendanceId == selected) {
        session = item;
        break;
      }
    }
    session ??= feed.sessions.isNotEmpty ? feed.sessions.first : null;
    if (session == null) {
      return const SizedBox.shrink();
    }

    final sessionPoints = _pointsForAttendance(feed.mapPoints, selected);
    final lastPoint = sessionPoints.isEmpty ? null : sessionPoints.last;
    final previous =
        sessionPoints.length >= 2 ? sessionPoints[sessionPoints.length - 2] : null;
    final speed = lastPoint == null ? null : _effectiveSpeedKph(previous, lastPoint);

    final processed = _processRoute(sessionPoints);
    final estimatedKm = _routeDistanceKm(processed.route);

    final color = _colorForAttendance(selected);

    final speedLabel = speed == null || !speed.isFinite
        ? '-'
        : '${speed.toStringAsFixed(1)} km/h';
    final estLabel = estimatedKm <= 0 ? '-' : '${estimatedKm.toStringAsFixed(1)} km';

    return Material(
      elevation: 4,
      borderRadius: BorderRadius.circular(18),
      color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.94),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
        child: Row(
          children: [
            Container(
              width: 12,
              height: 44,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${session.vehicleNumber} — ${session.driverName}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${session.statusLabel} • Speed: $speedLabel • Last: ${session.lastSeenLabel}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Estimated: $estLabel • KM: ${session.startKm ?? '-'} → ${session.endKm ?? '-'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilters({
    required DriverTrackingProvider tracking,
    required List<DriverInfo> drivers,
  }) {
    if (_fullScreen) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<int?>(
                  key: ValueKey<int?>(_selectedDriverId),
                  initialValue: _selectedDriverId,
                  decoration: const InputDecoration(
                    labelText: 'Driver',
                    prefixIcon: Icon(Icons.badge_outlined),
                  ),
                  items: [
                    const DropdownMenuItem<int?>(
                      value: null,
                      child: Text('All drivers'),
                    ),
                    for (final driver in drivers)
                      DropdownMenuItem<int?>(
                        value: driver.id,
                        child: Text(driver.username),
                      ),
                  ],
                  onChanged: tracking.loading
                      ? null
                      : (value) async {
                          setState(() {
                            _selectedDriverId = value;
                            _initialFitDone = false;
                          });
                          await _loadTracking(forceFit: true);
                        },
                ),
              ),
              const SizedBox(width: 12),
              Column(
                children: [
                  const Text('Open only'),
                  Switch(
                    value: _openOnly,
                    onChanged: tracking.loading
                        ? null
                        : (value) async {
                            setState(() {
                              _openOnly = value;
                              _initialFitDone = false;
                            });
                            await _loadTracking(forceFit: true);
                          },
                  ),
                ],
              ),
            ],
          ),
          if (tracking.error != null && tracking.error!.trim().isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: Colors.red.withValues(alpha: 0.2),
                  ),
                ),
                child: Text(
                  tracking.error!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            ),
        ],
      ),
    );
  }

  List<Polyline> _buildPolylines(DriverLocationFeed feed) {
    final polylines = <Polyline>[];
    final selected = _selectedAttendanceId;

    for (final session in feed.sessions) {
      final attendanceId = session.attendanceId;
      final sessionPoints = _pointsForAttendance(feed.mapPoints, attendanceId);
      if (sessionPoints.isEmpty) {
        continue;
      }
      final processed = _processRoute(sessionPoints);
      if (processed.route.length < 2) {
        continue;
      }

      final isSelected = selected != null && selected == attendanceId;
      final baseColor = _colorForAttendance(attendanceId);
      polylines.add(
        Polyline(
          points: processed.route,
          strokeWidth: isSelected ? 5 : 4,
          color: isSelected
              ? baseColor.withValues(alpha: 0.92)
              : baseColor.withValues(alpha: 0.55),
        ),
      );
    }

    return polylines;
  }

  List<Marker> _buildMarkers(DriverLocationFeed feed) {
    final markers = <Marker>[];
    final selected = _selectedAttendanceId;

    for (final session in feed.sessions) {
      final attendanceId = session.attendanceId;
      final sessionPoints = _pointsForAttendance(feed.mapPoints, attendanceId);
      if (sessionPoints.isEmpty) {
        continue;
      }

      final lastPoint = sessionPoints.last;
      final lastLatLng = LatLng(lastPoint.latitude, lastPoint.longitude);
      final prevPoint =
          sessionPoints.length >= 2 ? sessionPoints[sessionPoints.length - 2] : null;
      final prevLatLng = prevPoint == null
          ? null
          : LatLng(prevPoint.latitude, prevPoint.longitude);
      final bearing =
          prevLatLng == null ? 0 : _bearingDegrees(prevLatLng, lastLatLng);

      final baseColor = _colorForAttendance(attendanceId);
      final isSelected = selected != null && selected == attendanceId;

      if (session.statusLabel == 'Open') {
        final markerSize = isSelected ? 46.0 : 40.0;
        markers.add(
          Marker(
            point: lastLatLng,
            width: markerSize,
            height: markerSize,
            child: Transform.rotate(
              angle: (bearing * math.pi) / 180,
              child: Icon(
                Icons.local_shipping_rounded,
                color: baseColor,
                size: markerSize,
              ),
            ),
          ),
        );
      } else if (isSelected) {
        markers.add(
          Marker(
            point: lastLatLng,
            width: 36,
            height: 36,
            child: Icon(
              Icons.flag_circle_rounded,
              color: baseColor,
              size: 36,
            ),
          ),
        );
      }

      if (!isSelected) {
        continue;
      }

      final processed = _processRoute(sessionPoints);

      final startPoint = sessionPoints.firstWhere(
        (p) => p.pointType == 'start',
        orElse: () => sessionPoints.first,
      );
      final endPoint = sessionPoints.lastWhere(
        (p) => p.pointType == 'end',
        orElse: () => sessionPoints.last,
      );

      markers.add(
        Marker(
          point: LatLng(startPoint.latitude, startPoint.longitude),
          width: 34,
          height: 34,
          child: const Icon(
            Icons.circle,
            color: Color(0xFF12B981),
            size: 14,
          ),
        ),
      );

      if (session.statusLabel != 'Open' || endPoint.pointType == 'end') {
        markers.add(
          Marker(
            point: LatLng(endPoint.latitude, endPoint.longitude),
            width: 34,
            height: 34,
            child: const Icon(
              Icons.circle,
              color: Color(0xFFEF4444),
              size: 14,
            ),
          ),
        );
      }

      for (final stop in processed.stops) {
        markers.add(
          Marker(
            point: stop.point,
            width: 34,
            height: 34,
            child: const Icon(
              Icons.circle,
              color: Color(0xFFF59E0B),
              size: 14,
            ),
          ),
        );
      }
    }

    return markers;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Driver Tracking'),
        actions: [
          IconButton(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_month_outlined),
            tooltip: 'Select date',
          ),
          IconButton(
            onPressed: () => _loadTracking(),
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
          IconButton(
            onPressed: () {
              setState(() {
                _fullScreen = !_fullScreen;
              });
            },
            icon: Icon(_fullScreen ? Icons.fullscreen_exit : Icons.fullscreen),
            tooltip: 'Toggle full screen',
          ),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE9F2F2), Color(0xFFF5EFE7)],
          ),
        ),
        child: Consumer2<DriverTrackingProvider, TransporterProvider>(
          builder: (context, tracking, transporter, _) {
            final feed = tracking.feed;
            final drivers = transporter.drivers.toList()
              ..sort(
                (a, b) => a.username
                    .toLowerCase()
                    .compareTo(b.username.toLowerCase()),
              );

            final filters = _buildFilters(tracking: tracking, drivers: drivers);

            var initialCenter = _fallbackCenter;
            if (feed != null && feed.mapPoints.isNotEmpty) {
              for (final point in feed.mapPoints.reversed) {
                if (_isValidCoordinate(point.latitude, point.longitude)) {
                  initialCenter = LatLng(point.latitude, point.longitude);
                  break;
                }
              }
            }
            var polylines = const <Polyline>[];
            var markers = const <Marker>[];
            String? renderError;

            if (feed != null) {
              try {
                polylines = _buildPolylines(feed);
              } catch (_) {
                polylines = const <Polyline>[];
                renderError = 'Unable to render route on map.';
              }

              try {
                markers = _buildMarkers(feed);
              } catch (_) {
                markers = const <Marker>[];
                renderError ??= 'Unable to render markers on map.';
              }
            }

            return Column(
              children: [
                filters,
                Expanded(
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: FlutterMap(
                          mapController: _mapController,
                          options: MapOptions(
                            initialCenter: initialCenter,
                            initialZoom: 11.5,
                            keepAlive: true,
                            onPositionChanged: (camera, hasGesture) {
                              if (hasGesture && _followEnabled && !_followSuspended) {
                                setState(() {
                                  _followSuspended = true;
                                });
                              }
                            },
                          ),
                          children: [
                            TileLayer(
                              urlTemplate:
                                  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                              userAgentPackageName: 'com.tripmate.transporter',
                            ),
                            if (polylines.isNotEmpty)
                              PolylineLayer(polylines: polylines),
                            if (markers.isNotEmpty) MarkerLayer(markers: markers),
                          ],
                        ),
                      ),
                      if (tracking.loading)
                        Positioned.fill(
                          child: Container(
                            color: Colors.white.withValues(alpha: 0.6),
                            alignment: Alignment.center,
                            child: const CircularProgressIndicator(),
                          ),
                        ),
                      if (renderError != null)
                        Positioned(
                          bottom: 24,
                          left: 24,
                          right: 24,
                          child: Material(
                            elevation: 3,
                            borderRadius: BorderRadius.circular(14),
                            color: Colors.red.withValues(alpha: 0.08),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 12,
                              ),
                              child: Text(
                                renderError,
                                textAlign: TextAlign.center,
                                style: const TextStyle(color: Colors.red),
                              ),
                            ),
                          ),
                        ),
                      if (feed != null)
                        Positioned(
                          top: 12,
                          left: 12,
                          right: 12,
                          child: _buildSelectedOverlay(feed),
                        ),
                      Positioned(
                        bottom: 14,
                        right: 14,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            FloatingActionButton.small(
                              heroTag: 'runsBtn',
                              onPressed: feed == null ? null : () => _openRunsSheet(feed),
                              backgroundColor: const Color(0xFF0A6B6F),
                              child: const Icon(Icons.list_alt_rounded),
                            ),
                            const SizedBox(height: 10),
                            FloatingActionButton.small(
                              heroTag: 'followBtn',
                              onPressed: (_selectedAttendanceId == null)
                                  ? null
                                  : () {
                                      setState(() {
                                        _followEnabled = !_followEnabled;
                                        _followSuspended = false;
                                      });
                                      if (feed != null) {
                                        WidgetsBinding.instance.addPostFrameCallback((_) {
                                          if (!mounted) {
                                            return;
                                          }
                                          _maybeFollow(feed);
                                        });
                                      }
                                    },
                              backgroundColor: _followEnabled
                                  ? const Color(0xFF2563EB)
                                  : Colors.black87,
                              child: Icon(
                                _followEnabled
                                    ? Icons.my_location_rounded
                                    : Icons.location_searching_rounded,
                              ),
                            ),
                            const SizedBox(height: 10),
                            if (_followEnabled && _followSuspended)
                              FloatingActionButton.small(
                                heroTag: 'recenterBtn',
                                onPressed: feed == null
                                    ? null
                                    : () {
                                        setState(() {
                                          _followSuspended = false;
                                        });
                                        WidgetsBinding.instance.addPostFrameCallback((_) {
                                          if (!mounted) {
                                            return;
                                          }
                                          _maybeFollow(feed);
                                        });
                                      },
                                backgroundColor: const Color(0xFFE08D3C),
                                child: const Icon(Icons.center_focus_strong),
                              ),
                          ],
                        ),
                      ),
                      if (feed != null && feed.sessions.isEmpty)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text(
                              "No runs found. Try disabling 'Open only' or choosing another date.",
                              textAlign: TextAlign.center,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _StopInfo {
  const _StopInfo({
    required this.point,
    required this.durationMinutes,
    required this.firstPoint,
    required this.lastPoint,
  });

  final LatLng point;
  final double durationMinutes;
  final DriverLocationPoint firstPoint;
  final DriverLocationPoint lastPoint;
}

class _ProcessedRoute {
  const _ProcessedRoute({
    required this.route,
    required this.stops,
  });

  final List<LatLng> route;
  final List<_StopInfo> stops;
}
