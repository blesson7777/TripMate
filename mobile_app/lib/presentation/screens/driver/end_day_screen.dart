import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/ocr_service.dart';
import '../../../domain/entities/trip.dart';
import '../../providers/driver_provider.dart';
import 'add_trip_screen.dart';

class EndDayScreen extends StatefulWidget {
  const EndDayScreen({super.key});

  @override
  State<EndDayScreen> createState() => _EndDayScreenState();
}

class _EndDayScreenState extends State<EndDayScreen> {
  final _formKey = GlobalKey<FormState>();
  final _endKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  final _locationService = LocationService();
  File? _odoImage;
  LocationResult? _location;
  bool _fetchingLocation = false;
  bool _analyzingOdometer = false;
  String? _scanMessage;
  double? _scanConfidence;
  List<int> _scanCandidates = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DriverProvider>().loadTrips();
    });
  }

  @override
  void dispose() {
    _endKmController.dispose();
    _ocrService.dispose();
    super.dispose();
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

  Future<void> _captureOdometer([int? minimumValue]) async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
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

    final result = await _ocrService.analyzeOdometer(
      file,
      minimumValue: minimumValue,
    );

    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingOdometer = false;
      if (result.value != null) {
        if (minimumValue != null && result.value! < minimumValue) {
          _scanMessage =
              'Detected KM ${result.value} is below the opening KM '
              '($minimumValue). Enter the correct closing reading manually.';
        } else {
          _endKmController.text = result.value.toString();
          _scanMessage = 'Auto-detected closing KM: ${result.value}';
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

  Future<void> _submit() async {
    final provider = context.read<DriverProvider>();
    final activeDayTrip = _activeDayTrip(provider.trips);
    final pendingTrips = _pendingTrips(provider.trips).where((trip) {
      if (activeDayTrip == null) {
        return false;
      }
      return trip.attendanceId == activeDayTrip.attendanceId;
    }).toList();
    if (pendingTrips.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Legacy open child trips must be closed before End Day.'),
        ),
      );
      return;
    }
    if (activeDayTrip == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No active day found to close.'),
        ),
      );
      return;
    }

    if (!_formKey.currentState!.validate()) {
      return;
    }

    if (_odoImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture closing odometer photo first.')),
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

    final success = await provider.endDay(
      endKm: int.parse(_endKmController.text.trim()),
      odoEndImage: _odoImage!,
      latitude: _location!.latitude,
      longitude: _location!.longitude,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Day ended successfully' : provider.error ?? 'Failed')),
    );

    if (success) {
      Navigator.pop(context);
    }
  }

  List<Trip> _pendingTrips(List<Trip> trips) {
    return trips
        .where((trip) => trip.tripStatus == 'OPEN' && !trip.isDayTrip)
        .toList();
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('End Day')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            final activeDayTrip = _activeDayTrip(provider.trips);
            final pendingTrips = _pendingTrips(provider.trips).where((trip) {
              if (activeDayTrip == null) {
                return false;
              }
              return trip.attendanceId == activeDayTrip.attendanceId;
            }).toList();
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  if (activeDayTrip == null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Text(
                        'No active day found. Start Day first, then return to End Day.',
                      ),
                    ),
                    const SizedBox(height: 12),
                  ] else ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.teal.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: Colors.teal.withValues(alpha: 0.35),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Active Day Details',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 8),
                          Text('Service: ${activeDayTrip.attendanceServiceName ?? '-'}'),
                          Text('Vehicle: ${activeDayTrip.vehicleNumber ?? '-'}'),
                          Text('Opening KM: ${activeDayTrip.startKm}'),
                          if (activeDayTrip.destination.trim().isNotEmpty)
                            Text('Destination: ${activeDayTrip.destination}'),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  if (pendingTrips.isNotEmpty) ...[
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
                            'Legacy Pending Trips to Close',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                  color: Colors.orange.shade900,
                                ),
                          ),
                          const SizedBox(height: 8),
                          ...pendingTrips.map(
                            (trip) => Padding(
                              padding: const EdgeInsets.only(bottom: 6),
                              child: Text(
                                '#${trip.id}  ${trip.startLocation} -> ${trip.destination}  (Start KM ${trip.startKm})',
                              ),
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextButton.icon(
                            onPressed: () async {
                              final driverProvider = context.read<DriverProvider>();
                              await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => const AddTripScreen(),
                                ),
                              );
                              if (!mounted) {
                                return;
                              }
                              await driverProvider.loadTrips();
                            },
                            icon: const Icon(Icons.link_outlined),
                            label: const Text('Open legacy close screen'),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextFormField(
                    controller: _endKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'End KM'),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'End KM is required';
                      }
                      final parsed = int.tryParse(value.trim());
                      if (parsed == null) {
                        return 'Enter a valid number';
                      }
                      if (activeDayTrip != null && parsed < activeDayTrip.startKm) {
                        return 'Cannot be less than opening KM (${activeDayTrip.startKm})';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: provider.loading
                        ? null
                        : () => _captureOdometer(activeDayTrip?.startKm),
                    icon: const Icon(Icons.camera_alt),
                    label: Text(
                      _odoImage == null ? 'Capture End Odometer' : 'Retake End Odometer',
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
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: (provider.loading ||
                            _fetchingLocation ||
                            pendingTrips.isNotEmpty ||
                            activeDayTrip == null)
                        ? null
                        : _submit,
                    child: (provider.loading || _fetchingLocation)
                        ? const CircularProgressIndicator()
                        : const Text('End Day'),
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
