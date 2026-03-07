import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/ocr_service.dart';
import '../../../domain/entities/trip.dart';
import '../../../domain/entities/vehicle.dart';
import '../../providers/auth_provider.dart';
import '../../providers/driver_provider.dart';
import 'end_day_screen.dart';

class StartDayScreen extends StatefulWidget {
  const StartDayScreen({super.key});

  @override
  State<StartDayScreen> createState() => _StartDayScreenState();
}

class _StartDayScreenState extends State<StartDayScreen> {
  static const int _maxAutoFillOdometerDeltaKm = 50;
  static const int _maxOdometerSubmissionDeltaKm = 300;
  final _formKey = GlobalKey<FormState>();
  final _startKmController = TextEditingController();
  final _servicePurposeController = TextEditingController();
  final _destinationController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  final _locationService = LocationService();

  int? _selectedVehicleId;
  int? _selectedServiceId;
  File? _odoImage;
  LocationResult? _location;
  bool _fetchingLocation = false;
  bool _loadingVehicles = true;
  bool _loadingServices = true;
  bool _analyzingOdometer = false;
  String? _scanMessage;
  double? _scanConfidence;
  List<int> _scanCandidates = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initializeFormData());
  }

  @override
  void dispose() {
    _startKmController.dispose();
    _servicePurposeController.dispose();
    _destinationController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Future<void> _initializeFormData() async {
    setState(() {
      _loadingVehicles = true;
      _loadingServices = true;
    });

    final authProvider = context.read<AuthProvider>();
    final driverProvider = context.read<DriverProvider>();
    await authProvider.loadDriverProfile();
    await Future.wait([
      driverProvider.loadVehicles(),
      driverProvider.loadServices(),
      driverProvider.loadTrips(),
    ]);

    if (!mounted) {
      return;
    }

    final vehicles = driverProvider.vehicles;
    final services = driverProvider.services.where((item) => item.isActive).toList();
    final trips = driverProvider.trips;
    final profile = authProvider.driverProfile;
    final selectedVehicleId = _resolveDefaultVehicleId(
      assignedVehicleId: profile?.assignedVehicleId,
      vehicles: vehicles,
      trips: trips,
    );
    final selectedServiceId = _resolveDefaultServiceId(
      defaultServiceId: profile?.defaultServiceId,
      serviceIds: services.map((item) => item.id).toSet(),
      trips: trips,
    );

    setState(() {
      _selectedVehicleId = selectedVehicleId;
      _selectedServiceId =
          selectedServiceId ?? (services.isNotEmpty ? services.first.id : null);
      _loadingVehicles = false;
      _loadingServices = false;
    });
    _syncVehicleOdometer(vehicles, overwriteIfEmpty: true);
  }

  int? _resolveDefaultVehicleId({
    required int? assignedVehicleId,
    required List<Vehicle> vehicles,
    required List<Trip> trips,
  }) {
    if (assignedVehicleId != null &&
        vehicles.any((vehicle) => vehicle.id == assignedVehicleId)) {
      return assignedVehicleId;
    }

    for (final trip in trips) {
      final vehicleNumber = trip.vehicleNumber?.trim().toLowerCase();
      if (vehicleNumber == null || vehicleNumber.isEmpty) {
        continue;
      }
      for (final vehicle in vehicles) {
        if (vehicle.vehicleNumber.trim().toLowerCase() == vehicleNumber) {
          return vehicle.id;
        }
      }
    }

    if (vehicles.isNotEmpty) {
      return vehicles.first.id;
    }
    return null;
  }

  int? _resolveDefaultServiceId({
    required int? defaultServiceId,
    required Set<int> serviceIds,
    required List<Trip> trips,
  }) {
    if (defaultServiceId != null && serviceIds.contains(defaultServiceId)) {
      return defaultServiceId;
    }

    for (final trip in trips) {
      final serviceId = trip.attendanceServiceId;
      if (serviceId != null && serviceIds.contains(serviceId)) {
        return serviceId;
      }
    }

    return null;
  }

  Vehicle? _selectedVehicle(List<Vehicle> vehicles) {
    final selectedVehicleId = _selectedVehicleId;
    if (selectedVehicleId == null) {
      return null;
    }
    for (final vehicle in vehicles) {
      if (vehicle.id == selectedVehicleId) {
        return vehicle;
      }
    }
    return null;
  }

  void _syncVehicleOdometer(
    List<Vehicle> vehicles, {
    bool overwriteIfEmpty = false,
  }) {
    final vehicle = _selectedVehicle(vehicles);
    final latestKm = vehicle?.latestOdometerKm;
    if (latestKm == null) {
      return;
    }

    final existing = int.tryParse(_startKmController.text.trim());
    if (overwriteIfEmpty || existing == null || existing < latestKm) {
      _startKmController.text = latestKm.toString();
    }
  }

  Trip? _activeDayTrip(List<Trip> trips) {
    final dayTrips = trips
        .where((trip) => trip.isDayTrip && trip.tripStatus == 'OPEN')
        .toList()
      ..sort((a, b) {
        final aKey = a.tripStartedAt ?? a.createdAt;
        final bKey = b.tripStartedAt ?? b.createdAt;
        return bKey.compareTo(aKey);
    });
    return dayTrips.isEmpty ? null : dayTrips.first;
  }

  Future<void> _captureOdometer() async {
    final driverProvider = context.read<DriverProvider>();
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

    final latestKm = _selectedVehicle(driverProvider.vehicles)?.latestOdometerKm;
    final result = await _ocrService.analyzeOdometer(
      file,
      minimumValue: latestKm,
    );

    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingOdometer = false;
      if (result.value != null) {
        final detectedValue = result.value!;
        if (latestKm != null && detectedValue < latestKm) {
          _scanMessage =
              'Detected KM $detectedValue is below the latest recorded value '
              '($latestKm). Enter the correct reading manually.';
        } else if (latestKm != null &&
            (detectedValue - latestKm).abs() > _maxAutoFillOdometerDeltaKm) {
          _scanMessage =
              'Detected KM $detectedValue differs from the latest recorded value '
              '($latestKm) by more than $_maxAutoFillOdometerDeltaKm km. Enter it manually.';
        } else {
          _startKmController.text = detectedValue.toString();
          _scanMessage = 'Auto-detected opening KM: $detectedValue';
        }
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

  Future<bool> _confirmNearLatestOdometerSubmission({
    required int latestKm,
    required int startKm,
  }) async {
    final delta = startKm - latestKm;
    if (delta < 0 || delta <= _maxAutoFillOdometerDeltaKm) {
      return true;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Confirm Start KM'),
          content: Text(
            'The entered Start KM ($startKm) is $delta km above the latest '
            'recorded odometer ($latestKm). Do you want to continue?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Continue'),
            ),
          ],
        );
      },
    );

    return confirmed ?? false;
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
    final selectedVehicle = _selectedVehicle(provider.vehicles);
    final latestKm = selectedVehicle?.latestOdometerKm;
    final startKm = int.parse(_startKmController.text.trim());
    if (latestKm != null && startKm < latestKm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Start KM cannot be less than the latest recorded value ($latestKm).',
          ),
        ),
      );
      return;
    }
    if (latestKm != null &&
        startKm > latestKm + _maxOdometerSubmissionDeltaKm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Start KM cannot be greater than the latest recorded value '
            'by more than $_maxOdometerSubmissionDeltaKm km ($latestKm).',
          ),
        ),
      );
      return;
    }

    if (latestKm != null) {
      final confirmed = await _confirmNearLatestOdometerSubmission(
        latestKm: latestKm,
        startKm: startKm,
      );
      if (!mounted || !confirmed) {
        return;
      }
    }

    final success = await provider.startDay(
      vehicleId: _selectedVehicleId,
      serviceId: _selectedServiceId,
      servicePurpose: _servicePurposeController.text.trim(),
      destination: _destinationController.text.trim(),
      startKm: startKm,
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
            final services = provider.services.where((item) => item.isActive).toList();
            final activeDayTrip = _activeDayTrip(provider.trips);
            final selectedVehicle = _selectedVehicle(vehicles);
            final latestVehicleKm = selectedVehicle?.latestOdometerKm;

            if (activeDayTrip != null) {
              return ListView(
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: Colors.orange.withValues(alpha: 0.35),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Day already active',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: Colors.orange.shade900,
                              ),
                        ),
                        const SizedBox(height: 8),
                        Text('Service: ${activeDayTrip.attendanceServiceName ?? '-'}'),
                        Text('Vehicle: ${activeDayTrip.vehicleNumber ?? '-'}'),
                        Text('Start KM: ${activeDayTrip.startKm}'),
                        if ((activeDayTrip.destination).trim().isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text('Destination: ${activeDayTrip.destination}'),
                        ],
                        const SizedBox(height: 8),
                        FilledButton.icon(
                          onPressed: () async {
                            final driverProvider = context.read<DriverProvider>();
                            await Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => const EndDayScreen(),
                              ),
                            );
                            if (!mounted) {
                              return;
                            }
                            await driverProvider.loadTrips();
                          },
                          icon: const Icon(Icons.stop_circle_outlined),
                          label: const Text('Go to End Day'),
                        ),
                      ],
                    ),
                  ),
                ],
              );
            }
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  Text(
                    'Start Day opens the current run. Location will be fetched automatically when you submit.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.black.withValues(alpha: 0.66),
                        ),
                  ),
                  const SizedBox(height: 8),
                  if (_loadingServices)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: LinearProgressIndicator(),
                    )
                  else
                    DropdownButtonFormField<int>(
                      initialValue: _selectedServiceId,
                      decoration: const InputDecoration(
                        labelText: 'Select Service',
                        prefixIcon: Icon(Icons.miscellaneous_services_outlined),
                      ),
                      items: services
                          .map(
                            (service) => DropdownMenuItem<int>(
                              value: service.id,
                              child: Text(service.name),
                            ),
                          )
                          .toList(),
                      onChanged: (value) {
                        setState(() {
                          _selectedServiceId = value;
                        });
                      },
                      validator: (value) {
                        if (services.isEmpty) {
                          return 'No services configured by transporter';
                        }
                        if (value == null) {
                          return 'Please select a service';
                        }
                        return null;
                      },
                    ),
                  const SizedBox(height: 12),
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
                        _syncVehicleOdometer(vehicles);
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
                  if (selectedVehicle != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0A6B6F).withValues(alpha: 0.06),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: const Color(0xFF0A6B6F).withValues(alpha: 0.16),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Selected Vehicle',
                            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 4),
                          Text(selectedVehicle.vehicleNumber),
                          Text(
                            latestVehicleKm == null
                                ? 'Latest odometer: not available'
                                : 'Latest odometer: $latestVehicleKm km',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  if (selectedVehicle != null) const SizedBox(height: 12),
                  TextFormField(
                    controller: _servicePurposeController,
                    decoration: const InputDecoration(
                      labelText: 'Service Purpose (optional)',
                      prefixIcon: Icon(Icons.description_outlined),
                    ),
                    maxLength: 255,
                  ),
                  const SizedBox(height: 4),
                  TextFormField(
                    controller: _destinationController,
                    decoration: const InputDecoration(
                      labelText: 'Destination (optional)',
                      prefixIcon: Icon(Icons.place_outlined),
                    ),
                    maxLength: 255,
                  ),
                  const SizedBox(height: 4),
                  TextFormField(
                    controller: _startKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Start KM'),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Start KM is required';
                      }
                      final parsed = int.tryParse(value.trim());
                      if (parsed == null) {
                        return 'Enter a valid number';
                      }
                      if (latestVehicleKm != null && parsed < latestVehicleKm) {
                        return 'Cannot be less than latest recorded KM ($latestVehicleKm)';
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
                  if (_fetchingLocation)
                    const Padding(
                      padding: EdgeInsets.only(top: 12),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          SizedBox(width: 10),
                          Text('Fetching current location...'),
                        ],
                      ),
                    )
                  else if (_location != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(
                        'Location ready: ${_location!.latitude.toStringAsFixed(5)}, ${_location!.longitude.toStringAsFixed(5)}',
                        style: Theme.of(context).textTheme.bodySmall,
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
