import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';
import '../../../domain/entities/trip.dart';

class TowerDieselEntryScreen extends StatefulWidget {
  const TowerDieselEntryScreen({super.key});

  @override
  State<TowerDieselEntryScreen> createState() => _TowerDieselEntryScreenState();
}

class _TowerDieselEntryScreenState extends State<TowerDieselEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _siteIdController = TextEditingController();
  final _siteNameController = TextEditingController();
  final _fuelController = TextEditingController();
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
    _siteIdController.addListener(_onSiteIdChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
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
    _purposeController.dispose();
    super.dispose();
  }

  void _onSiteIdChanged() {
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
    _matchedTowerSiteId = site.indusSiteId;
    _matchedTowerSiteName = site.siteName;
    _siteNameController.text = site.siteName;
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
    return km >= 10 ? '${km.toStringAsFixed(1)} km' : '${km.toStringAsFixed(2)} km';
  }

  Future<void> _pickLogbookImage() async {
    final image =
        await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
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
    await _loadNearbyTowerSuggestions();
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
      final isOpenDayTrip = trip.isDayTrip &&
          (trip.tripStatus ?? '').toUpperCase() == 'OPEN';
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
    _siteNameController.text = site.siteName;
    _matchedTowerSiteId = site.indusSiteId;
    _matchedTowerSiteName = site.siteName;
  }

  Future<void> _loadNearbyTowerSuggestions() async {
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
          _selectedNearbyTowerIndex = 0;
          _nearbyTowerMessage = towers.length == 1
              ? 'Nearby tower found and auto-filled.'
              : 'Multiple nearby towers found. Select one.';
        }
      });
      if (towers.isNotEmpty) {
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

    final success = await provider.addTowerDieselRecord(
      indusSiteId: _siteIdController.text.trim(),
      siteName: _siteNameController.text.trim(),
      fuelFilled: double.parse(_fuelController.text.trim()),
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(success
              ? 'Tower diesel entry saved.'
              : provider.error ?? 'Failed')),
    );
    if (success) {
      setState(() {
        _logbookPhoto = null;
        _fillDate = DateTime.now();
      });
      _siteIdController.clear();
      _siteNameController.clear();
      _matchedTowerSiteId = null;
      _matchedTowerSiteName = null;
      _fuelController.clear();
      _purposeController.text = 'Diesel Filling';
      await _loadNearbyTowerSuggestions();
    }
  }

  Future<bool?> _confirmSiteNameUpdateIfNeeded() async {
    final siteId = _siteIdController.text.trim();
    final siteName = _siteNameController.text.trim();
    final matchedSiteId = (_matchedTowerSiteId ?? '').trim();
    final matchedSiteName = (_matchedTowerSiteName ?? '').trim();
    if (
      matchedSiteId != siteId ||
      siteName.isEmpty ||
      siteName == matchedSiteName
    ) {
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
      final body = response.body.toLowerCase();
      if (body.startsWith('<!doctype html') ||
          body.startsWith('<html') ||
          body.contains('<title>')) {
        throw Exception('Server returned HTML instead of image.');
      }
      throw Exception(
          'Unable to load logbook photo (HTTP ${response.statusCode}).');
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
                              snapshot.error
                                  .toString()
                                  .replaceFirst('Exception: ', ''),
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
        if (towers.length > 1)
          DropdownButtonFormField<int>(
            key: ValueKey(_selectedNearbyTowerIndex),
            initialValue: _selectedNearbyTowerIndex,
            decoration: const InputDecoration(
              labelText: 'Select Nearby Tower',
            ),
            items: List.generate(towers.length, (index) {
              final site = towers[index];
              final label =
                  '${site.siteName} (${site.indusSiteId}) - ${_formatDistanceKm(site.distanceMeters)}';
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
    final records = provider.towerDieselRecords;
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
    if (_moduleLocked) {
      return Scaffold(
        appBar: AppBar(title: const Text('Tower Diesel Filling')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.lock_outline, size: 56, color: Color(0xFF0F766E)),
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
      appBar: AppBar(title: const Text('Tower Diesel Filling')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            return Form(
              key: _formKey,
              child: ListView(
                children: [
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
                  const SizedBox(height: 12),
                  _buildNearbyTowerSection(provider),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _siteIdController,
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(7),
                    ],
                    decoration:
                        const InputDecoration(
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
                      onPressed: provider.loading ? null : _pickDate,
                      child: const Text('Change'),
                    ),
                  ),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: const Color(0xFFEAF4F2),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Padding(
                      padding: EdgeInsets.all(10),
                      child: Text(
                        'KM is auto-fetched from Start Day and Day End. '
                        'If additional closed trip exists for same attendance/service, that trip end KM is used.',
                      ),
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
