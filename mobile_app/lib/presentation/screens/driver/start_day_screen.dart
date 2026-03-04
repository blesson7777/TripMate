import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/location_service.dart';
import '../../../core/services/ocr_service.dart';
import '../../providers/driver_provider.dart';

class StartDayScreen extends StatefulWidget {
  const StartDayScreen({super.key});

  @override
  State<StartDayScreen> createState() => _StartDayScreenState();
}

class _StartDayScreenState extends State<StartDayScreen> {
  final _formKey = GlobalKey<FormState>();
  final _vehicleController = TextEditingController();
  final _startKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  final _locationService = LocationService();

  File? _odoImage;
  LocationResult? _location;

  @override
  void dispose() {
    _vehicleController.dispose();
    _startKmController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Future<void> _captureOdometer() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }

    final file = File(image.path);
    final ocrValue = await _ocrService.extractOdometerValue(file);

    if (!mounted) {
      return;
    }

    setState(() {
      _odoImage = file;
      if (ocrValue != null) {
        _startKmController.text = ocrValue.toString();
      }
    });
  }

  Future<void> _fetchLocation() async {
    try {
      final location = await _locationService.getCurrentLocation();
      if (!mounted) {
        return;
      }
      setState(() {
        _location = location;
      });
    } catch (exception) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(exception.toString())),
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

    if (_location == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Fetch location first.')),
      );
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.startDay(
      vehicleId: _vehicleController.text.trim().isEmpty
          ? null
          : int.tryParse(_vehicleController.text.trim()),
      startKm: int.parse(_startKmController.text.trim()),
      odoStartImage: _odoImage!,
      latitude: _location!.latitude,
      longitude: _location!.longitude,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Day started successfully' : provider.error ?? 'Failed')),
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
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  TextFormField(
                    controller: _vehicleController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle ID (optional)',
                    ),
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
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: provider.loading ? null : _fetchLocation,
                    icon: const Icon(Icons.my_location),
                    label: Text(
                      _location == null
                          ? 'Get Current Location'
                          : 'Location: ${_location!.latitude.toStringAsFixed(5)}, ${_location!.longitude.toStringAsFixed(5)}',
                    ),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
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
