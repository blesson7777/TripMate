import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/diesel_daily_route_plan.dart';
import '../../../domain/entities/tower_site_suggestion.dart';
import '../../providers/transporter_provider.dart';

class TowerRoutePlannerScreen extends StatefulWidget {
  const TowerRoutePlannerScreen({super.key});

  @override
  State<TowerRoutePlannerScreen> createState() => _TowerRoutePlannerScreenState();
}

class _TowerRoutePlannerScreenState extends State<TowerRoutePlannerScreen> {
  late final TextEditingController _searchController;
  DateTime _selectedDate = DateTime.now();
  int? _selectedVehicleId;
  bool _loadingPlan = false;
  double? _suggestedDistanceKm;
  List<_PlannerStopDraft> _draftStops = const [];

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initialize());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _initialize() async {
    final provider = context.read<TransporterProvider>();
    if (provider.vehicles.isEmpty) {
      await provider.loadDashboardData(force: true, prefetchHeavyData: false);
    }
    if (!mounted) {
      return;
    }
    if (_selectedVehicleId == null && provider.vehicles.isNotEmpty) {
      _selectedVehicleId = provider.vehicles.first.id;
    }
    await _loadExistingPlan();
    await _searchSites();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime.now().subtract(const Duration(days: 30)),
      lastDate: DateTime.now().add(const Duration(days: 90)),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _selectedDate = picked;
    });
    await _loadExistingPlan();
  }

  Future<void> _searchSites() async {
    await context.read<TransporterProvider>().loadTowerSites(
          query: _searchController.text.trim(),
          limit: 40,
        );
  }

  Future<void> _loadExistingPlan() async {
    final vehicleId = _selectedVehicleId;
    if (vehicleId == null) {
      return;
    }
    setState(() {
      _loadingPlan = true;
    });
    final provider = context.read<TransporterProvider>();
    await provider.loadDailyRoutePlan(
      vehicleId: vehicleId,
      date: _selectedDate,
      silent: true,
    );
    if (!mounted) {
      return;
    }
    final plan = provider.dailyRoutePlan;
    setState(() {
      _loadingPlan = false;
      _suggestedDistanceKm = plan?.estimatedDistanceKm;
      _draftStops = plan?.stops
              .map(
                (stop) => _PlannerStopDraft(
                  indusSiteId: stop.indusSiteId,
                  siteName: stop.siteName,
                  latitude: stop.latitude,
                  longitude: stop.longitude,
                  plannedQty: stop.plannedQty,
                  notes: stop.notes,
                ),
              )
              .toList(growable: true) ??
          <_PlannerStopDraft>[];
    });
  }

  Future<void> _savePlan() async {
    final vehicleId = _selectedVehicleId;
    if (vehicleId == null) {
      _showMessage('Select a vehicle first.');
      return;
    }
    if (_draftStops.isEmpty) {
      _showMessage('Add at least one tower site.');
      return;
    }
    final provider = context.read<TransporterProvider>();
    final success = await provider.saveDailyRoutePlan(
      vehicleId: vehicleId,
      date: _selectedDate,
      stops: _draftStops
          .asMap()
          .entries
          .map(
            (entry) => DieselDailyRouteStop(
              sequence: entry.key + 1,
              indusSiteId: entry.value.indusSiteId,
              siteName: entry.value.siteName,
              plannedQty: entry.value.plannedQty,
              latitude: entry.value.latitude,
              longitude: entry.value.longitude,
              notes: entry.value.notes,
              isFilled: false,
            ),
          )
          .toList(growable: false),
    );
    if (!mounted) {
      return;
    }
    if (!success) {
      _showMessage(provider.error ?? 'Unable to save route plan.');
      return;
    }
    await _loadExistingPlan();
    if (!mounted) {
      return;
    }
    _showMessage('Daily route plan saved.');
  }

  Future<void> _optimizeOrder() async {
    if (_draftStops.length < 2) {
      _showMessage('Add at least 2 stops to optimize.');
      return;
    }
    final provider = context.read<TransporterProvider>();
    final startPoint = provider.dailyRoutePlan?.startPoint;
    final suggestion = await provider.suggestTowerRoute(
      startLatitude: startPoint?.latitude,
      startLongitude: startPoint?.longitude,
      stops: _draftStops
          .asMap()
          .entries
          .map(
            (entry) => DieselDailyRouteStop(
              sequence: entry.key + 1,
              indusSiteId: entry.value.indusSiteId,
              siteName: entry.value.siteName,
              plannedQty: entry.value.plannedQty,
              latitude: entry.value.latitude,
              longitude: entry.value.longitude,
              notes: entry.value.notes,
              isFilled: false,
            ),
          )
          .toList(growable: false),
    );
    if (!mounted || suggestion == null) {
      return;
    }

    final reordered = <_PlannerStopDraft>[];
    for (final stop in suggestion.stops) {
      if (stop.isReturnLeg) {
        continue;
      }
      final originalIndex = stop.originalIndex;
      if (originalIndex == null ||
          originalIndex < 0 ||
          originalIndex >= _draftStops.length) {
        continue;
      }
      reordered.add(_draftStops[originalIndex]);
    }
    if (reordered.length != _draftStops.length) {
      return;
    }
    setState(() {
      _draftStops = reordered;
      _suggestedDistanceKm = suggestion.totalKm;
    });
    _showMessage(
      suggestion.usedFallback
          ? 'Route optimized with fallback order.'
          : 'Route optimized successfully.',
    );
  }

  Future<void> _openStopEditor(
    TowerSiteSuggestion site, {
    _PlannerStopDraft? existing,
  }) async {
    final qtyController = TextEditingController(
      text: existing == null ? '' : existing.plannedQty.toStringAsFixed(2),
    );
    final notesController = TextEditingController(text: existing?.notes ?? '');
    final formKey = GlobalKey<FormState>();

    final result = await showModalBottomSheet<_PlannerStopDraft>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
          ),
          child: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    existing == null ? 'Add Site to Plan' : 'Update Planned Quantity',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${site.siteName} (${site.indusSiteId})',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black54,
                        ),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: qtyController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Planned Fill Quantity',
                      hintText: 'Enter quantity in liters',
                    ),
                    validator: (value) {
                      final qty = double.tryParse((value ?? '').trim());
                      if (qty == null || qty < 0) {
                        return 'Enter a valid quantity.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: notesController,
                    decoration: const InputDecoration(
                      labelText: 'Notes (optional)',
                    ),
                    maxLines: 2,
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: () {
                        if (!formKey.currentState!.validate()) {
                          return;
                        }
                        Navigator.pop(
                          sheetContext,
                          _PlannerStopDraft(
                            indusSiteId: site.indusSiteId,
                            siteName: site.siteName,
                            latitude: site.latitude,
                            longitude: site.longitude,
                            plannedQty:
                                double.parse(qtyController.text.trim()),
                            notes: notesController.text.trim(),
                          ),
                        );
                      },
                      child: Text(existing == null ? 'Add Stop' : 'Update Stop'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );

    if (result == null || !mounted) {
      return;
    }
    final existingIndex = _draftStops.indexWhere(
      (stop) => stop.indusSiteId.toUpperCase() == site.indusSiteId.toUpperCase(),
    );
    setState(() {
      final nextStops = List<_PlannerStopDraft>.from(_draftStops);
      if (existingIndex >= 0) {
        nextStops[existingIndex] = result;
      } else {
        nextStops.add(result);
      }
      _draftStops = nextStops;
    });
  }

  void _removeStop(int index) {
    setState(() {
      final nextStops = List<_PlannerStopDraft>.from(_draftStops);
      nextStops.removeAt(index);
      _draftStops = nextStops;
    });
  }

  void _reorderStop(int oldIndex, int newIndex) {
    setState(() {
      final nextStops = List<_PlannerStopDraft>.from(_draftStops);
      if (newIndex > oldIndex) {
        newIndex -= 1;
      }
      final item = nextStops.removeAt(oldIndex);
      nextStops.insert(newIndex, item);
      _draftStops = nextStops;
    });
  }

  double get _totalPlannedQty => _draftStops.fold<double>(
        0,
        (sum, stop) => sum + stop.plannedQty,
      );

  String _vehicleLabel(int vehicleId, TransporterProvider provider) {
    for (final vehicle in provider.vehicles) {
      if (vehicle.id != vehicleId) {
        continue;
      }
      final model = vehicle.model.trim();
      if (model.isEmpty) {
        return vehicle.vehicleNumber;
      }
      return '${vehicle.vehicleNumber} • $model';
    }
    return 'Vehicle';
  }

  String _siteMetaLabel(TowerSiteSuggestion site) {
    final parts = <String>[site.indusSiteId];
    if (site.lastFilledQuantity != null) {
      parts.add('${site.lastFilledQuantity!.toStringAsFixed(2)} L');
    }
    if (site.lastFillDate != null) {
      final date = site.lastFillDate!;
      parts.add(
        '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}',
      );
    }
    return parts.join(' • ');
  }

  String _formatDate(DateTime value) {
    final day = value.day.toString().padLeft(2, '0');
    final month = value.month.toString().padLeft(2, '0');
    return '$day-$month-${value.year}';
  }

  String _formatDistance(double? km) {
    if (km == null) {
      return '-';
    }
    return '${km.toStringAsFixed(1)} km';
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Daily Route Planner'),
        actions: [
          IconButton(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_month_outlined),
            tooltip: 'Select date',
          ),
        ],
      ),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          final vehicles = provider.vehicles;
          final searchResults = provider.towerSites;
          return RefreshIndicator(
            onRefresh: _initialize,
            child: ListView(
              padding: const EdgeInsets.all(14),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        DropdownButtonFormField<int>(
                          initialValue: vehicles.any((item) => item.id == _selectedVehicleId)
                              ? _selectedVehicleId
                              : null,
                          decoration: const InputDecoration(
                            labelText: 'Select Vehicle',
                            prefixIcon: Icon(Icons.local_shipping_outlined),
                          ),
                          items: vehicles
                              .map(
                                (vehicle) => DropdownMenuItem<int>(
                                  value: vehicle.id,
                                  child: Text(vehicle.vehicleNumber),
                                ),
                              )
                              .toList(),
                          onChanged: (value) async {
                            setState(() {
                              _selectedVehicleId = value;
                            });
                            await _loadExistingPlan();
                          },
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            Chip(
                              avatar: const Icon(Icons.event_outlined, size: 18),
                              label: Text('Date: ${_formatDate(_selectedDate)}'),
                            ),
                            Chip(
                              avatar: const Icon(Icons.route_outlined, size: 18),
                              label: Text('Stops: ${_draftStops.length}'),
                            ),
                            Chip(
                              avatar:
                                  const Icon(Icons.local_gas_station_outlined, size: 18),
                              label: Text(
                                'Qty: ${_totalPlannedQty.toStringAsFixed(2)} L',
                              ),
                            ),
                            Chip(
                              avatar: const Icon(Icons.alt_route_outlined, size: 18),
                              label:
                                  Text('Estimated: ${_formatDistance(_suggestedDistanceKm)}'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            FilledButton.icon(
                              onPressed: provider.loading ? null : _savePlan,
                              icon: const Icon(Icons.save_outlined),
                              label: const Text('Save Plan'),
                            ),
                            OutlinedButton.icon(
                              onPressed: provider.loading ? null : _optimizeOrder,
                              icon: const Icon(Icons.auto_fix_high_outlined),
                              label: const Text('Optimize Order'),
                            ),
                            OutlinedButton.icon(
                              onPressed: provider.loading ? null : _loadExistingPlan,
                              icon: const Icon(Icons.refresh_rounded),
                              label: const Text('Reload Plan'),
                            ),
                          ],
                        ),
                        if (_loadingPlan || provider.loading)
                          const Padding(
                            padding: EdgeInsets.only(top: 12),
                            child: LinearProgressIndicator(),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Search Tower Sites',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _searchController,
                          textInputAction: TextInputAction.search,
                          onSubmitted: (_) => _searchSites(),
                          decoration: InputDecoration(
                            labelText: 'Search by site name or site ID',
                            prefixIcon: const Icon(Icons.search),
                            suffixIcon: _searchController.text.trim().isEmpty
                                ? null
                                : IconButton(
                                    onPressed: () {
                                      _searchController.clear();
                                      _searchSites();
                                    },
                                    icon: const Icon(Icons.close),
                                  ),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Align(
                          alignment: Alignment.centerRight,
                          child: FilledButton.icon(
                            onPressed: _searchSites,
                            icon: const Icon(Icons.search),
                            label: const Text('Search'),
                          ),
                        ),
                        const SizedBox(height: 12),
                        if (searchResults.isEmpty)
                          const Text('No tower sites found.')
                        else
                          ...searchResults.take(12).map((site) {
                            final existing = _draftStops
                                .cast<_PlannerStopDraft?>()
                                .firstWhere(
                                  (item) =>
                                      item?.indusSiteId.toUpperCase() ==
                                      site.indusSiteId.toUpperCase(),
                                  orElse: () => null,
                                );
                            return ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: CircleAvatar(
                                backgroundColor:
                                    const Color(0xFF0F766E).withValues(alpha: 0.12),
                                child: const Icon(
                                  Icons.place_outlined,
                                  color: Color(0xFF0F766E),
                                ),
                              ),
                              title: Text(site.siteName),
                              subtitle: Text(site.indusSiteId),
                              trailing: FilledButton.tonal(
                                onPressed: () => _openStopEditor(
                                  site,
                                  existing: existing,
                                ),
                                child: Text(existing == null ? 'Add' : 'Edit'),
                              ),
                            );
                          }),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Planned Stops',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                        const SizedBox(height: 10),
                        if (_draftStops.isEmpty)
                          const Text('Add tower sites to start planning.')
                        else
                          ReorderableListView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            itemCount: _draftStops.length,
                            onReorder: _reorderStop,
                            itemBuilder: (context, index) {
                              final stop = _draftStops[index];
                              return Card(
                                key: ValueKey(stop.indusSiteId),
                                margin: const EdgeInsets.only(bottom: 10),
                                child: ListTile(
                                  leading: ReorderableDragStartListener(
                                    index: index,
                                    child: const Icon(Icons.drag_indicator_rounded),
                                  ),
                                  title: Text(stop.siteName),
                                  subtitle: Text(
                                    '${stop.indusSiteId} • ${stop.plannedQty.toStringAsFixed(2)} L',
                                  ),
                                  trailing: Wrap(
                                    spacing: 4,
                                    children: [
                                      IconButton(
                                        onPressed: () => _openStopEditor(
                                          TowerSiteSuggestion(
                                            indusSiteId: stop.indusSiteId,
                                            siteName: stop.siteName,
                                            latitude: stop.latitude ?? 0,
                                            longitude: stop.longitude ?? 0,
                                            distanceMeters: 0,
                                          ),
                                          existing: stop,
                                        ),
                                        icon: const Icon(Icons.edit_outlined),
                                      ),
                                      IconButton(
                                        onPressed: () => _removeStop(index),
                                        icon: const Icon(Icons.delete_outline),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _PlannerStopDraft {
  const _PlannerStopDraft({
    required this.indusSiteId,
    required this.siteName,
    required this.plannedQty,
    this.latitude,
    this.longitude,
    this.notes = '',
  });

  final String indusSiteId;
  final String siteName;
  final double plannedQty;
  final double? latitude;
  final double? longitude;
  final String notes;
}
