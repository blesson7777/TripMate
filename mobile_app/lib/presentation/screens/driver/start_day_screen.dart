import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/ocr_service.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';

class StartDayScreen extends StatefulWidget {
  const StartDayScreen({super.key});

  @override
  State<StartDayScreen> createState() => _StartDayScreenState();
}

class _StartDayScreenState extends State<StartDayScreen> {
  final _formKey = GlobalKey<FormState>();
  final _startKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  final _locationService = LocationService();

  int? _selectedVehicleId;
  File? _odoImage;
  LocationResult? _location;
  bool _fetchingLocation = false;
  bool _loadingVehicles = true;
  bool _analyzingOdometer = false;
  String? _scanMessage;
  double? _scanConfidence;
  List<int> _scanCandidates = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initializeVehicles());
  }

  @override
  void dispose() {
    _startKmController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Future<void> _initializeVehicles() async {
    setState(() {
      _loadingVehicles = true;
    });

    final authProvider = context.read<AuthProvider>();
    await authProvider.loadDriverProfile();
    await context.read<DriverProvider>().loadVehicles();

    if (!mounted) {
      return;
    }

    final vehicles = context.read<DriverProvider>().vehicles;
    final assignedVehicleId = authProvider.driverProfile?.assignedVehicleId;

    int? selectedVehicleId;
    if (assignedVehicleId != null &&
        vehicles.any((vehicle) => vehicle.id == assignedVehicleId)) {
      selectedVehicleId = assignedVehicleId;
    } else if (vehicles.isNotEmpty) {
      selectedVehicleId = vehicles.first.id;
    }

    setState(() {
      _selectedVehicleId = selectedVehicleId;
      _loadingVehicles = false;
    });
  }

  Future<void> _captureOdometer() async {
    final image =
        await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }

    final file = File(image.path);
    setState(() {
      _odoImage = file;
      _analyzingOdometer = true;
      _scanMessage = null;
      _scanConfidence = null;
      _scanCandidates = const [];
    });

    final result = await _ocrService.analyzeOdometer(file);

    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingOdometer = false;
      if (result.value != null) {
        _startKmController.text = result.value.toString();
        _scanMessage = 'Auto-detected opening KM: ${result.value}';
        _scanConfidence = result.confidence;
        _scanCandidates = result.candidates.take(3).toList();
      } else {
        _scanMessage = 'Auto-detection failed. Enter KM manually and retake if needed.';
        _scanConfidence = null;
        _scanCandidates = const [];
      }
    });
  }

  Future<void> _fetchLocation() async {
    setState(() {
      _fetchingLocation = true;
    });

    try {
      final location = await _locationService.getCurrentLocation();
      if (!mounted) {
        return;
      }
      setState(() {
        _location = location;
        _fetchingLocation = false;
      });
    } catch (exception) {
      if (!mounted) {
        return;
      }
      setState(() {
        _fetchingLocation = false;
      });
      final message = exception.toString().replaceFirst('Exception: ', '');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    if (_odoImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture odometer image first.')),
      );
      return;
    }

    await _fetchLocation();
    if (!mounted) {
      return;
    }
    if (_location == null) {
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.startDay(
      vehicleId: _selectedVehicleId,
      startKm: int.parse(_startKmController.text.trim()),
      odoStartImage: _odoImage!,
      latitude: _location!.latitude,
      longitude: _location!.longitude,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(success
              ? 'Day started successfully'
              : provider.error ?? 'Failed')),
    );

    if (success) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Start Day')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            final vehicles = provider.vehicles;
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  Text(
                    'Allocated vehicle is selected by default. You can switch to another vehicle when required.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.black.withValues(alpha: 0.66),
                        ),
                  ),
                  const SizedBox(height: 8),
                  if (_loadingVehicles)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: LinearProgressIndicator(),
                    )
                  else
                    DropdownButtonFormField<int>(
                      initialValue: _selectedVehicleId,
                      decoration: const InputDecoration(
                        labelText: 'Select Vehicle',
                        prefixIcon: Icon(Icons.local_shipping_outlined),
                      ),
                      items: vehicles
                          .map(
                            (vehicle) => DropdownMenuItem<int>(
                              value: vehicle.id,
                              child: Text(
                                '${vehicle.vehicleNumber} (${vehicle.status})',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (value) {
                        setState(() {
                          _selectedVehicleId = value;
                        });
                      },
                      validator: (value) {
                        if (vehicles.isEmpty) {
                          return 'No vehicles available for your transporter';
                        }
                        if (value == null) {
                          return 'Please select a vehicle';
                        }
                        return null;
                      },
                    ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _startKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Start KM'),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Start KM is required';
                      }
                      if (int.tryParse(value.trim()) == null) {
                        return 'Enter a valid number';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _captureOdometer,
                    icon: const Icon(Icons.camera_alt),
                    label: Text(
                      _odoImage == null
                          ? 'Capture Odometer Photo'
                          : 'Retake Odometer Photo',
                    ),
                  ),
                  if (_analyzingOdometer)
                    const Padding(
                      padding: EdgeInsets.only(top: 12),
                      child: LinearProgressIndicator(),
                    ),
                  if (_odoImage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.file(
                          _odoImage!,
                          height: 170,
                          width: double.infinity,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  if (_scanMessage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.04),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_scanMessage!),
                              if (_scanConfidence != null)
                                Text(
                                  'Confidence: ${(_scanConfidence! * 100).toStringAsFixed(0)}%',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              if (_scanCandidates.isNotEmpty)
                                Text(
                                  'Other readings: ${_scanCandidates.join(', ')}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: (provider.loading || _fetchingLocation)
                        ? null
                        : _fetchLocation,
                    icon: _fetchingLocation
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.my_location),
                    label: Text(
                      _fetchingLocation
                          ? 'Fetching location...'
                          : _location == null
                              ? 'Get Current Location'
                              : 'Location: ${_location!.latitude.toStringAsFixed(5)}, ${_location!.longitude.toStringAsFixed(5)}',
                    ),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: (provider.loading || _fetchingLocation)
                        ? null
                        : _submit,
                    child: (provider.loading || _fetchingLocation)
                        ? const CircularProgressIndicator()
                        : const Text('Start Day'),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
