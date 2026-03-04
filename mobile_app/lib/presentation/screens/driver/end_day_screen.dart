import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

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
  File? _odoImage;

  @override
  void dispose() {
    _endKmController.dispose();
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
        _endKmController.text = ocrValue.toString();
      }
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final provider = context.read<DriverProvider>();
    final success = await provider.endDay(
      endKm: int.parse(_endKmController.text.trim()),
      odoEndImage: _odoImage,
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
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
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
