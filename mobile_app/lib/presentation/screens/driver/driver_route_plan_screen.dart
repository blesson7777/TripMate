import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/services/location_service.dart';
import '../../../domain/entities/diesel_daily_route_plan.dart';
import '../../../domain/entities/diesel_route_suggestion.dart';
import '../../providers/driver_provider.dart';
import 'tower_diesel_entry_screen.dart';

class DriverRoutePlanScreen extends StatefulWidget {
  const DriverRoutePlanScreen({super.key});

  @override
  State<DriverRoutePlanScreen> createState() => _DriverRoutePlanScreenState();
}

class _DriverRoutePlanScreenState extends State<DriverRoutePlanScreen> {
  static const double _fillRadiusMeters = 150;

  final MapController _mapController = MapController();
  final LocationService _locationService = LocationService();
  final Distance _distance = const Distance();

  LocationResult? _driverLocation;
  bool _resolvingLocation = false;
  String? _locationError;
  bool _rerouting = false;
  DieselRouteSuggestion? _routeSuggestion;
  List<String> _manualPendingOrderKeys = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _refreshPlan());
  }

  Future<void> _refreshPlan() async {
    if (mounted) {
      setState(() {
        _routeSuggestion = null;
        _manualPendingOrderKeys = const [];
      });
    }
    await _refreshCurrentLocation();
    if (!mounted) {
      return;
    }
    await context.read<DriverProvider>().loadDailyRoutePlan(silent: true);
  }

  Future<void> _refreshCurrentLocation() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _resolvingLocation = true;
      _locationError = null;
    });
    try {
      final current = await _locationService.getCurrentLocation();
      if (!mounted) {
        return;
      }
      setState(() {
        _driverLocation = current;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _locationError = _friendlyErrorText(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _resolvingLocation = false;
        });
      }
    }
  }

  String _friendlyErrorText(Object error) {
    final raw = error.toString().trim();
    final cleaned = raw.replaceFirst('Exception: ', '').trim();
    if (cleaned.isEmpty) {
      return 'Unable to get location. Please try again.';
    }
    final lower = cleaned.toLowerCase();
    if (lower.contains('socketexception') ||
        lower.contains('handshakeexception') ||
        lower.contains('timeout') ||
        lower.contains('timed out') ||
        lower.contains('failed host lookup')) {
      return 'Unable to connect. Please check your internet connection and try again.';
    }
    if (lower.contains('platformexception')) {
      return 'Unable to get location. Please enable GPS and try again.';
    }
    return cleaned;
  }

  String _dateLabel(DateTime value) {
    final local = value.toLocal();
    final dd = local.day.toString().padLeft(2, '0');
    final mm = local.month.toString().padLeft(2, '0');
    return '$dd-$mm-${local.year}';
  }

  String _formatDistanceMeters(double distanceMeters) {
    if (distanceMeters <= 0) {
      return 'At tower';
    }
    final km = distanceMeters / 1000;
    return km >= 10
        ? '${km.toStringAsFixed(1)} km away'
        : '${km.toStringAsFixed(2)} km away';
  }

  String _formatQuantity(double value) {
    if (value == value.roundToDouble()) {
      return value.toStringAsFixed(0);
    }
    return value.toStringAsFixed(2);
  }

  String _formatDateTime(DateTime? value) {
    if (value == null) {
      return '-';
    }
    final local = value.toLocal();
    final dd = local.day.toString().padLeft(2, '0');
    final mm = local.month.toString().padLeft(2, '0');
    final hh = local.hour.toString().padLeft(2, '0');
    final min = local.minute.toString().padLeft(2, '0');
    return '$dd-$mm-${local.year} $hh:$min';
  }

  double? _distanceToStop(DieselDailyRouteStop stop) {
    if (_driverLocation == null || !stop.hasCoordinates) {
      return null;
    }
    return _distance.as(
      LengthUnit.Meter,
      LatLng(_driverLocation!.latitude, _driverLocation!.longitude),
      LatLng(stop.latitude!, stop.longitude!),
    );
  }

  bool _canFillStop(DieselDailyRouteStop stop) {
    final distanceMeters = _distanceToStop(stop);
    return !stop.isFilled &&
        distanceMeters != null &&
        distanceMeters <= _fillRadiusMeters;
  }

  List<DieselDailyRouteStop> _pendingStops(DieselDailyRoutePlan plan) {
    return plan.stops.where((stop) => !stop.isFilled).toList(growable: false);
  }

  List<DieselDailyRouteStop> _completedStops(DieselDailyRoutePlan plan) {
    return plan.stops.where((stop) => stop.isFilled).toList(growable: false);
  }

  String _pendingStopKey(DieselDailyRouteStop stop) {
    return [
      stop.sequence.toString(),
      stop.indusSiteId,
      stop.latitude?.toStringAsFixed(6) ?? 'na',
      stop.longitude?.toStringAsFixed(6) ?? 'na',
    ].join('|');
  }

  List<DieselDailyRouteStop> _orderedPendingStops(DieselDailyRoutePlan plan) {
    final pending = _pendingStops(plan);
    final pendingWithCoords =
        pending.where((stop) => stop.hasCoordinates).toList(growable: false);
    final pendingWithoutCoords =
        pending.where((stop) => !stop.hasCoordinates).toList(growable: false);
    final suggestion = _routeSuggestion;
    final reordered = <DieselDailyRouteStop>[];
    if (suggestion == null || suggestion.stops.isEmpty) {
      reordered.addAll(pending);
    } else {
      final consumed = <int>{};
      for (final stop in suggestion.stops) {
        final originalIndex = stop.originalIndex;
        if (originalIndex == null ||
            originalIndex < 0 ||
            originalIndex >= pendingWithCoords.length) {
          continue;
        }
        reordered.add(pendingWithCoords[originalIndex]);
        consumed.add(originalIndex);
      }
      for (var index = 0; index < pendingWithCoords.length; index += 1) {
        if (!consumed.contains(index)) {
          reordered.add(pendingWithCoords[index]);
        }
      }
      reordered.addAll(pendingWithoutCoords);
    }

    if (_manualPendingOrderKeys.isEmpty) {
      return _prioritizeCurrentTowerFirst(reordered);
    }

    final pendingByKey = {
      for (final stop in reordered) _pendingStopKey(stop): stop,
    };
    final manuallyOrdered = <DieselDailyRouteStop>[];
    final usedKeys = <String>{};
    for (final key in _manualPendingOrderKeys) {
      final stop = pendingByKey[key];
      if (stop == null) {
        continue;
      }
      manuallyOrdered.add(stop);
      usedKeys.add(key);
    }
    for (final stop in reordered) {
      final key = _pendingStopKey(stop);
      if (!usedKeys.contains(key)) {
        manuallyOrdered.add(stop);
      }
    }
    return _prioritizeCurrentTowerFirst(manuallyOrdered);
  }

  List<DieselDailyRouteStop> _prioritizeCurrentTowerFirst(
    List<DieselDailyRouteStop> stops,
  ) {
    if (stops.length < 2 || _driverLocation == null) {
      return stops;
    }

    final ranked =
        <({DieselDailyRouteStop stop, double distance, int index})>[];
    for (var index = 0; index < stops.length; index += 1) {
      final stop = stops[index];
      final distance = _distanceToStop(stop);
      if (distance == null || distance > _fillRadiusMeters) {
        continue;
      }
      ranked.add((stop: stop, distance: distance, index: index));
    }

    if (ranked.isEmpty) {
      return stops;
    }

    ranked.sort((a, b) {
      final compareDistance = a.distance.compareTo(b.distance);
      if (compareDistance != 0) {
        return compareDistance;
      }
      return a.index.compareTo(b.index);
    });

    final currentStop = ranked.first.stop;
    final prioritized = List<DieselDailyRouteStop>.from(stops);
    prioritized.remove(currentStop);
    prioritized.insert(0, currentStop);
    return prioritized;
  }

  int _displayStopSequence(
    DieselDailyRoutePlan plan,
    DieselDailyRouteStop stop,
  ) {
    if (stop.isFilled) {
      return stop.sequence;
    }
    final orderedPending = _orderedPendingStops(plan);
    final pendingIndex =
        orderedPending.indexWhere((item) => identical(item, stop));
    if (pendingIndex >= 0) {
      return pendingIndex + 1;
    }
    return stop.sequence;
  }

  Future<void> _suggestReroute(DieselDailyRoutePlan plan) async {
    final pendingWithCoords = _pendingStops(plan)
        .where((stop) => stop.hasCoordinates)
        .toList(growable: false);
    if (pendingWithCoords.length < 2) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'At least 2 mapped pending towers are needed for reroute suggestion.'),
        ),
      );
      return;
    }

    if (_driverLocation == null) {
      await _refreshCurrentLocation();
    }
    if (!mounted || _driverLocation == null) {
      return;
    }

    setState(() {
      _rerouting = true;
    });
    final suggestion = await context.read<DriverProvider>().suggestTowerRoute(
          startLatitude: _driverLocation!.latitude,
          startLongitude: _driverLocation!.longitude,
          stops: pendingWithCoords,
        );
    if (!mounted) {
      return;
    }
    setState(() {
      _rerouting = false;
      _routeSuggestion = suggestion;
      _manualPendingOrderKeys = const [];
    });
    if (suggestion == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.read<DriverProvider>().error ??
                'Unable to suggest a better route right now.',
          ),
        ),
      );
    }
  }

  Future<void> _resetRouteOrdering() async {
    if (_routeSuggestion == null && _manualPendingOrderKeys.isEmpty) {
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Reset Order?'),
        content: const Text(
          'This will remove the current reroute/manual order and bring back the saved route order.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) {
      return;
    }
    setState(() {
      _routeSuggestion = null;
      _manualPendingOrderKeys = const [];
    });
  }

  void _invertPendingOrder(DieselDailyRoutePlan plan) {
    final pendingStops = _orderedPendingStops(plan);
    if (pendingStops.length < 2) {
      return;
    }
    setState(() {
      _manualPendingOrderKeys =
          pendingStops.reversed.map(_pendingStopKey).toList(growable: false);
    });
  }

  Future<void> _openManualReorderSheet(DieselDailyRoutePlan plan) async {
    final pendingStops = _orderedPendingStops(plan);
    if (pendingStops.length < 2) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content:
              Text('At least 2 pending stops are needed for manual reorder.'),
        ),
      );
      return;
    }

    final result = await showModalBottomSheet<List<String>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) {
        final workingStops = List<DieselDailyRouteStop>.from(pendingStops);
        return SafeArea(
          child: StatefulBuilder(
            builder: (context, modalSetState) {
              return SizedBox(
                height: MediaQuery.of(context).size.height * 0.78,
                child: Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 6, 20, 10),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Manual Rearrange',
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleLarge
                                      ?.copyWith(
                                        fontWeight: FontWeight.w800,
                                      ),
                                ),
                              ],
                            ),
                          ),
                          TextButton.icon(
                            onPressed: () {
                              modalSetState(() {
                                workingStops.setAll(
                                  0,
                                  workingStops.reversed.toList(growable: false),
                                );
                              });
                            },
                            icon: const Icon(Icons.swap_vert_rounded),
                            label: const Text('Invert'),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: ReorderableListView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                        buildDefaultDragHandles: false,
                        itemCount: workingStops.length,
                        onReorder: (oldIndex, newIndex) {
                          modalSetState(() {
                            if (newIndex > oldIndex) {
                              newIndex -= 1;
                            }
                            final item = workingStops.removeAt(oldIndex);
                            workingStops.insert(newIndex, item);
                          });
                        },
                        itemBuilder: (context, index) {
                          final stop = workingStops[index];
                          final title = stop.siteName.trim().isEmpty
                              ? 'Tower ${stop.indusSiteId}'
                              : stop.siteName.trim();
                          return Container(
                            key: ValueKey(_pendingStopKey(stop)),
                            margin: const EdgeInsets.only(bottom: 10),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(16),
                              border:
                                  Border.all(color: const Color(0xFFD7E2E1)),
                            ),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: const Color(0xFF0A6B6F)
                                    .withValues(alpha: 0.12),
                                foregroundColor: const Color(0xFF0A6B6F),
                                child: Text(
                                  '${index + 1}',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800),
                                ),
                              ),
                              title: Text(
                                title,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700),
                              ),
                              subtitle: Text(
                                stop.indusSiteId.isEmpty
                                    ? 'Pending stop'
                                    : 'ID ${stop.indusSiteId} - ${_formatQuantity(stop.plannedQty)} L',
                              ),
                              trailing: ReorderableDragStartListener(
                                index: index,
                                child: const Icon(Icons.drag_handle_rounded),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                      child: Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(sheetContext),
                              child: const Text('Cancel'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: FilledButton(
                              onPressed: () => Navigator.pop(
                                sheetContext,
                                workingStops
                                    .map(_pendingStopKey)
                                    .toList(growable: false),
                              ),
                              child: const Text('Apply Order'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );

    if (result == null || !mounted) {
      return;
    }
    setState(() {
      _manualPendingOrderKeys = result;
    });
  }

  Future<void> _openNavigation(DieselDailyRouteStop stop) async {
    if (!stop.hasCoordinates) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Coordinates are not available for this tower.')),
      );
      return;
    }
    final lat = stop.latitude!.toStringAsFixed(6);
    final lon = stop.longitude!.toStringAsFixed(6);
    final navigationUri = Uri.parse('google.navigation:q=$lat,$lon');
    if (await canLaunchUrl(navigationUri)) {
      await launchUrl(navigationUri, mode: LaunchMode.externalApplication);
      return;
    }
    final mapsUri = Uri.parse(
      'https://www.google.com/maps/search/?api=1&query=$lat,$lon',
    );
    if (await launchUrl(mapsUri, mode: LaunchMode.externalApplication)) {
      return;
    }
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Unable to open Google Maps right now.')),
    );
  }

  Future<void> _openFullRoute(DieselDailyRoutePlan plan) async {
    final remainingStops = _orderedPendingStops(plan)
        .where((stop) => stop.hasCoordinates)
        .toList();
    if (remainingStops.isEmpty) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('No pending mapped towers left in this route.')),
      );
      return;
    }

    final waypoints = <String>[];
    if (_driverLocation != null) {
      waypoints.add(
          '${_driverLocation!.latitude.toStringAsFixed(6)},${_driverLocation!.longitude.toStringAsFixed(6)}');
    } else if (plan.startPoint != null) {
      waypoints.add(
          '${plan.startPoint!.latitude.toStringAsFixed(6)},${plan.startPoint!.longitude.toStringAsFixed(6)}');
    }
    for (final stop in remainingStops) {
      waypoints.add(
          '${stop.latitude!.toStringAsFixed(6)},${stop.longitude!.toStringAsFixed(6)}');
    }
    if (waypoints.length < 2) {
      return;
    }

    final url = Uri.parse(
      'https://www.google.com/maps/dir/?api=1&travelmode=driving&waypoints=${Uri.encodeComponent(waypoints.skip(1).take(waypoints.length - 2).join('|'))}&destination=${Uri.encodeComponent(waypoints.last)}&origin=${Uri.encodeComponent(waypoints.first)}',
    );
    if (!await launchUrl(url, mode: LaunchMode.externalApplication) &&
        mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to open route in Google Maps.')),
      );
    }
  }

  Future<void> _openFillEntry(
    DieselDailyRoutePlan plan,
    DieselDailyRouteStop stop,
  ) async {
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => TowerDieselEntryScreen(
          initialSiteId: stop.indusSiteId,
          initialSiteName: stop.siteName,
          initialTowerLatitude: stop.latitude,
          initialTowerLongitude: stop.longitude,
          initialFillDate: plan.planDate,
          lockPlannedStop: true,
          closeOnSuccess: true,
        ),
      ),
    );
    if (saved == true && mounted) {
      await _refreshPlan();
      if (!mounted) {
        return;
      }
      final title = stop.siteName.trim().isEmpty
          ? 'Tower ${stop.indusSiteId}'
          : stop.siteName.trim();
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Saved'),
          content: Text('$title filling saved successfully.'),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    }
  }

  Future<void> _handleStopPrimaryAction(
    DieselDailyRoutePlan plan,
    DieselDailyRouteStop stop,
  ) async {
    if (_canFillStop(stop)) {
      await _openFillEntry(plan, stop);
      return;
    }
    await _openNavigation(stop);
  }

  List<LatLng> _buildRemainingRoutePolyline(DieselDailyRoutePlan plan) {
    final pending = _orderedPendingStops(plan)
        .where((stop) => stop.hasCoordinates)
        .toList();
    if (pending.isEmpty) {
      return const [];
    }
    final points = <LatLng>[];
    if (_driverLocation != null) {
      points.add(LatLng(_driverLocation!.latitude, _driverLocation!.longitude));
    } else if (plan.startPoint != null) {
      points.add(LatLng(plan.startPoint!.latitude, plan.startPoint!.longitude));
    }
    for (final stop in pending) {
      points.add(LatLng(stop.latitude!, stop.longitude!));
    }
    return points.length >= 2 ? points : const [];
  }

  LatLng _resolveInitialCenter(DieselDailyRoutePlan? plan) {
    if (_driverLocation != null) {
      return LatLng(_driverLocation!.latitude, _driverLocation!.longitude);
    }
    if (plan?.startPoint != null) {
      return LatLng(plan!.startPoint!.latitude, plan.startPoint!.longitude);
    }
    for (final stop in plan?.stops ?? const <DieselDailyRouteStop>[]) {
      if (stop.hasCoordinates) {
        return LatLng(stop.latitude!, stop.longitude!);
      }
    }
    return const LatLng(9.931233, 76.267303);
  }

  List<Marker> _buildMarkers(DieselDailyRoutePlan plan) {
    final markers = <Marker>[];
    if (plan.startPoint != null) {
      markers.add(
        Marker(
          point: LatLng(plan.startPoint!.latitude, plan.startPoint!.longitude),
          width: 48,
          height: 48,
          child: const _MapBadge(
            icon: Icons.home_work_rounded,
            color: Color(0xFF0A6B6F),
            tooltip: 'Start point',
          ),
        ),
      );
    }
    for (final stop in plan.stops.where((item) => item.hasCoordinates)) {
      final near = _canFillStop(stop);
      final color = stop.isFilled
          ? const Color(0xFF16A34A)
          : (near ? const Color(0xFFF59E0B) : const Color(0xFFFACC15));
      final icon = stop.isFilled
          ? Icons.check_circle_rounded
          : (near
              ? Icons.local_gas_station_rounded
              : Icons.location_on_rounded);
      markers.add(
        Marker(
          point: LatLng(stop.latitude!, stop.longitude!),
          width: 48,
          height: 48,
          child: GestureDetector(
            onTap: () => _handleStopPrimaryAction(plan, stop),
            child: _MapBadge(
              icon: icon,
              color: color,
              tooltip:
                  stop.siteName.isNotEmpty ? stop.siteName : stop.indusSiteId,
            ),
          ),
        ),
      );
    }
    if (_driverLocation != null) {
      markers.add(
        Marker(
          point: LatLng(_driverLocation!.latitude, _driverLocation!.longitude),
          width: 46,
          height: 46,
          child: const _MapBadge(
            icon: Icons.my_location_rounded,
            color: Color(0xFF2563EB),
            tooltip: 'Your current location',
          ),
        ),
      );
    }
    return markers;
  }

  Widget _buildSummaryCard(DieselDailyRoutePlan plan) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFD7E2E1)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            plan.vehicleNumber,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            'Plan date: ${_dateLabel(plan.planDate)}',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: const Color(0xFF4B5563),
                ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _StatusBadge(
                label: 'Pending ${plan.pendingStopsCount}',
                color: const Color(0xFFFACC15),
                textColor: const Color(0xFF6B5A00),
              ),
              _StatusBadge(
                label: 'Filled ${plan.filledStopsCount}',
                color: const Color(0xFF16A34A),
              ),
              _StatusBadge(
                label: 'Qty ${_formatQuantity(plan.totalPlannedQty)} L',
                color: const Color(0xFF0A6B6F),
              ),
              if (plan.estimatedDistanceKm != null)
                _StatusBadge(
                  label:
                      'Est ${plan.estimatedDistanceKm!.toStringAsFixed(1)} km',
                  color: const Color(0xFF2563EB),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLegend() {
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      children: const [
        _StatusBadge(
            label: 'Pending',
            color: Color(0xFFFACC15),
            textColor: Color(0xFF6B5A00)),
        _StatusBadge(label: 'Near Tower', color: Color(0xFFF59E0B)),
        _StatusBadge(label: 'Filled', color: Color(0xFF16A34A)),
        _StatusBadge(label: 'You', color: Color(0xFF2563EB)),
      ],
    );
  }

  Widget _buildMapCanvas(
    DieselDailyRoutePlan plan,
    DriverProvider provider, {
    bool fullscreen = false,
  }) {
    final routePoints = _buildRemainingRoutePolyline(plan);
    final markers = _buildMarkers(plan);
    return Stack(
      children: [
        Positioned.fill(
          child: FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _resolveInitialCenter(plan),
              initialZoom: fullscreen ? 13.2 : 12.8,
              keepAlive: true,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.tripmate.driver',
              ),
              if (routePoints.isNotEmpty)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: routePoints,
                      strokeWidth: fullscreen ? 6 : 5,
                      color: const Color(0xFF0A6B6F),
                    ),
                  ],
                ),
              if (markers.isNotEmpty) MarkerLayer(markers: markers),
            ],
          ),
        ),
        Positioned(
          right: 12,
          bottom: 12,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              FloatingActionButton.small(
                heroTag: fullscreen
                    ? 'routeRefreshBtnFullscreen'
                    : 'routeRefreshBtn',
                onPressed: provider.loading ? null : _refreshPlan,
                backgroundColor: const Color(0xFF0A6B6F),
                child: provider.loading || _resolvingLocation
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor:
                              AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : const Icon(Icons.refresh),
              ),
              const SizedBox(height: 10),
              FloatingActionButton.small(
                heroTag: fullscreen ? 'routeNavBtnFullscreen' : 'routeNavBtn',
                onPressed: () => _openFullRoute(plan),
                backgroundColor: const Color(0xFF2563EB),
                child: const Icon(Icons.alt_route_rounded),
              ),
              const SizedBox(height: 10),
              FloatingActionButton.small(
                heroTag: fullscreen
                    ? 'routeCloseFullscreenBtn'
                    : 'routeFullscreenBtn',
                onPressed: fullscreen
                    ? () => Navigator.of(context).maybePop()
                    : () => _openFullscreenMap(plan),
                backgroundColor: const Color(0xFF111827),
                child: Icon(
                  fullscreen
                      ? Icons.fullscreen_exit_rounded
                      : Icons.fullscreen_rounded,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMap(DieselDailyRoutePlan plan, DriverProvider provider) {
    return Container(
      height: 360,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFFD7E2E1)),
      ),
      clipBehavior: Clip.antiAlias,
      child: _buildMapCanvas(plan, provider),
    );
  }

  Future<void> _openFullscreenMap(DieselDailyRoutePlan plan) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (routeContext) {
          return Consumer<DriverProvider>(
            builder: (context, provider, _) {
              return Scaffold(
                appBar: AppBar(
                  title: Text('Route Map - ${plan.vehicleNumber}'),
                ),
                body: SafeArea(
                  child: Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
                        child: _buildLegend(),
                      ),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          child: Container(
                            width: double.infinity,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(22),
                              border: Border.all(
                                color: const Color(0xFFD7E2E1),
                              ),
                            ),
                            clipBehavior: Clip.antiAlias,
                            child: _buildMapCanvas(
                              plan,
                              provider,
                              fullscreen: true,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildSectionHeader({
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
  }) {
    return Row(
      children: [
        CircleAvatar(
          radius: 18,
          backgroundColor: color.withValues(alpha: 0.12),
          child: Icon(icon, color: color, size: 18),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
              ),
              if (subtitle.trim().isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFF6B7280),
                      ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildStopCard(
    DieselDailyRoutePlan plan,
    DieselDailyRouteStop stop,
  ) {
    final near = _canFillStop(stop);
    final distanceMeters = _distanceToStop(stop);
    final isFilled = stop.isFilled;
    final borderColor = isFilled
        ? const Color(0xFF16A34A)
        : (near ? const Color(0xFFF59E0B) : const Color(0xFFFACC15));
    final backgroundColor = isFilled
        ? const Color(0xFFF0FDF4)
        : (near ? const Color(0xFFFFF7ED) : const Color(0xFFFEFCE8));
    final title = stop.siteName.trim().isEmpty
        ? 'Tower ${stop.indusSiteId}'
        : stop.siteName.trim();
    final displaySequence = _displayStopSequence(plan, stop);

    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: borderColor, width: 1.3),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 17,
                backgroundColor: borderColor,
                foregroundColor:
                    isFilled ? Colors.white : const Color(0xFF2F2F2F),
                child: Text(
                  displaySequence.toString(),
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 13),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: near && !isFilled
                      ? () => _openFillEntry(plan, stop)
                      : null,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text(
                      title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            color: near && !isFilled
                                ? const Color(0xFFB45309)
                                : const Color(0xFF111827),
                            decoration: near && !isFilled
                                ? TextDecoration.underline
                                : TextDecoration.none,
                          ),
                    ),
                  ),
                ),
              ),
              IconButton(
                onPressed: () => _handleStopPrimaryAction(plan, stop),
                tooltip: near && !isFilled ? 'Fill this tower' : 'Open in map',
                icon: Icon(
                  near && !isFilled
                      ? Icons.edit_location_alt_rounded
                      : Icons.map_outlined,
                  color: borderColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (stop.indusSiteId.isNotEmpty)
                _StatusBadge(
                  label: 'ID ${stop.indusSiteId}',
                  color: const Color(0xFF1F2937),
                ),
              _StatusBadge(
                label: isFilled ? 'Filled' : (near ? 'Near Tower' : 'Pending'),
                color: borderColor,
                textColor: isFilled
                    ? Colors.white
                    : (near
                        ? const Color(0xFF7C2D12)
                        : const Color(0xFF6B5A00)),
              ),
              if (distanceMeters != null && !isFilled)
                _StatusBadge(
                  label: _formatDistanceMeters(distanceMeters),
                  color: const Color(0xFF2563EB),
                ),
              _StatusBadge(
                label: 'Plan ${_formatQuantity(stop.plannedQty)} L',
                color: const Color(0xFF0A6B6F),
              ),
            ],
          ),
          if (stop.notes.trim().isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              stop.notes.trim(),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: const Color(0xFF4B5563),
                  ),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _openNavigation(stop),
                  icon: const Icon(Icons.navigation_outlined),
                  label: const Text('Navigate'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.icon(
                  onPressed: near && !isFilled
                      ? () => _openFillEntry(plan, stop)
                      : null,
                  icon: const Icon(Icons.local_gas_station_rounded),
                  label: Text(isFilled ? 'Completed' : 'Fill Here'),
                ),
              ),
            ],
          ),
          if (isFilled) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.7),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFBBF7D0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Filled ${stop.filledQty != null ? '${_formatQuantity(stop.filledQty!)} L' : ''}'
                        .trim(),
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF166534),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text('Updated: ${_formatDateTime(stop.filledAt)}'),
                  if (stop.filledBy.trim().isNotEmpty)
                    Text('By: ${stop.filledBy.trim()}'),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Daily Route Plan'),
        actions: [
          IconButton(
            onPressed: _refreshPlan,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh route',
          ),
        ],
      ),
      body: Consumer<DriverProvider>(
        builder: (context, provider, _) {
          final plan = provider.dailyRoutePlan;
          if (provider.loading && plan == null) {
            return const Center(child: CircularProgressIndicator());
          }
          if (plan == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.route_outlined,
                        size: 56, color: Color(0xFF0A6B6F)),
                    const SizedBox(height: 12),
                    Text(
                      provider.error ?? 'No route plan for today.',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: _refreshPlan,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Reload'),
                    ),
                  ],
                ),
              ),
            );
          }

          final pendingStops = _orderedPendingStops(plan);
          final completedStops = _completedStops(plan);
          final mappedPendingCount =
              pendingStops.where((stop) => stop.hasCoordinates).length;
          final hasCustomOrdering =
              _routeSuggestion != null || _manualPendingOrderKeys.isNotEmpty;

          return RefreshIndicator(
            onRefresh: _refreshPlan,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
              children: [
                _buildSummaryCard(plan),
                const SizedBox(height: 14),
                _buildMap(plan, provider),
                const SizedBox(height: 14),
                _buildLegend(),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: const Color(0xFFD7E2E1)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      FilledButton.icon(
                        onPressed: _rerouting || mappedPendingCount < 2
                            ? null
                            : () => _suggestReroute(plan),
                        icon: _rerouting
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(
                                    Colors.white,
                                  ),
                                ),
                              )
                            : const Icon(Icons.alt_route_rounded),
                        label: Text(
                          _routeSuggestion == null
                              ? 'Suggest Road Reroute'
                              : 'Refresh Reroute',
                        ),
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: [
                          OutlinedButton.icon(
                            onPressed: pendingStops.length < 2
                                ? null
                                : () => _openManualReorderSheet(plan),
                            icon: const Icon(Icons.drag_indicator_rounded),
                            label: Text(
                              _manualPendingOrderKeys.isEmpty
                                  ? 'Manual Rearrange'
                                  : 'Edit Manual Order',
                            ),
                          ),
                          OutlinedButton.icon(
                            onPressed: pendingStops.length < 2
                                ? null
                                : () => _invertPendingOrder(plan),
                            icon: const Icon(Icons.swap_vert_rounded),
                            label: const Text('Invert Order'),
                          ),
                          if (hasCustomOrdering)
                            OutlinedButton.icon(
                              onPressed: _resetRouteOrdering,
                              icon: const Icon(Icons.restart_alt_rounded),
                              label: const Text('Reset Order'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(
                        _manualPendingOrderKeys.isNotEmpty
                            ? 'Manual order active.'
                            : (_routeSuggestion == null
                                ? (mappedPendingCount < 2
                                    ? 'Need 2 mapped stops.'
                                    : 'Reroute ready.')
                                : 'Reroute active - ${_routeSuggestion!.totalKm.toStringAsFixed(1)} km'),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: const Color(0xFF4B5563),
                            ),
                      ),
                    ],
                  ),
                ),
                if (_locationError != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEE2E2),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFFFCA5A5)),
                    ),
                    child: Text(
                      _locationError!,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: const Color(0xFF991B1B),
                          ),
                    ),
                  ),
                ],
                const SizedBox(height: 18),
                _buildSectionHeader(
                  title: 'Pending stops',
                  subtitle: pendingStops.isEmpty
                      ? ''
                      : (_manualPendingOrderKeys.isNotEmpty
                          ? 'Manual order'
                          : (_routeSuggestion == null ? '' : 'Reroute order')),
                  icon: Icons.pending_actions_rounded,
                  color: const Color(0xFFF59E0B),
                ),
                if (pendingStops.isEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF0FDF4),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: const Color(0xFFBBF7D0)),
                    ),
                    child: const Text('All stops completed.'),
                  )
                else
                  ...pendingStops.map((stop) => _buildStopCard(plan, stop)),
                const SizedBox(height: 22),
                _buildSectionHeader(
                  title: 'Filled stops',
                  subtitle: completedStops.isEmpty ? '' : '',
                  icon: Icons.check_circle_outline_rounded,
                  color: const Color(0xFF16A34A),
                ),
                if (completedStops.isEmpty)
                  Container(
                    margin: const EdgeInsets.only(top: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF9FAFB),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Text('No completed stops.'),
                  )
                else
                  ...completedStops.map((stop) => _buildStopCard(plan, stop)),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({
    required this.label,
    required this.color,
    this.textColor = Colors.white,
  });

  final String label;
  final Color color;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                fontWeight: FontWeight.w700,
                color: textColor == Colors.white ? color : textColor,
              ),
        ),
      ),
    );
  }
}

class _MapBadge extends StatelessWidget {
  const _MapBadge({
    required this.icon,
    required this.color,
    required this.tooltip,
  });

  final IconData icon;
  final Color color;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          shape: BoxShape.circle,
          border: Border.all(color: color, width: 2),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.12),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        alignment: Alignment.center,
        child: Icon(icon, color: color, size: 24),
      ),
    );
  }
}
