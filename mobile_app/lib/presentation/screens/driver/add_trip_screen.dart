import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/ocr_service.dart';
import '../../../domain/entities/trip.dart';
import '../../providers/driver_provider.dart';

class AddTripScreen extends StatefulWidget {
  const AddTripScreen({super.key});

  @override
  State<AddTripScreen> createState() => _AddTripScreenState();
}

class _AddTripScreenState extends State<AddTripScreen> {
  final _startFormKey = GlobalKey<FormState>();
  final _closeFormKey = GlobalKey<FormState>();

  final _startLocationController = TextEditingController();
  final _destinationController = TextEditingController();
  final _startKmController = TextEditingController();
  final _purposeController = TextEditingController();
  final _endKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();

  File? _startOdoImage;
  File? _endOdoImage;
  bool _analyzingStart = false;
  bool _analyzingEnd = false;
  String? _startScanMessage;
  String? _endScanMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DriverProvider>().loadTrips();
    });
  }

  @override
  void dispose() {
    _startLocationController.dispose();
    _destinationController.dispose();
    _startKmController.dispose();
    _purposeController.dispose();
    _endKmController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Trip? _activeTrip(List<Trip> trips) {
    for (final trip in trips) {
      if (trip.tripStatus == 'OPEN' && !trip.isDayTrip) {
        return trip;
      }
    }
    return null;
  }

  Future<void> _captureStartOdo() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }

    final file = File(image.path);
    setState(() {
      _startOdoImage = file;
      _analyzingStart = true;
      _startScanMessage = null;
    });

    final result = await _ocrService.analyzeOdometer(file);
    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingStart = false;
      if (result.value != null) {
        _startKmController.text = result.value.toString();
        _startScanMessage = 'Auto-detected start KM: ${result.value}';
      } else {
        _startScanMessage = 'Auto-detection failed. Enter start KM manually.';
      }
    });
  }

  Future<void> _captureEndOdo() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }

    final file = File(image.path);
    setState(() {
      _endOdoImage = file;
      _analyzingEnd = true;
      _endScanMessage = null;
    });

    final result = await _ocrService.analyzeOdometer(file);
    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingEnd = false;
      if (result.value != null) {
        _endKmController.text = result.value.toString();
        _endScanMessage = 'Auto-detected end KM: ${result.value}';
      } else {
        _endScanMessage = 'Auto-detection failed. Enter end KM manually.';
      }
    });
  }

  Future<void> _submitStartTrip() async {
    if (!_startFormKey.currentState!.validate()) {
      return;
    }
    if (_startOdoImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture start odometer photo first.')),
      );
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.startTrip(
      startLocation: _startLocationController.text.trim(),
      destination: _destinationController.text.trim(),
      startKm: int.parse(_startKmController.text.trim()),
      purpose: _purposeController.text.trim(),
      startOdoImage: _startOdoImage!,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Trip started' : provider.error ?? 'Failed')),
    );

    if (success) {
      _startLocationController.clear();
      _destinationController.clear();
      _startKmController.clear();
      _purposeController.clear();
      setState(() {
        _startOdoImage = null;
        _startScanMessage = null;
      });
      await provider.loadTrips();
    }
  }

  Future<void> _submitCloseTrip(Trip trip) async {
    if (!_closeFormKey.currentState!.validate()) {
      return;
    }
    if (_endOdoImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture end odometer photo first.')),
      );
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.closeTrip(
      tripId: trip.id,
      endKm: int.parse(_endKmController.text.trim()),
      endOdoImage: _endOdoImage!,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Trip closed' : provider.error ?? 'Failed')),
    );

    if (success) {
      _endKmController.clear();
      setState(() {
        _endOdoImage = null;
        _endScanMessage = null;
      });
      await provider.loadTrips();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Trip Workflow')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            final activeTrip = _activeTrip(provider.trips);
            return ListView(
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Form(
                      key: _startFormKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Start Trip',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 10),
                          if (activeTrip != null)
                            Text(
                              'Close current open trip before starting another.',
                              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: Colors.red.shade700,
                                  ),
                            ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _startLocationController,
                            decoration: const InputDecoration(labelText: 'Start Location'),
                            validator: (value) =>
                                value == null || value.trim().isEmpty ? 'Required' : null,
                          ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _destinationController,
                            decoration: const InputDecoration(labelText: 'Destination'),
                            validator: (value) =>
                                value == null || value.trim().isEmpty ? 'Required' : null,
                          ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _startKmController,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(labelText: 'Start KM'),
                            validator: (value) =>
                                int.tryParse(value ?? '') == null ? 'Invalid' : null,
                          ),
                          const SizedBox(height: 10),
                          TextFormField(
                            controller: _purposeController,
                            decoration: const InputDecoration(labelText: 'Purpose'),
                          ),
                          const SizedBox(height: 10),
                          FilledButton.icon(
                            onPressed: provider.loading ? null : _captureStartOdo,
                            icon: const Icon(Icons.camera_alt),
                            label: Text(
                              _startOdoImage == null
                                  ? 'Capture Start Odometer'
                                  : 'Retake Start Odometer',
                            ),
                          ),
                          if (_analyzingStart)
                            const Padding(
                              padding: EdgeInsets.only(top: 8),
                              child: LinearProgressIndicator(),
                            ),
                          if (_startScanMessage != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(_startScanMessage!),
                            ),
                          const SizedBox(height: 10),
                          FilledButton(
                            onPressed: (provider.loading || activeTrip != null)
                                ? null
                                : _submitStartTrip,
                            child: provider.loading
                                ? const CircularProgressIndicator()
                                : const Text('Start Trip'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Form(
                      key: _closeFormKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Close Active Trip',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 10),
                          if (activeTrip == null)
                            const Text('No active trip found.')
                          else ...[
                            Text('Route: ${activeTrip.startLocation} -> ${activeTrip.destination}'),
                            Text('Start KM: ${activeTrip.startKm}'),
                            const SizedBox(height: 10),
                            TextFormField(
                              controller: _endKmController,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(labelText: 'End KM'),
                              validator: (value) =>
                                  int.tryParse(value ?? '') == null ? 'Invalid' : null,
                            ),
                            const SizedBox(height: 10),
                            FilledButton.icon(
                              onPressed: provider.loading ? null : _captureEndOdo,
                              icon: const Icon(Icons.camera_alt),
                              label: Text(
                                _endOdoImage == null
                                    ? 'Capture End Odometer'
                                    : 'Retake End Odometer',
                              ),
                            ),
                            if (_analyzingEnd)
                              const Padding(
                                padding: EdgeInsets.only(top: 8),
                                child: LinearProgressIndicator(),
                              ),
                            if (_endScanMessage != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(_endScanMessage!),
                              ),
                            const SizedBox(height: 10),
                            FilledButton(
                              onPressed: provider.loading
                                  ? null
                                  : () => _submitCloseTrip(activeTrip),
                              child: provider.loading
                                  ? const CircularProgressIndicator()
                                  : const Text('Close Trip'),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
