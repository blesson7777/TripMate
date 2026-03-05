import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/ocr_service.dart';
import '../../providers/driver_provider.dart';

class FuelEntryScreen extends StatefulWidget {
  const FuelEntryScreen({super.key});

  @override
  State<FuelEntryScreen> createState() => _FuelEntryScreenState();
}

class _FuelEntryScreenState extends State<FuelEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _litersController = TextEditingController();
  final _amountController = TextEditingController();
  final _odometerKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();
  File? _meterImage;
  File? _billImage;
  bool _analyzingMeter = false;
  String? _meterScanMessage;
  double? _meterScanConfidence;
  List<int> _meterCandidates = const [];

  @override
  void dispose() {
    _litersController.dispose();
    _amountController.dispose();
    _odometerKmController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Future<void> _pickMeterImage() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }
    final file = File(image.path);
    setState(() {
      _meterImage = file;
      _analyzingMeter = true;
      _meterScanMessage = null;
      _meterScanConfidence = null;
      _meterCandidates = const [];
    });

    final result = await _ocrService.analyzeOdometer(file);
    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingMeter = false;
      if (result.value != null) {
        _odometerKmController.text = result.value.toString();
        _meterScanMessage = 'Auto-detected odometer KM: ${result.value}';
        _meterScanConfidence = result.confidence;
        _meterCandidates = result.candidates.take(3).toList();
      } else {
        _meterScanMessage = 'Auto-detection failed. Enter odometer KM manually.';
        _meterScanConfidence = null;
        _meterCandidates = const [];
      }
    });
  }

  Future<void> _pickBillImage() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }
    setState(() {
      _billImage = File(image.path);
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    if (_meterImage == null || _billImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture both meter and bill images.')),
      );
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.addFuelRecord(
      liters: double.parse(_litersController.text.trim()),
      amount: double.parse(_amountController.text.trim()),
      odometerKm: int.parse(_odometerKmController.text.trim()),
      meterImage: _meterImage!,
      billImage: _billImage!,
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Fuel entry saved' : provider.error ?? 'Failed')),
    );

    if (success) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fuel Entry')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  TextFormField(
                    controller: _litersController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Liters'),
                    validator: (value) => double.tryParse(value ?? '') == null ? 'Invalid' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _amountController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Amount'),
                    validator: (value) => double.tryParse(value ?? '') == null ? 'Invalid' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _odometerKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Odometer KM'),
                    validator: (value) => int.tryParse(value ?? '') == null ? 'Invalid' : null,
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _pickMeterImage,
                    icon: const Icon(Icons.speed),
                    label: Text(_meterImage == null ? 'Capture Meter Image' : 'Retake Meter Image'),
                  ),
                  if (_analyzingMeter)
                    const Padding(
                      padding: EdgeInsets.only(top: 10),
                      child: LinearProgressIndicator(),
                    ),
                  if (_meterImage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.file(
                          _meterImage!,
                          height: 140,
                          width: double.infinity,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  if (_meterScanMessage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.04),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(10),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_meterScanMessage!),
                              if (_meterScanConfidence != null)
                                Text(
                                  'Confidence: ${(_meterScanConfidence! * 100).toStringAsFixed(0)}%',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              if (_meterCandidates.isNotEmpty)
                                Text(
                                  'Other readings: ${_meterCandidates.join(', ')}',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _pickBillImage,
                    icon: const Icon(Icons.receipt_long),
                    label: Text(_billImage == null ? 'Capture Bill Image' : 'Retake Bill Image'),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
                        ? const CircularProgressIndicator()
                        : const Text('Save Fuel Entry'),
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
