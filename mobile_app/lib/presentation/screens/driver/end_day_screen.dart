import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/ocr_service.dart';
import '../../providers/driver_provider.dart';

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

  Future<void> _captureOdometer() async {
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

    final result = await _ocrService.analyzeOdometer(file);

    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingOdometer = false;
      if (result.value != null) {
        _endKmController.text = result.value.toString();
        _scanMessage = 'Auto-detected closing KM: ${result.value}';
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

    final provider = context.read<DriverProvider>();
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('End Day')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  TextFormField(
                    controller: _endKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'End KM'),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'End KM is required';
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
                    onPressed: (provider.loading || _fetchingLocation) ? null : _submit,
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
