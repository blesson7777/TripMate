import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

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

  final _picker = ImagePicker();
  File? _meterImage;
  File? _billImage;

  @override
  void dispose() {
    _litersController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _pickMeterImage() async {
    final image = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }
    setState(() {
      _meterImage = File(image.path);
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
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _pickMeterImage,
                    icon: const Icon(Icons.speed),
                    label: Text(_meterImage == null ? 'Capture Meter Image' : 'Retake Meter Image'),
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
