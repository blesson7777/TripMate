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
  final _closeFormKey = GlobalKey<FormState>();

  final _endKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  final _scrollController = ScrollController();
  final _closeSectionKey = GlobalKey();

  File? _endOdoImage;
  bool _analyzingEnd = false;
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
    _endKmController.dispose();
    _scrollController.dispose();
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

  Future<void> _scrollToCloseSection() async {
    final context = _closeSectionKey.currentContext;
    if (context == null) {
      return;
    }
    await Scrollable.ensureVisible(
      context,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
      alignment: 0.1,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Legacy Trip Close')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            final activeTrip = _activeTrip(provider.trips);
            return ListView(
              controller: _scrollController,
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Child Trip Creation Retired',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                        const SizedBox(height: 10),
                        const Text(
                          'New trip starts must use Start Day, and closing must use End Day. '
                          'This screen remains only to close old legacy child trips if any are still open.',
                        ),
                        if (activeTrip != null) ...[
                          const SizedBox(height: 10),
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
                                  'Legacy active child trip found.',
                                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                        color: Colors.orange.shade900,
                                        fontWeight: FontWeight.w700,
                                      ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '${activeTrip.startLocation} -> ${activeTrip.destination}',
                                ),
                                Text('Start KM: ${activeTrip.startKm}'),
                                const SizedBox(height: 8),
                                TextButton.icon(
                                  onPressed: provider.loading ? null : _scrollToCloseSection,
                                  icon: const Icon(Icons.link_outlined),
                                  label: const Text('Go to Close Section'),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  key: _closeSectionKey,
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
