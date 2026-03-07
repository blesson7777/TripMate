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
    final enabled = context.read<AuthProvider>().driverProfile?.dieselTrackingEnabled ?? false;
    if (!enabled) {
      return;
    }
    await _refreshCurrentLocation();
    await _loadSites();
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
        _locationError = error.toString();
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
    return km >= 10 ? '${km.toStringAsFixed(1)} km' : '${km.toStringAsFixed(2)} km';
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
          Text('Last filled quantity: ${_formatQuantity(site.lastFilledQuantity)}'),
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
                final fallbackCenter = sites.isNotEmpty
                    ? LatLng(sites.first.latitude, sites.first.longitude)
                    : const LatLng(10.8505, 76.2711);

                return Stack(
                  children: [
                    Positioned.fill(
                      child: provider.loading && sites.isEmpty
                          ? const Center(child: CircularProgressIndicator())
                          : FlutterMap(
                              mapController: _mapController,
                              options: MapOptions(
                                initialCenter: _selectedSite != null
                                    ? LatLng(_selectedSite!.latitude, _selectedSite!.longitude)
                                    : fallbackCenter,
                                initialZoom: sites.isNotEmpty ? 12.5 : 6,
                              ),
                              children: [
                                TileLayer(
                                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                                  userAgentPackageName: 'com.tripmate.driver',
                                ),
                                MarkerLayer(
                                  markers: [
                                    for (final site in sites)
                                      Marker(
                                        point: LatLng(site.latitude, site.longitude),
                                        width: 44,
                                        height: 44,
                                        child: GestureDetector(
                                          onTap: () => _selectSite(site),
                                          child: Icon(
                                            Icons.location_on,
                                            color: _selectedSite?.indusSiteId == site.indusSiteId
                                                ? const Color(0xFFE08D3C)
                                                : const Color(0xFF0A6B6F),
                                            size: _selectedSite?.indusSiteId == site.indusSiteId ? 38 : 32,
                                          ),
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
                                  suffixIcon: (_searchController.text.isNotEmpty || _appliedQuery.isNotEmpty)
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
                                  if (_resolvingLocation)
                                    const Chip(
                                      avatar: SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(strokeWidth: 2),
                                      ),
                                      label: Text('Updating location'),
                                    ),
                                  Chip(
                                    avatar: const Icon(Icons.place_outlined, size: 18),
                                    label: Text('${sites.length} sites'),
                                  ),
                                  if (_appliedQuery.isNotEmpty)
                                    Chip(
                                      avatar: const Icon(Icons.filter_alt_outlined, size: 18),
                                      label: Text(_appliedQuery),
                                    ),
                                ],
                              ),
                              if (_locationError != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  _locationError!,
                                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                        color: Theme.of(context).colorScheme.error,
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
                            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
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
                                    ? const Center(child: CircularProgressIndicator())
                                    : sites.isEmpty
                                        ? ListView(
                                            controller: scrollController,
                                            padding: const EdgeInsets.fromLTRB(12, 24, 12, 24),
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
                                            padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
                                            itemCount: sites.length + (_selectedSite != null ? 1 : 0),
                                            separatorBuilder: (_, __) => const SizedBox(height: 8),
                                            itemBuilder: (context, index) {
                                              if (_selectedSite != null && index == 0) {
                                                return _buildSelectedSiteCard(_selectedSite!);
                                              }
                                              final adjustedIndex =
                                                  index - (_selectedSite != null ? 1 : 0);
                                              final site = sites[adjustedIndex];
                                              final selected =
                                                  _selectedSite?.indusSiteId == site.indusSiteId;
                                              return Card(
                                                color: selected
                                                    ? const Color(0xFF0A6B6F)
                                                        .withValues(alpha: 0.08)
                                                    : null,
                                                child: ListTile(
                                                  onTap: () => _selectSite(site),
                                                  leading: Icon(
                                                    Icons.place_outlined,
                                                    color: selected
                                                        ? const Color(0xFF0A6B6F)
                                                        : const Color(0xFFE08D3C),
                                                  ),
                                                  title: Text(
                                                    site.siteName.trim().isEmpty
                                                        ? 'Unnamed Tower Site'
                                                        : site.siteName,
                                                  ),
                                                  subtitle: Text(_siteSubtitle(site)),
                                                  isThreeLine: true,
                                                  trailing: IconButton(
                                                    icon: const Icon(Icons.navigation_outlined),
                                                    onPressed: () => _openNavigation(site),
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
