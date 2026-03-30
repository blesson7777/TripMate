import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/offline_tower_diesel_queue_service.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';
import '../../../domain/entities/trip.dart';

class TowerDieselEntryScreen extends StatefulWidget {
  const TowerDieselEntryScreen({
    super.key,
    this.initialSiteId,
    this.initialSiteName,
    this.initialTowerLatitude,
    this.initialTowerLongitude,
    this.initialFillDate,
    this.lockPlannedStop = false,
    this.closeOnSuccess = false,
    this.offlineQueueOnly = false,
    this.onCloseRequested,
  });

  final String? initialSiteId;
  final String? initialSiteName;
  final double? initialTowerLatitude;
  final double? initialTowerLongitude;
  final DateTime? initialFillDate;
  final bool lockPlannedStop;
  final bool closeOnSuccess;
  final bool offlineQueueOnly;
  final VoidCallback? onCloseRequested;

  @override
  State<TowerDieselEntryScreen> createState() => _TowerDieselEntryScreenState();
}

class _TowerDieselEntryScreenState extends State<TowerDieselEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _siteIdController = TextEditingController();
  final _siteNameController = TextEditingController();
  final _fuelController = TextEditingController();
  final _piuReadingController = TextEditingController();
  final _dgHmrController = TextEditingController();
  final _openingStockController = TextEditingController();
  final _purposeController = TextEditingController(text: 'Diesel Filling');

  final _picker = ImagePicker();
  final _locationService = LocationService();

  DateTime _fillDate = DateTime.now();
  File? _logbookPhoto;
  bool _loadingNearbyTowers = false;
  String? _nearbyTowerMessage;
  bool _moduleLocked = false;
  String? _moduleLockMessage;
  bool _siteLookupLoading = false;
  Timer? _siteLookupDebounce;
  String _lastSiteLookupId = '';
  String? _matchedTowerSiteId;
  String? _matchedTowerSiteName;
  int? _selectedNearbyTowerIndex;
  double? _detectedTowerLatitude;
  double? _detectedTowerLongitude;

  @override
  void initState() {
    super.initState();
    _applyInitialValues();
    _siteIdController.addListener(_onSiteIdChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (widget.offlineQueueOnly) {
        return;
      }
      _initializeScreenData();
    });
  }

  @override
  void dispose() {
    _siteLookupDebounce?.cancel();
    _siteIdController.removeListener(_onSiteIdChanged);
    _siteIdController.dispose();
    _siteNameController.dispose();
    _fuelController.dispose();
    _piuReadingController.dispose();
    _dgHmrController.dispose();
    _openingStockController.dispose();
    _purposeController.dispose();
    super.dispose();
  }

  void _onSiteIdChanged() {
    if (widget.lockPlannedStop) {
      return;
    }
    final normalized = _siteIdController.text.trim();
    if (normalized.isEmpty) {
      _lastSiteLookupId = '';
      _matchedTowerSiteId = null;
      _matchedTowerSiteName = null;
      return;
    }
    if (normalized.length != 7) {
      _matchedTowerSiteId = null;
      _matchedTowerSiteName = null;
      return;
    }
    _siteLookupDebounce?.cancel();
    _siteLookupDebounce = Timer(const Duration(milliseconds: 450), () {
      _lookupTowerBySiteId(normalized);
    });
  }

  Future<void> _lookupTowerBySiteId(String siteId) async {
    if (widget.lockPlannedStop) {
      return;
    }
    final normalized = siteId.trim();
    if (normalized.isEmpty || normalized == _lastSiteLookupId) {
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _siteLookupLoading = true;
    });
    _lastSiteLookupId = normalized;

    final provider = context.read<DriverProvider>();
    final site = await provider.findTowerSiteById(indusSiteId: normalized);
    if (!mounted) {
      return;
    }
    setState(() {
      _siteLookupLoading = false;
    });

    if (site == null) {
      _matchedTowerSiteId = null;
      _matchedTowerSiteName = null;
      return;
    }
    final formattedName = _formatSiteName(site.siteName);
    _matchedTowerSiteId = site.indusSiteId;
    _matchedTowerSiteName = formattedName;
    _siteNameController.text = formattedName;
    if (site.latitude != 0 || site.longitude != 0) {
      _detectedTowerLatitude = site.latitude;
      _detectedTowerLongitude = site.longitude;
    }
  }

  String _dateLabel(DateTime value) {
    final day = value.day.toString().padLeft(2, '0');
    final month = value.month.toString().padLeft(2, '0');
    return '$day-$month-${value.year}';
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

  String _formatSiteName(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return '';
    }
    if (trimmed.contains(RegExp(r'[A-Z]'))) {
      return trimmed;
    }
    return trimmed.split(RegExp(r'\\s+')).map((part) {
      if (part.isEmpty) {
        return part;
      }
      final first = part.substring(0, 1).toUpperCase();
      final rest = part.length > 1 ? part.substring(1) : '';
      return '$first$rest';
    }).join(' ');
  }

  String _friendlyErrorText(Object error,
      {String fallback = 'Operation failed. Please try again.'}) {
    final raw = error.toString().trim();
    final cleaned = raw.replaceFirst('Exception: ', '').trim();
    if (cleaned.isEmpty) {
      return fallback;
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
      return fallback;
    }
    return cleaned;
  }

  void _applyInitialValues() {
    final initialSiteId = (widget.initialSiteId ?? '').trim();
    final initialSiteName = _formatSiteName(widget.initialSiteName ?? '');
    if (initialSiteId.isNotEmpty) {
      _siteIdController.text = initialSiteId;
      _matchedTowerSiteId = initialSiteId;
      _lastSiteLookupId = initialSiteId;
    }
    if (initialSiteName.isNotEmpty) {
      _siteNameController.text = initialSiteName;
      _matchedTowerSiteName = initialSiteName;
    }
    if (widget.initialFillDate != null) {
      _fillDate = widget.initialFillDate!;
    }
    if (widget.initialTowerLatitude != null) {
      _detectedTowerLatitude = widget.initialTowerLatitude;
    }
    if (widget.initialTowerLongitude != null) {
      _detectedTowerLongitude = widget.initialTowerLongitude;
    }
  }

  Future<void> _pickLogbookImage() async {
    final image =
        await _picker.pickImage(
          source: ImageSource.camera,
          imageQuality: 80,
          maxWidth: 1600,
          maxHeight: 1600,
        );
    if (image == null) {
      return;
    }
    final file = File(image.path);
    setState(() {
      _logbookPhoto = file;
    });
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _fillDate,
      firstDate: DateTime(DateTime.now().year - 1, 1, 1),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _fillDate = picked;
    });
  }

  Future<void> _initializeScreenData() async {
    final eligible = await _ensureDieselEligibility();
    if (!eligible) {
      return;
    }
    await _loadTodayRecords();
    if (!widget.lockPlannedStop) {
      await _loadNearbyTowerSuggestions();
    }
  }

  bool _containsDieselKeyword(String? value) {
    final normalized = (value ?? '').trim().toLowerCase();
    if (normalized.isEmpty) {
      return false;
    }
    return normalized.contains('diesel');
  }

  bool _hasActiveDieselDayTrip(List<Trip> trips) {
    return trips.any((trip) {
      final isOpenDayTrip =
          trip.isDayTrip && (trip.tripStatus ?? '').toUpperCase() == 'OPEN';
      if (!isOpenDayTrip) {
        return false;
      }
      return _containsDieselKeyword(trip.attendanceServiceName) ||
          _containsDieselKeyword(trip.attendanceServicePurpose) ||
          _containsDieselKeyword(trip.purpose);
    });
  }

  Future<bool> _ensureDieselEligibility() async {
    final auth = context.read<AuthProvider>();
    final enabled = auth.driverProfile?.dieselTrackingEnabled ?? false;
    if (!enabled) {
      if (!mounted) {
        return false;
      }
      setState(() {
        _moduleLocked = true;
        _moduleLockMessage =
            'Tower diesel module is disabled by your transporter.';
      });
      return false;
    }

    final provider = context.read<DriverProvider>();
    await provider.loadTrips(force: true, silent: true);
    final eligible = _hasActiveDieselDayTrip(provider.trips);
    if (!mounted) {
      return false;
    }
    setState(() {
      _moduleLocked = !eligible;
      _moduleLockMessage = eligible
          ? null
          : 'Start day with Diesel Filling Vehicle service to open this module.';
    });
    return eligible;
  }

  void _applyNearbyTowerSelection(int index, {bool force = false}) {
    final towers = context.read<DriverProvider>().nearbyTowerSites;
    if (index < 0 || index >= towers.length) {
      return;
    }
    final site = towers[index];
    final hasExistingInput = _siteIdController.text.trim().isNotEmpty ||
        _siteNameController.text.trim().isNotEmpty;
    if (!force && hasExistingInput) {
      return;
    }
    _siteIdController.text = site.indusSiteId;
    final formattedName = _formatSiteName(site.siteName);
    _siteNameController.text = formattedName;
    _matchedTowerSiteId = site.indusSiteId;
    _matchedTowerSiteName = formattedName;
  }

  Future<void> _loadNearbyTowerSuggestions({bool autoFill = true}) async {
    setState(() {
      _loadingNearbyTowers = true;
      _nearbyTowerMessage = null;
    });
    try {
      final location = await _locationService.getCurrentLocation();
      _detectedTowerLatitude = location.latitude;
      _detectedTowerLongitude = location.longitude;

      if (!mounted) {
        return;
      }
      final provider = context.read<DriverProvider>();
      await provider.loadNearbyTowerSites(
        latitude: location.latitude,
        longitude: location.longitude,
        radiusMeters: 100,
      );
      if (!mounted) {
        return;
      }
      if (provider.error != null && provider.nearbyTowerSites.isEmpty) {
        setState(() {
          _selectedNearbyTowerIndex = null;
          _nearbyTowerMessage = provider.error;
        });
        return;
      }
      final towers = provider.nearbyTowerSites;
      setState(() {
        if (towers.isEmpty) {
          _selectedNearbyTowerIndex = null;
          _nearbyTowerMessage = 'No previously saved tower found within 100m.';
        } else {
          _selectedNearbyTowerIndex = autoFill ? 0 : null;
          if (autoFill) {
            _nearbyTowerMessage = towers.length == 1
                ? 'Nearby tower found and auto-filled.'
                : 'Multiple nearby towers found. Select one.';
          } else {
            _nearbyTowerMessage = towers.length == 1
                ? 'Nearby tower found. Select it to auto-fill.'
                : 'Nearby towers found. Select one to auto-fill.';
          }
        }
      });
      if (towers.isNotEmpty && autoFill) {
        _applyNearbyTowerSelection(0);
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _nearbyTowerMessage =
            'Location unavailable. Enter site details manually.';
      });
    } finally {
      if (mounted) {
        setState(() {
          _loadingNearbyTowers = false;
        });
      }
    }
  }

  Future<void> _submit() async {
    if (_moduleLocked) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_moduleLockMessage ?? 'Module is locked.')),
      );
      return;
    }
    if (!_formKey.currentState!.validate()) {
      return;
    }
    if (_logbookPhoto == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Logbook photo is required.')),
      );
      return;
    }

    final confirmSiteNameUpdate = await _confirmSiteNameUpdateIfNeeded();
    if (!mounted || confirmSiteNameUpdate == null) {
      return;
    }

    final provider = context.read<DriverProvider>();
    final auth = context.read<AuthProvider>();
    final readingsEnabled = auth.driverProfile?.dieselReadingsEnabled ??
        auth.session?.dieselReadingsEnabled ??
        false;
    double? towerLatitude = _detectedTowerLatitude;
    double? towerLongitude = _detectedTowerLongitude;
    try {
      final location = await _locationService.getCurrentLocation();
      towerLatitude = location.latitude;
      towerLongitude = location.longitude;
      _detectedTowerLatitude = towerLatitude;
      _detectedTowerLongitude = towerLongitude;
    } catch (_) {
      // Keep previous captured location if live GPS is unavailable.
    }

    double? piuReading;
    double? dgHmr;
    double? openingStock;
    if (readingsEnabled) {
      piuReading = double.tryParse(_piuReadingController.text.trim());
      dgHmr = double.tryParse(_dgHmrController.text.trim());
      openingStock = double.tryParse(_openingStockController.text.trim());
      if (piuReading == null || dgHmr == null || openingStock == null) {
        if (!mounted) {
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Fill PIU, DG HMR, and Opening Stock.')),
        );
        return;
      }
    }

    final success = widget.offlineQueueOnly
        ? await provider.queueTowerDieselRecord(
            indusSiteId: _siteIdController.text.trim(),
            siteName: _formatSiteName(_siteNameController.text),
            fuelFilled: double.parse(_fuelController.text.trim()),
            piuReading: piuReading,
            dgHmr: dgHmr,
            openingStock: openingStock,
            confirmSiteNameUpdate: confirmSiteNameUpdate,
            towerLatitude: towerLatitude,
            towerLongitude: towerLongitude,
            purpose: _purposeController.text.trim(),
            fillDate: _fillDate,
            logbookPhoto: _logbookPhoto!,
          )
        : await provider.addTowerDieselRecord(
            indusSiteId: _siteIdController.text.trim(),
            siteName: _formatSiteName(_siteNameController.text),
            fuelFilled: double.parse(_fuelController.text.trim()),
            piuReading: piuReading,
            dgHmr: dgHmr,
            openingStock: openingStock,
            confirmSiteNameUpdate: confirmSiteNameUpdate,
            towerLatitude: towerLatitude,
            towerLongitude: towerLongitude,
            purpose: _purposeController.text.trim(),
            fillDate: _fillDate,
            logbookPhoto: _logbookPhoto!,
          );
    if (!mounted) {
      return;
    }
    if (success) {
      _resetFormAfterSuccess();

      if (!widget.offlineQueueOnly) {
        unawaited(_loadTodayRecords());
        if (!widget.lockPlannedStop) {
          unawaited(_loadNearbyTowerSuggestions(autoFill: false));
        }
      }

      if (widget.closeOnSuccess && mounted) {
        Navigator.pop(context, true);
        return;
      }
      if (!mounted) {
        return;
      }
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Success'),
          content: Text(
            widget.offlineQueueOnly
                ? 'Tower diesel entry saved offline. It will sync automatically when internet is back.'
                : 'Tower diesel entry saved successfully.',
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(provider.error ?? 'Failed to save entry.')),
      );
    }
  }

  Future<bool?> _confirmSiteNameUpdateIfNeeded() async {
    if (widget.offlineQueueOnly) {
      return false;
    }
    final siteId = _siteIdController.text.trim();
    final siteName = _formatSiteName(_siteNameController.text);
    final matchedSiteId = (_matchedTowerSiteId ?? '').trim();
    final matchedSiteName = (_matchedTowerSiteName ?? '').trim();
    if (matchedSiteId != siteId ||
        siteName.isEmpty ||
        siteName.toLowerCase() == matchedSiteName.toLowerCase()) {
      return false;
    }
    return showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final existingLabel =
            matchedSiteName.isEmpty ? 'no saved site name' : matchedSiteName;
        return AlertDialog(
          title: const Text('Update Site Name?'),
          content: Text(
            'Site ID $siteId is already saved as "$existingLabel". Are you sure to update it to "$siteName"?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, null),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Yes, Update'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _loadTodayRecords() async {
    final now = DateTime.now();
    await context.read<DriverProvider>().loadTowerDieselRecords(
          month: now.month,
          year: now.year,
        );
  }

  void _resetFormAfterSuccess() {
    setState(() {
      _logbookPhoto = null;
      _fillDate = widget.initialFillDate ?? DateTime.now();
    });
    if (widget.lockPlannedStop) {
      _applyInitialValues();
    } else {
      _siteIdController.clear();
      _siteNameController.clear();
      _matchedTowerSiteId = null;
      _matchedTowerSiteName = null;
    }
    _fuelController.clear();
    _piuReadingController.clear();
    _dgHmrController.clear();
    _openingStockController.clear();
    _purposeController.text = 'Diesel Filling';
  }

  Future<void> _deleteRecord(int recordId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Delete Filling'),
          content: const Text('Delete this tower diesel filling entry?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) {
      return;
    }
    final now = DateTime.now();
    final provider = context.read<DriverProvider>();
    final ok = await provider.deleteTowerDieselRecord(
      recordId: recordId,
      month: now.month,
      year: now.year,
    );
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'Entry deleted.' : (provider.error ?? 'Delete failed.'),
        ),
      ),
    );
  }

  Future<Uint8List> _fetchLogbookBytes(String imageUrl) async {
    final session = context.read<AuthProvider>().session;
    if (session == null) {
      throw Exception('Session expired. Please login again.');
    }
    final response = await http.get(
      Uri.parse(imageUrl),
      headers: {
        'Accept': '*/*',
        'Authorization': 'Bearer ${session.accessToken}',
      },
    );
    if (response.statusCode != 200) {
      if (response.statusCode == 401) {
        throw Exception('Session expired. Please login again.');
      }
      throw Exception('Unable to load logbook photo. Please try again.');
    }
    return response.bodyBytes;
  }

  void _openLogbook(String imageUrl) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420, maxHeight: 620),
            child: Column(
              children: [
                ListTile(
                  title: const Text('Captured Logbook'),
                  trailing: IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(dialogContext),
                  ),
                ),
                const Divider(height: 1),
                Expanded(
                  child: FutureBuilder<Uint8List>(
                    future: _fetchLogbookBytes(imageUrl),
                    builder: (context, snapshot) {
                      if (snapshot.connectionState == ConnectionState.waiting) {
                        return const Center(child: CircularProgressIndicator());
                      }
                      if (snapshot.hasError) {
                        return Center(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              _friendlyErrorText(
                                snapshot.error!,
                                fallback: 'Unable to load logbook photo.',
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        );
                      }
                      final bytes = snapshot.data;
                      if (bytes == null || bytes.isEmpty) {
                        return const Center(
                            child: Text('Photo not available.'));
                      }
                      return InteractiveViewer(
                        child: Image.memory(
                          bytes,
                          fit: BoxFit.contain,
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildNearbyTowerSection(DriverProvider provider) {
    final towers = provider.nearbyTowerSites;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.my_location_outlined, size: 18),
            const SizedBox(width: 6),
            Text(
              'Nearby Towers (100m)',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const Spacer(),
            TextButton.icon(
              onPressed: provider.loading || _loadingNearbyTowers
                  ? null
                  : _loadNearbyTowerSuggestions,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Check'),
            ),
          ],
        ),
        if (_loadingNearbyTowers)
          const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: LinearProgressIndicator(),
          ),
        if (_nearbyTowerMessage != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              _nearbyTowerMessage!,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: const Color(0xFF285E55),
                  ),
            ),
          ),
        if (towers.isNotEmpty)
          DropdownButtonFormField<int>(
            key: ValueKey(_selectedNearbyTowerIndex),
            initialValue: _selectedNearbyTowerIndex,
            decoration: const InputDecoration(
              labelText: 'Select Nearby Tower',
            ),
            items: List.generate(towers.length, (index) {
              final site = towers[index];
              final label =
                  '${_formatSiteName(site.siteName)} (${site.indusSiteId}) - ${_formatDistanceKm(site.distanceMeters)}';
              return DropdownMenuItem<int>(
                value: index,
                child: Text(
                  label,
                  overflow: TextOverflow.ellipsis,
                ),
              );
            }),
            onChanged: provider.loading || _loadingNearbyTowers
                ? null
                : (value) {
                    if (value == null) {
                      return;
                    }
                    setState(() {
                      _selectedNearbyTowerIndex = value;
                    });
                    _applyNearbyTowerSelection(value, force: true);
                  },
          ),
      ],
    );
  }

  Widget _buildTodayFillingSection(DriverProvider provider) {
    final today = DateTime.now();
    final records = provider.towerDieselRecords.where((item) {
      final date = item.effectiveDate.toLocal();
      return date.year == today.year &&
          date.month == today.month &&
          date.day == today.day;
    }).toList();
    final totalFilled = records.fold<double>(
      0,
      (sum, item) => sum + item.fuelFilled,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 20),
        Row(
          children: [
            const Icon(Icons.list_alt_outlined, size: 20),
            const SizedBox(width: 8),
            Text(
              'Today Filled Sites (${records.length})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const Spacer(),
            IconButton(
              onPressed: provider.loading ? null : _loadTodayRecords,
              tooltip: 'Refresh',
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.teal.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: Colors.teal.withValues(alpha: 0.22),
            ),
          ),
          child: Row(
            children: [
              const Icon(Icons.local_gas_station_outlined, size: 18),
              const SizedBox(width: 8),
              const Text('Total Filled Today'),
              const Spacer(),
              Text(
                '${totalFilled.toStringAsFixed(2)} L',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ),
        if (records.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFFF5F7F7),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text('No tower diesel filling added today.'),
          )
        else
          ...records.map((item) {
            final date = item.effectiveDate.toLocal();
            final dateText =
                '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}';
            final siteName = item.siteName.trim().isEmpty
                ? 'Site name not available'
                : item.siteName.trim();
            return Card(
              margin: const EdgeInsets.only(top: 10),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFE2F3EE),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFF0D7A67)),
                      ),
                      child: Text(
                        siteName,
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF085B4E),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text('Date: $dateText'),
                    if (item.indusSiteId.isNotEmpty)
                      Text('Indus Site ID: ${item.indusSiteId}'),
                    Text(
                        'Fuel Filled: ${item.fuelFilled.toStringAsFixed(2)} L'),
                    Text(
                      'KM: ${item.startKm ?? 0} -> ${item.endKm ?? 0} (Run ${item.runKm})',
                    ),
                    if (item.purpose.trim().isNotEmpty)
                      Text('Purpose: ${item.purpose.trim()}'),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        if (item.logbookPhotoUrl.trim().isNotEmpty)
                          TextButton.icon(
                            onPressed: () => _openLogbook(item.logbookPhotoUrl),
                            icon: const Icon(Icons.photo_outlined),
                            label: const Text('View Logbook'),
                          ),
                        const Spacer(),
                        IconButton(
                          onPressed: provider.loading
                              ? null
                              : () => _deleteRecord(item.id),
                          tooltip: 'Delete filling',
                          icon: const Icon(Icons.delete_outline,
                              color: Color(0xFFC0392B)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final readingsEnabled = auth.driverProfile?.dieselReadingsEnabled ??
        auth.session?.dieselReadingsEnabled ??
        false;
    if (_moduleLocked) {
      return Scaffold(
        appBar: AppBar(title: const Text('Tower Diesel Filling')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.lock_outline,
                    size: 56, color: Color(0xFF0F766E)),
                const SizedBox(height: 12),
                Text(
                  _moduleLockMessage ??
                      'Start day with Diesel Filling Vehicle service to open this module.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _initializeScreenData,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Recheck'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        leading: widget.offlineQueueOnly
            ? IconButton(
                onPressed: widget.onCloseRequested,
                icon: const Icon(Icons.arrow_back_rounded),
              )
            : null,
        title: Text(
          widget.offlineQueueOnly
              ? 'Offline Diesel Queue'
              : 'Tower Diesel Filling',
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  if (widget.offlineQueueOnly)
                    ValueListenableBuilder<int>(
                      valueListenable:
                          OfflineTowerDieselQueueService.instance.pendingCount,
                      builder: (context, pendingCount, _) {
                        return Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          margin: const EdgeInsets.only(bottom: 12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF0F9FF),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: const Color(0xFF7DD3FC),
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Offline queue mode',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleSmall
                                    ?.copyWith(fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                pendingCount == 0
                                    ? 'Saved entries will sync automatically when internet comes back.'
                                    : '$pendingCount saved entr${pendingCount == 1 ? 'y is' : 'ies are'} waiting to sync.',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(height: 1.35),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  if (widget.lockPlannedStop)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF7ED),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFF59E0B)),
                      ),
                      child: Text(
                        'This stop comes from the daily route plan. Site details are locked so you can update the filling quickly when you reach the tower.',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: const Color(0xFF9A3412),
                            ),
                      ),
                    ),
                  OutlinedButton.icon(
                    onPressed: provider.loading ? null : _pickLogbookImage,
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: Text(
                      _logbookPhoto == null
                          ? 'Capture Logbook Photo'
                          : 'Retake Logbook Photo',
                    ),
                  ),
                  if (_logbookPhoto != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.file(
                          _logbookPhoto!,
                          height: 170,
                          width: double.infinity,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  if (!widget.lockPlannedStop && !widget.offlineQueueOnly) ...[
                    const SizedBox(height: 12),
                    _buildNearbyTowerSection(provider),
                    const SizedBox(height: 8),
                  ] else
                    const SizedBox(height: 12),
                  TextFormField(
                    controller: _siteIdController,
                    keyboardType: TextInputType.number,
                    readOnly: widget.lockPlannedStop,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(7),
                    ],
                    decoration: const InputDecoration(
                      labelText: 'Indus Site ID',
                      hintText: '7 digit site ID',
                    ),
                    validator: (value) {
                      final normalized = (value ?? '').trim();
                      if (normalized.isEmpty) {
                        return 'Enter site ID.';
                      }
                      if (!RegExp(r'^\d{7}$').hasMatch(normalized)) {
                        return 'Site ID must be exactly 7 digits.';
                      }
                      return null;
                    },
                  ),
                  if (_siteLookupLoading)
                    const Padding(
                      padding: EdgeInsets.only(top: 6),
                      child: LinearProgressIndicator(minHeight: 2),
                    ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: _siteNameController,
                    readOnly: widget.lockPlannedStop,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(labelText: 'Site Name'),
                    validator: (value) {
                      final normalized = (value ?? '').trim();
                      if (normalized.isEmpty &&
                          ((_matchedTowerSiteId ?? '').trim() !=
                              _siteIdController.text.trim())) {
                        return 'Enter site name.';
                      }
                      if (RegExp(r'^\d+$').hasMatch(normalized)) {
                        return 'Site name cannot contain only numbers.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: _fuelController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Fuel Filled'),
                    validator: (value) {
                      final parsed = double.tryParse((value ?? '').trim());
                      if (parsed == null || parsed <= 0) {
                        return 'Enter valid fuel value.';
                      }
                      return null;
                    },
                  ),
                  if (readingsEnabled) ...[
                    const SizedBox(height: 12),
                    Text(
                      'Tower Readings',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: _piuReadingController,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'PIU Reading',
                        hintText: 'Enter PIU reading',
                      ),
                      validator: (value) {
                        if (!readingsEnabled) {
                          return null;
                        }
                        final parsed = double.tryParse((value ?? '').trim());
                        if (parsed == null) {
                          return 'Enter PIU reading.';
                        }
                        if (parsed < 0) {
                          return 'PIU reading cannot be negative.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _dgHmrController,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'DG HMR',
                        hintText: 'Enter DG HMR reading',
                      ),
                      validator: (value) {
                        if (!readingsEnabled) {
                          return null;
                        }
                        final parsed = double.tryParse((value ?? '').trim());
                        if (parsed == null) {
                          return 'Enter DG HMR.';
                        }
                        if (parsed < 0) {
                          return 'DG HMR cannot be negative.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _openingStockController,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'Opening Stock',
                        hintText: 'Enter opening diesel stock',
                      ),
                      validator: (value) {
                        if (!readingsEnabled) {
                          return null;
                        }
                        final parsed = double.tryParse((value ?? '').trim());
                        if (parsed == null) {
                          return 'Enter opening stock.';
                        }
                        if (parsed < 0) {
                          return 'Opening stock cannot be negative.';
                        }
                        return null;
                      },
                    ),
                  ],
                  const SizedBox(height: 10),
                  TextFormField(
                    controller: _purposeController,
                    decoration: const InputDecoration(labelText: 'Purpose'),
                    validator: (value) {
                      if ((value ?? '').trim().isEmpty) {
                        return 'Enter purpose.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 10),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.calendar_month_outlined),
                    title: const Text('Fill Date'),
                    subtitle: Text(_dateLabel(_fillDate)),
                    trailing: TextButton(
                      onPressed: provider.loading || widget.lockPlannedStop
                          ? null
                          : _pickDate,
                      child: const Text('Change'),
                    ),
                  ),
                  const SizedBox(height: 14),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save Tower Diesel Entry'),
                  ),
                  if (!widget.offlineQueueOnly)
                    _buildTodayFillingSection(provider),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
