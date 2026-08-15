import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/driver_info.dart';
import '../../../domain/entities/tower_site_suggestion.dart';
import '../../../domain/entities/vehicle.dart';
import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';

class ManualTowerDieselEntryScreen extends StatefulWidget {
  const ManualTowerDieselEntryScreen({super.key});

  @override
  State<ManualTowerDieselEntryScreen> createState() =>
      _ManualTowerDieselEntryScreenState();
}

class _ManualTowerDieselEntryScreenState
    extends State<ManualTowerDieselEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _siteIdController = TextEditingController();
  final _siteNameController = TextEditingController();
  final _fuelFilledController = TextEditingController();
  final _piuController = TextEditingController();
  final _dgHmrController = TextEditingController();
  final _openingStockController = TextEditingController();
  final _startKmController = TextEditingController();
  final _endKmController = TextEditingController();
  final _purposeController = TextEditingController(text: 'Diesel Filling');
  final _latitudeController = TextEditingController();
  final _longitudeController = TextEditingController();
  final _picker = ImagePicker();

  int? _vehicleId;
  int? _driverId;
  DateTime _fillDate = DateTime.now();
  bool _skipReadings = false;
  bool _confirmSiteNameUpdate = false;
  bool _loadingContext = true;
  bool _lookingUpSite = false;
  TowerSiteSuggestion? _matchedSite;
  File? _logbookPhoto;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadContext());
  }

  @override
  void dispose() {
    _siteIdController.dispose();
    _siteNameController.dispose();
    _fuelFilledController.dispose();
    _piuController.dispose();
    _dgHmrController.dispose();
    _openingStockController.dispose();
    _startKmController.dispose();
    _endKmController.dispose();
    _purposeController.dispose();
    _latitudeController.dispose();
    _longitudeController.dispose();
    super.dispose();
  }

  Future<void> _loadContext() async {
    await context.read<TransporterProvider>().loadDashboardData(
          force: true,
          prefetchHeavyData: false,
        );
    if (!mounted) {
      return;
    }
    setState(() {
      _loadingContext = false;
    });
  }

  void _applyVehicle(Vehicle vehicle) {
    _vehicleId = vehicle.id;
    final latestKm = vehicle.latestOdometerKm;
    if (latestKm != null) {
      _startKmController.text = latestKm.toString();
      if (_endKmController.text.trim().isEmpty) {
        _endKmController.text = latestKm.toString();
      }
    }
  }

  Vehicle? _vehicleById(List<Vehicle> vehicles, int? id) {
    if (id == null) {
      return null;
    }
    for (final vehicle in vehicles) {
      if (vehicle.id == id) {
        return vehicle;
      }
    }
    return null;
  }

  DriverInfo? _driverById(List<DriverInfo> drivers, int? id) {
    if (id == null) {
      return null;
    }
    for (final driver in drivers) {
      if (driver.id == id) {
        return driver;
      }
    }
    return null;
  }

  void _selectDriver(DriverInfo driver, List<Vehicle> vehicles) {
    _driverId = driver.id;
    if (driver.vehicleId != null) {
      final assigned = _vehicleById(vehicles, driver.vehicleId);
      if (assigned != null) {
        _applyVehicle(assigned);
      }
    }
  }

  Future<void> _lookupSite() async {
    final siteId = _siteIdController.text.trim();
    if (siteId.isEmpty) {
      _showMessage('Enter Indus Site ID first.');
      return;
    }
    setState(() {
      _lookingUpSite = true;
    });
    try {
      final site =
          await context.read<TransporterProvider>().lookupTowerSiteById(siteId);
      if (!mounted) {
        return;
      }
      if (site == null) {
        setState(() {
          _matchedSite = null;
        });
        _showMessage('New site. Enter site name manually.');
        return;
      }
      setState(() {
        _matchedSite = site;
        _siteNameController.text = site.siteName;
        if (site.latitude != 0) {
          _latitudeController.text = site.latitude.toStringAsFixed(6);
        }
        if (site.longitude != 0) {
          _longitudeController.text = site.longitude.toStringAsFixed(6);
        }
      });
      _showMessage('Site details filled.');
    } catch (_) {
      if (mounted) {
        _showMessage('Unable to lookup site.');
      }
    } finally {
      if (mounted) {
        setState(() {
          _lookingUpSite = false;
        });
      }
    }
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _fillDate,
      firstDate: DateTime(DateTime.now().year - 2, 1, 1),
      lastDate: DateTime(DateTime.now().year + 1, 12, 31),
    );
    if (picked == null) {
      return;
    }
    setState(() {
      _fillDate = DateTime(picked.year, picked.month, picked.day);
    });
  }

  Future<void> _pickLogbookPhoto() async {
    final image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 80,
      maxWidth: 1600,
      maxHeight: 1600,
    );
    if (image == null) {
      return;
    }
    setState(() {
      _logbookPhoto = File(image.path);
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    if (_vehicleId == null || _driverId == null) {
      _showMessage('Select vehicle and driver.');
      return;
    }

    final provider = context.read<TransporterProvider>();
    final ok = await provider.addManualTowerDieselRecord(
      vehicleId: _vehicleId!,
      driverId: _driverId!,
      indusSiteId: _siteIdController.text.trim(),
      siteName: _siteNameController.text.trim(),
      fuelFilled: double.parse(_fuelFilledController.text.trim()),
      piuReading: _skipReadings ? null : _parseDouble(_piuController.text),
      dgHmr: _skipReadings ? null : _parseDouble(_dgHmrController.text),
      openingStock:
          _skipReadings ? null : _parseDouble(_openingStockController.text),
      skipReadings: _skipReadings,
      confirmSiteNameUpdate: _confirmSiteNameUpdate,
      startKm: _parseInt(_startKmController.text),
      endKm: _parseInt(_endKmController.text),
      towerLatitude: _parseDouble(_latitudeController.text),
      towerLongitude: _parseDouble(_longitudeController.text),
      purpose: _purposeController.text.trim().isEmpty
          ? 'Diesel Filling'
          : _purposeController.text.trim(),
      fillDate: _fillDate,
      logbookPhoto: _logbookPhoto,
    );

    if (!mounted) {
      return;
    }
    _showMessage(ok ? 'Manual diesel entry saved.' : provider.error ?? 'Failed.');
    if (ok) {
      Navigator.of(context).pop(true);
    }
  }

  double? _parseDouble(String raw) {
    final value = raw.trim();
    if (value.isEmpty) {
      return null;
    }
    return double.tryParse(value);
  }

  int? _parseInt(String raw) {
    final value = raw.trim();
    if (value.isEmpty) {
      return null;
    }
    return int.tryParse(value);
  }

  String? _requiredNumber(String? value) {
    final raw = value?.trim() ?? '';
    if (raw.isEmpty) {
      return 'Required';
    }
    if (double.tryParse(raw) == null) {
      return 'Invalid number';
    }
    return null;
  }

  String? _optionalNumber(String? value) {
    final raw = value?.trim() ?? '';
    if (raw.isEmpty) {
      return null;
    }
    if (double.tryParse(raw) == null) {
      return 'Invalid number';
    }
    return null;
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final readingsEnabled = context.select(
      (AuthProvider auth) =>
          auth.transporterProfile?.dieselReadingsEnabled ??
          auth.session?.dieselReadingsEnabled ??
          false,
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Manual Diesel Entry')),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (_loadingContext) {
            return const Center(child: CircularProgressIndicator());
          }
          return Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                DropdownButtonFormField<int>(
                  // ignore: deprecated_member_use
                  value: _driverId,
                  decoration: const InputDecoration(labelText: 'Driver'),
                  items: provider.drivers
                      .map(
                        (driver) => DropdownMenuItem(
                          value: driver.id,
                          child: Text(driver.username),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    final driver = _driverById(provider.drivers, value);
                    if (driver == null) {
                      return;
                    }
                    setState(() => _selectDriver(driver, provider.vehicles));
                  },
                  validator: (value) => value == null ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  // ignore: deprecated_member_use
                  value: _vehicleId,
                  decoration: const InputDecoration(labelText: 'Vehicle'),
                  items: provider.vehicles
                      .map(
                        (vehicle) => DropdownMenuItem(
                          value: vehicle.id,
                          child: Text(vehicle.vehicleNumber),
                        ),
                      )
                      .toList(),
                  onChanged: (value) {
                    final vehicle = _vehicleById(provider.vehicles, value);
                    if (vehicle == null) {
                      return;
                    }
                    setState(() => _applyVehicle(vehicle));
                  },
                  validator: (value) => value == null ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _siteIdController,
                  decoration: InputDecoration(
                    labelText: 'Indus Site ID',
                    suffixIcon: IconButton(
                      onPressed: _lookingUpSite ? null : _lookupSite,
                      icon: _lookingUpSite
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.auto_fix_high_outlined),
                      tooltip: 'Autofill site',
                    ),
                  ),
                  validator: (value) =>
                      (value?.trim().isEmpty ?? true) ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _siteNameController,
                  decoration: const InputDecoration(labelText: 'Site Name'),
                  validator: (value) =>
                      (value?.trim().isEmpty ?? true) ? 'Required' : null,
                ),
                if (_matchedSite != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    'Autofilled from saved site. Last fill: ${_matchedSite!.lastFillDate?.toString().split(' ').first ?? '-'}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 12),
                TextFormField(
                  controller: _fuelFilledController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration:
                      const InputDecoration(labelText: 'Filled Quantity'),
                  validator: _requiredNumber,
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Fill Date'),
                  subtitle: Text(_fillDate.toIso8601String().split('T').first),
                  trailing: const Icon(Icons.calendar_month_outlined),
                  onTap: _pickDate,
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _startKmController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Start KM'),
                        validator: _optionalNumber,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextFormField(
                        controller: _endKmController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'End KM'),
                        validator: _optionalNumber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _skipReadings,
                  onChanged: (value) => setState(() => _skipReadings = value),
                  title: const Text('Save without readings'),
                  subtitle: Text(readingsEnabled
                      ? 'Use only when PIU / DG HMR / opening stock is not available.'
                      : 'Readings are optional for this transporter.'),
                ),
                if (!_skipReadings) ...[
                  TextFormField(
                    controller: _piuController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'PIU Reading'),
                    validator: readingsEnabled ? _requiredNumber : _optionalNumber,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _dgHmrController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'DG HMR'),
                    validator: readingsEnabled ? _requiredNumber : _optionalNumber,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _openingStockController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Opening Stock'),
                    validator: readingsEnabled ? _requiredNumber : _optionalNumber,
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _latitudeController,
                        keyboardType:
                            const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'Latitude'),
                        validator: _optionalNumber,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextFormField(
                        controller: _longitudeController,
                        keyboardType:
                            const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'Longitude'),
                        validator: _optionalNumber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _purposeController,
                  decoration: const InputDecoration(labelText: 'Purpose'),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _confirmSiteNameUpdate,
                  onChanged: (value) => setState(
                    () => _confirmSiteNameUpdate = value ?? false,
                  ),
                  title: const Text('Confirm site name update if changed'),
                ),
                OutlinedButton.icon(
                  onPressed: _pickLogbookPhoto,
                  icon: const Icon(Icons.photo_camera_outlined),
                  label: Text(_logbookPhoto == null
                      ? 'Add Logbook Photo (Optional)'
                      : 'Logbook Photo Selected'),
                ),
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: provider.loading ? null : _submit,
                  icon: provider.loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: const Text('Save Manual Diesel Entry'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
