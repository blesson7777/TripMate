import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/services/location_service.dart';
import '../../../domain/entities/tower_site_suggestion.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';

class TowerSiteMapScreen extends StatefulWidget {
  const TowerSiteMapScreen({super.key});

  @override
  State<TowerSiteMapScreen> createState() => _TowerSiteMapScreenState();
}

class _TowerSiteMapScreenState extends State<TowerSiteMapScreen> {
  final MapController _mapController = MapController();
  final TextEditingController _searchController = TextEditingController();
  final LocationService _locationService = LocationService();
  TowerSiteSuggestion? _selectedSite;
  String _appliedQuery = '';
  LocationResult? _driverLocation;
  bool _resolvingLocation = false;
  String? _locationError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    if (!mounted) {
      return;
    }
    final enabled =
        context.read<AuthProvider>().driverProfile?.dieselTrackingEnabled ??
            false;
    if (!enabled) {
      return;
    }
    await _refreshCurrentLocation();
    await _loadSites();
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

  Future<void> _refreshCurrentLocation() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _resolvingLocation = true;
      _locationError = null;
    });
    try {
      final location = await _locationService.getCurrentLocation();
      if (!mounted) {
        return;
      }
      setState(() {
        _driverLocation = location;
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

  Future<void> _loadSites({String? query, bool refreshLocation = false}) async {
    if (refreshLocation) {
      await _refreshCurrentLocation();
    }
    if (!mounted) {
      return;
    }
    final provider = context.read<DriverProvider>();
    await provider.loadTowerSites(
      query: query,
      limit: 250,
      latitude: _driverLocation?.latitude,
      longitude: _driverLocation?.longitude,
    );
    if (!mounted) {
      return;
    }
    final sites = provider.towerSites;
    final hadSelection = _selectedSite != null;
    TowerSiteSuggestion? retained;
    if (_selectedSite != null) {
      for (final item in sites) {
        if (item.indusSiteId == _selectedSite!.indusSiteId) {
          retained = item;
          break;
        }
      }
    }
    setState(() {
      _selectedSite = retained ?? (sites.isNotEmpty ? sites.first : null);
    });
    final hasActiveQuery = (query ?? _appliedQuery).trim().isNotEmpty;
    if (retained != null || hadSelection || hasActiveQuery) {
      _moveToSelectedSite();
      return;
    }
    if (_driverLocation != null) {
      _moveToDriverLocation();
      return;
    }
    _moveToSelectedSite();
  }

  Future<void> _applySearch() async {
    FocusScope.of(context).unfocus();
    final query = _searchController.text.trim();
    setState(() {
      _appliedQuery = query;
    });
    await _loadSites(query: query);
  }

  Future<void> _clearSearch() async {
    _searchController.clear();
    setState(() {
      _appliedQuery = '';
    });
    await _loadSites(refreshLocation: true);
  }

  void _selectSite(TowerSiteSuggestion site) {
    setState(() {
      _selectedSite = site;
    });
    _moveToSelectedSite();
  }

  void _moveToSelectedSite() {
    final site = _selectedSite;
    if (site == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _mapController.move(
        LatLng(site.latitude, site.longitude),
        14.5,
      );
    });
  }

  void _moveToDriverLocation() {
    final current = _driverLocation;
    if (current == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _mapController.move(
        LatLng(current.latitude, current.longitude),
        14.5,
      );
    });
  }

  Future<void> _openNavigation(TowerSiteSuggestion site) async {
    final lat = site.latitude.toStringAsFixed(6);
    final lon = site.longitude.toStringAsFixed(6);
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
      const SnackBar(content: Text('Unable to open Google Maps navigation.')),
    );
  }

  String _formatDate(DateTime? date) {
    if (date == null) {
      return '-';
    }
    final local = date.toLocal();
    final dd = local.day.toString().padLeft(2, '0');
    final mm = local.month.toString().padLeft(2, '0');
    return '$dd-$mm-${local.year}';
  }

  String _formatDistanceKm(double distanceMeters) {
    if (distanceMeters <= 0) {
      return '-';
    }
    final km = distanceMeters / 1000;
    return km >= 10
        ? '${km.toStringAsFixed(1)} km'
        : '${km.toStringAsFixed(2)} km';
  }

  String _formatQuantity(double? quantity) {
    if (quantity == null) {
      return '-';
    }
    return '${quantity.toStringAsFixed(2)} L';
  }

  String _siteSubtitle(TowerSiteSuggestion site) {
    final lines = <String>[
      'ID: ${site.indusSiteId}',
      'Distance: ${_formatDistanceKm(site.distanceMeters)}',
      'Last filled qty: ${_formatQuantity(site.lastFilledQuantity)}',
      'Last filled: ${_formatDate(site.lastFillDate)}',
    ];
    return lines.join('\n');
  }

  Widget _buildSelectedSiteCard(TowerSiteSuggestion site) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0A6B6F).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFF0A6B6F).withValues(alpha: 0.18),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            site.siteName.trim().isEmpty ? 'Unnamed Tower Site' : site.siteName,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 4),
          Text('Site ID: ${site.indusSiteId}'),
          Text(
            'Coordinates: ${site.latitude.toStringAsFixed(6)}, ${site.longitude.toStringAsFixed(6)}',
          ),
          Text('Distance from you: ${_formatDistanceKm(site.distanceMeters)}'),
          Text(
              'Last filled quantity: ${_formatQuantity(site.lastFilledQuantity)}'),
          Text('Last filled: ${_formatDate(site.lastFillDate)}'),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: () => _openNavigation(site),
            icon: const Icon(Icons.navigation_outlined),
            label: const Text('Navigate with Google Maps'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dieselEnabled = context.select(
      (AuthProvider auth) => auth.driverProfile?.dieselTrackingEnabled ?? false,
    );
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tower Site Map'),
      ),
      body: !dieselEnabled
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Tower site map is available only when the diesel filling module is enabled by your transporter.',
                  textAlign: TextAlign.center,
                ),
              ),
            )
          : Consumer<DriverProvider>(
              builder: (context, provider, _) {
                final sites = provider.towerSites;
                final fallbackCenter = _driverLocation != null
                    ? LatLng(
                        _driverLocation!.latitude, _driverLocation!.longitude)
                    : (sites.isNotEmpty
                        ? LatLng(sites.first.latitude, sites.first.longitude)
                        : const LatLng(10.8505, 76.2711));

                return Stack(
                  children: [
                    Positioned.fill(
                      child: provider.loading && sites.isEmpty
                          ? const Center(child: CircularProgressIndicator())
                          : FlutterMap(
                              mapController: _mapController,
                              options: MapOptions(
                                initialCenter: _selectedSite != null
                                    ? LatLng(_selectedSite!.latitude,
                                        _selectedSite!.longitude)
                                    : fallbackCenter,
                                initialZoom: sites.isNotEmpty ? 12.5 : 6,
                              ),
                              children: [
                                TileLayer(
                                  urlTemplate:
                                      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                                  userAgentPackageName: 'com.tripmate.driver',
                                ),
                                MarkerLayer(
                                  markers: [
                                    for (final site in sites)
                                      Marker(
                                        point: LatLng(
                                            site.latitude, site.longitude),
                                        width: 58,
                                        height: 74,
                                        alignment: Alignment.bottomCenter,
                                        child: GestureDetector(
                                          onTap: () => _selectSite(site),
                                          child: _TowerMapMarker(
                                            selected:
                                                _selectedSite?.indusSiteId ==
                                                    site.indusSiteId,
                                          ),
                                        ),
                                      ),
                                    if (_driverLocation != null)
                                      Marker(
                                        point: LatLng(
                                          _driverLocation!.latitude,
                                          _driverLocation!.longitude,
                                        ),
                                        width: 48,
                                        height: 48,
                                        child: const Tooltip(
                                          message: 'Your current location',
                                          child: _DriverLocationMarker(),
                                        ),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                    ),
                    Positioned(
                      top: 12,
                      left: 12,
                      right: 12,
                      child: Material(
                        elevation: 4,
                        color: Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(20),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              TextField(
                                controller: _searchController,
                                textInputAction: TextInputAction.search,
                                onChanged: (_) => setState(() {}),
                                onSubmitted: (_) => _applySearch(),
                                decoration: InputDecoration(
                                  labelText: 'Search by site name or site ID',
                                  prefixIcon: const Icon(Icons.search),
                                  suffixIcon:
                                      (_searchController.text.isNotEmpty ||
                                              _appliedQuery.isNotEmpty)
                                          ? IconButton(
                                              icon: const Icon(Icons.close),
                                              onPressed: _clearSearch,
                                            )
                                          : null,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  FilledButton.icon(
                                    onPressed: _applySearch,
                                    icon: const Icon(Icons.search),
                                    label: const Text('Search'),
                                  ),
                                  OutlinedButton.icon(
                                    onPressed: () => _loadSites(
                                      query: _appliedQuery,
                                      refreshLocation: true,
                                    ),
                                    icon: const Icon(Icons.refresh),
                                    label: const Text('Reload'),
                                  ),
                                  OutlinedButton.icon(
                                    onPressed: _driverLocation == null
                                        ? () => _loadSites(
                                              query: _appliedQuery,
                                              refreshLocation: true,
                                            )
                                        : _moveToDriverLocation,
                                    icon: const Icon(Icons.my_location_rounded),
                                    label: const Text('My Location'),
                                  ),
                                  if (_resolvingLocation)
                                    const Chip(
                                      avatar: SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2),
                                      ),
                                      label: Text('Updating location'),
                                    ),
                                  Chip(
                                    avatar: const Icon(Icons.place_outlined,
                                        size: 18),
                                    label: Text('${sites.length} sites'),
                                  ),
                                  if (_appliedQuery.isNotEmpty)
                                    Chip(
                                      avatar: const Icon(
                                          Icons.filter_alt_outlined,
                                          size: 18),
                                      label: Text(_appliedQuery),
                                    ),
                                ],
                              ),
                              if (_locationError != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  _locationError!,
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodySmall
                                      ?.copyWith(
                                        color:
                                            Theme.of(context).colorScheme.error,
                                      ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ),
                    DraggableScrollableSheet(
                      initialChildSize: 0.32,
                      minChildSize: 0.18,
                      maxChildSize: 0.82,
                      builder: (context, scrollController) {
                        return Container(
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.surface,
                            borderRadius: const BorderRadius.vertical(
                                top: Radius.circular(24)),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.14),
                                blurRadius: 18,
                                offset: const Offset(0, -4),
                              ),
                            ],
                          ),
                          child: Column(
                            children: [
                              const SizedBox(height: 10),
                              Container(
                                width: 54,
                                height: 6,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(999),
                                ),
                              ),
                              const SizedBox(height: 8),
                              Expanded(
                                child: provider.loading && sites.isNotEmpty
                                    ? const Center(
                                        child: CircularProgressIndicator())
                                    : sites.isEmpty
                                        ? ListView(
                                            controller: scrollController,
                                            padding: const EdgeInsets.fromLTRB(
                                                12, 24, 12, 24),
                                            children: const [
                                              SizedBox(height: 100),
                                              Center(
                                                child: Text(
                                                  'No tower sites found for the current search.',
                                                ),
                                              ),
                                            ],
                                          )
                                        : ListView.separated(
                                            controller: scrollController,
                                            padding: const EdgeInsets.fromLTRB(
                                                12, 0, 12, 24),
                                            itemCount: sites.length +
                                                (_selectedSite != null ? 1 : 0),
                                            separatorBuilder: (_, __) =>
                                                const SizedBox(height: 8),
                                            itemBuilder: (context, index) {
                                              if (_selectedSite != null &&
                                                  index == 0) {
                                                return _buildSelectedSiteCard(
                                                    _selectedSite!);
                                              }
                                              final adjustedIndex = index -
                                                  (_selectedSite != null
                                                      ? 1
                                                      : 0);
                                              final site = sites[adjustedIndex];
                                              final selected =
                                                  _selectedSite?.indusSiteId ==
                                                      site.indusSiteId;
                                              return Card(
                                                color: selected
                                                    ? const Color(0xFF0A6B6F)
                                                        .withValues(alpha: 0.08)
                                                    : null,
                                                child: ListTile(
                                                  onTap: () =>
                                                      _selectSite(site),
                                                  leading: Icon(
                                                    Icons.place_outlined,
                                                    color: selected
                                                        ? const Color(
                                                            0xFF0A6B6F)
                                                        : const Color(
                                                            0xFFE08D3C),
                                                  ),
                                                  title: Text(
                                                    site.siteName.trim().isEmpty
                                                        ? 'Unnamed Tower Site'
                                                        : site.siteName,
                                                  ),
                                                  subtitle:
                                                      Text(_siteSubtitle(site)),
                                                  isThreeLine: true,
                                                  trailing: IconButton(
                                                    icon: const Icon(Icons
                                                        .navigation_outlined),
                                                    onPressed: () =>
                                                        _openNavigation(site),
                                                  ),
                                                ),
                                              );
                                            },
                                          ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ],
                );
              },
            ),
    );
  }
}

class _DriverLocationMarker extends StatelessWidget {
  const _DriverLocationMarker();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: const Color(0xFF2563EB), width: 2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      alignment: Alignment.center,
      child: const Icon(
        Icons.my_location_rounded,
        color: Color(0xFF2563EB),
        size: 24,
      ),
    );
  }
}

class _TowerMapMarker extends StatelessWidget {
  const _TowerMapMarker({required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: selected ? 'Selected tower site' : 'Tower site',
      child: CustomPaint(
        painter: _TowerMapMarkerPainter(selected: selected),
        child: const SizedBox.expand(),
      ),
    );
  }
}

class _TowerMapMarkerPainter extends CustomPainter {
  const _TowerMapMarkerPainter({required this.selected});

  final bool selected;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final scale = selected ? 1.0 : 0.9;
    final centerX = w / 2;
    final baseY = h - 7;
    final topY = 7 + ((1 - scale) * 8);
    final towerBottomY = baseY - 8;
    final towerHalfBase = 16 * scale;
    final towerHalfMid = 8 * scale;
    final towerHalfTop = 2.8 * scale;
    final accent = selected ? const Color(0xFFE08D3C) : const Color(0xFF0A6B6F);
    const metalLight = Color(0xFFE8EEF2);
    const metalMid = Color(0xFF9AA8B0);
    const metalDark = Color(0xFF56636B);

    final shadowPaint = Paint()
      ..color = Colors.black.withValues(alpha: selected ? 0.26 : 0.18)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(centerX, baseY - 1),
        width: selected ? 36 : 30,
        height: selected ? 10 : 8,
      ),
      shadowPaint,
    );

    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          accent.withValues(alpha: selected ? 0.28 : 0.16),
          accent.withValues(alpha: 0),
        ],
      ).createShader(Rect.fromCircle(
        center: Offset(centerX, towerBottomY - 12),
        radius: 31,
      ));
    canvas.drawCircle(Offset(centerX, towerBottomY - 12), 31, glowPaint);

    final backLegPaint = Paint()
      ..color = metalMid
      ..strokeWidth = 3 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
      Offset(centerX - towerHalfTop, topY + 6),
      Offset(centerX - towerHalfBase, towerBottomY),
      backLegPaint,
    );
    canvas.drawLine(
      Offset(centerX + towerHalfTop, topY + 6),
      Offset(centerX + towerHalfBase, towerBottomY),
      backLegPaint,
    );

    final facePath = ui.Path()
      ..moveTo(centerX, topY)
      ..lineTo(centerX - towerHalfBase, towerBottomY)
      ..lineTo(centerX + towerHalfBase, towerBottomY)
      ..close();
    final facePaint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [metalLight, metalMid, metalDark],
      ).createShader(facePath.getBounds());
    canvas.drawPath(facePath, facePaint);

    final innerCutout = ui.Path()
      ..moveTo(centerX, topY + 9)
      ..lineTo(centerX - towerHalfMid, towerBottomY - 8)
      ..lineTo(centerX + towerHalfMid, towerBottomY - 8)
      ..close();
    canvas.drawPath(
        innerCutout, Paint()..color = Colors.white.withValues(alpha: 0.90));

    final beamPaint = Paint()
      ..color = metalDark
      ..strokeWidth = 2 * scale
      ..strokeCap = StrokeCap.round;
    final levels = <double>[
      topY + 13,
      topY + 25,
      topY + 38,
      topY + 51,
    ];
    for (final y in levels) {
      final t = ((y - topY) / (towerBottomY - topY)).clamp(0.0, 1.0);
      final half = towerHalfTop + ((towerHalfBase - towerHalfTop) * t);
      canvas.drawLine(
          Offset(centerX - half, y), Offset(centerX + half, y), beamPaint);
    }
    for (var i = 0; i < levels.length - 1; i++) {
      final y1 = levels[i];
      final y2 = levels[i + 1];
      final t1 = ((y1 - topY) / (towerBottomY - topY)).clamp(0.0, 1.0);
      final t2 = ((y2 - topY) / (towerBottomY - topY)).clamp(0.0, 1.0);
      final half1 = towerHalfTop + ((towerHalfBase - towerHalfTop) * t1);
      final half2 = towerHalfTop + ((towerHalfBase - towerHalfTop) * t2);
      canvas.drawLine(
          Offset(centerX - half1, y1), Offset(centerX + half2, y2), beamPaint);
      canvas.drawLine(
          Offset(centerX + half1, y1), Offset(centerX - half2, y2), beamPaint);
    }

    final frontPaint = Paint()
      ..color = const Color(0xFF2F3A40)
      ..strokeWidth = 2.4 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(
        Offset(centerX, topY), Offset(centerX, towerBottomY), frontPaint);

    final dishPaint = Paint()..color = accent;
    final dishStroke = Paint()
      ..color = const Color(0xFF263238)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final leftDish = Rect.fromCenter(
      center: Offset(centerX - 15 * scale, topY + 22 * scale),
      width: 14 * scale,
      height: 9 * scale,
    );
    final rightDish = Rect.fromCenter(
      center: Offset(centerX + 15 * scale, topY + 29 * scale),
      width: 14 * scale,
      height: 9 * scale,
    );
    canvas.drawArc(leftDish, math.pi * 0.64, math.pi * 1.15, false,
        dishPaint..style = PaintingStyle.fill);
    canvas.drawArc(leftDish, math.pi * 0.64, math.pi * 1.15, false, dishStroke);
    canvas.drawArc(rightDish, math.pi * 1.20, math.pi * 1.15, false,
        dishPaint..style = PaintingStyle.fill);
    canvas.drawArc(
        rightDish, math.pi * 1.20, math.pi * 1.15, false, dishStroke);

    final beaconPaint = Paint()
      ..color = selected ? const Color(0xFFFFD166) : accent;
    canvas.drawCircle(Offset(centerX, topY), selected ? 4.3 : 3.7, beaconPaint);
    canvas.drawCircle(
      Offset(centerX, topY),
      selected ? 7.5 : 6.5,
      Paint()
        ..color = beaconPaint.color.withValues(alpha: 0.18)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );

    final basePaint = Paint()
      ..shader = LinearGradient(
        colors: [accent, accent.withValues(alpha: 0.62)],
      ).createShader(Rect.fromLTWH(centerX - 17, towerBottomY - 2, 34, 10));
    final baseRect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: Offset(centerX, towerBottomY + 2),
        width: selected ? 34 : 30,
        height: selected ? 9 : 8,
      ),
      const Radius.circular(5),
    );
    canvas.drawRRect(baseRect, basePaint);
  }

  @override
  bool shouldRepaint(covariant _TowerMapMarkerPainter oldDelegate) {
    return oldDelegate.selected != selected;
  }
}
