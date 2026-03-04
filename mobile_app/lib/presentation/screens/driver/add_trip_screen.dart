import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/driver_provider.dart';

class AddTripScreen extends StatefulWidget {
  const AddTripScreen({super.key});

  @override
  State<AddTripScreen> createState() => _AddTripScreenState();
}

class _AddTripScreenState extends State<AddTripScreen> {
  final _formKey = GlobalKey<FormState>();
  final _startLocationController = TextEditingController();
  final _destinationController = TextEditingController();
  final _startKmController = TextEditingController();
  final _endKmController = TextEditingController();
  final _purposeController = TextEditingController();

  @override
  void dispose() {
    _startLocationController.dispose();
    _destinationController.dispose();
    _startKmController.dispose();
    _endKmController.dispose();
    _purposeController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.addTrip(
      startLocation: _startLocationController.text.trim(),
      destination: _destinationController.text.trim(),
      startKm: int.parse(_startKmController.text.trim()),
      endKm: int.parse(_endKmController.text.trim()),
      purpose: _purposeController.text.trim(),
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(success ? 'Trip saved' : provider.error ?? 'Failed')),
    );

    if (success) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Add Trip')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  TextFormField(
                    controller: _startLocationController,
                    decoration: const InputDecoration(labelText: 'Start Location'),
                    validator: (value) =>
                        value == null || value.trim().isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _destinationController,
                    decoration: const InputDecoration(labelText: 'Destination'),
                    validator: (value) =>
                        value == null || value.trim().isEmpty ? 'Required' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _startKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Start KM'),
                    validator: (value) => int.tryParse(value ?? '') == null ? 'Invalid' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _endKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'End KM'),
                    validator: (value) => int.tryParse(value ?? '') == null ? 'Invalid' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _purposeController,
                    decoration: const InputDecoration(labelText: 'Purpose'),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
                        ? const CircularProgressIndicator()
                        : const Text('Save Trip'),
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
