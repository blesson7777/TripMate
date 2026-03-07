import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/services/ocr_service.dart';
import '../../../domain/entities/trip.dart';
import '../../providers/driver_provider.dart';

class FuelEntryScreen extends StatefulWidget {
  const FuelEntryScreen({super.key});

  @override
  State<FuelEntryScreen> createState() => _FuelEntryScreenState();
}

class _FuelEntryScreenState extends State<FuelEntryScreen> {
  static const int _maxAutoFillOdometerDeltaKm = 50;
  static const int _maxOdometerSubmissionDeltaKm = 300;
  final _formKey = GlobalKey<FormState>();
  final _litersController = TextEditingController();
  final _amountController = TextEditingController();
  final _odometerKmController = TextEditingController();

  final _picker = ImagePicker();
  final _ocrService = OcrService();

  int? _selectedVehicleId;
  File? _meterImage;
  File? _billImage;
  bool _analyzingMeter = false;
  String? _meterScanMessage;
  bool _loadingContext = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _initializeContext());
  }

  @override
  void dispose() {
    _litersController.dispose();
    _amountController.dispose();
    _odometerKmController.dispose();
    _ocrService.dispose();
    super.dispose();
  }

  Future<void> _initializeContext() async {
    final provider = context.read<DriverProvider>();
    await Future.wait([
      provider.loadTrips(force: true, silent: true),
      provider.loadVehicles(),
    ]);
    if (!mounted) {
      return;
    }
    setState(() {
      _loadingContext = false;
    });
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

  int? _expectedOdometerKm(DriverProvider provider, Trip? activeDayTrip) {
    if (activeDayTrip != null) {
      final activeVehicleName = activeDayTrip.vehicleNumber?.trim();
      if (activeVehicleName == null || activeVehicleName.isEmpty) {
        return null;
      }
      for (final vehicle in provider.vehicles) {
        if (vehicle.vehicleNumber.trim() == activeVehicleName) {
          return vehicle.latestOdometerKm;
        }
      }
      return null;
    }
    if (_selectedVehicleId == null) {
      return null;
    }
    for (final vehicle in provider.vehicles) {
      if (vehicle.id == _selectedVehicleId) {
        return vehicle.latestOdometerKm;
      }
    }
    return null;
  }

  Future<void> _pickMeterImage() async {
    final provider = context.read<DriverProvider>();
    final activeDayTrip = _activeDayTrip(provider.trips);
    final image =
        await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }
    final file = File(image.path);
    setState(() {
      _meterImage = file;
      _analyzingMeter = true;
      _meterScanMessage = null;
    });

    final expectedKm = _expectedOdometerKm(provider, activeDayTrip);
    final result = await _ocrService.analyzeOdometer(
      file,
      minimumValue: expectedKm,
    );
    if (!mounted) {
      return;
    }

    setState(() {
      _analyzingMeter = false;
      if (result.value != null) {
        final detectedValue = result.value!;
        if (expectedKm != null && detectedValue < expectedKm) {
          _meterScanMessage =
              'Detected odometer KM $detectedValue is below the latest recorded value '
              '($expectedKm). Enter it manually.';
        } else if (expectedKm != null &&
            (detectedValue - expectedKm).abs() > _maxAutoFillOdometerDeltaKm) {
          _meterScanMessage =
              'Detected odometer KM $detectedValue differs from the latest recorded value '
              '($expectedKm) by more than $_maxAutoFillOdometerDeltaKm km. Enter it manually.';
        } else {
          _odometerKmController.text = detectedValue.toString();
          _meterScanMessage = 'Auto-detected odometer KM: $detectedValue';
        }
      } else {
        _meterScanMessage =
            'Auto-detection failed. Enter odometer KM manually.';
      }
    });
  }

  Future<void> _pickBillImage() async {
    final image =
        await _picker.pickImage(source: ImageSource.camera, imageQuality: 85);
    if (image == null) {
      return;
    }
    setState(() {
      _billImage = File(image.path);
    });
  }

  Future<bool> _confirmFuelOdometerSubmission({
    required int latestKm,
    required int odometerKm,
  }) async {
    final delta = odometerKm - latestKm;
    if (delta <= _maxAutoFillOdometerDeltaKm) {
      return true;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Confirm Odometer KM'),
          content: Text(
            'The entered odometer KM ($odometerKm) is $delta km above the latest '
            'recorded value ($latestKm). Do you want to continue?',
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

    if (_meterImage == null || _billImage == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Capture both meter and bill images.')),
      );
      return;
    }

    final provider = context.read<DriverProvider>();
    final activeDayTrip = _activeDayTrip(provider.trips);
    if (activeDayTrip == null && _selectedVehicleId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select a vehicle for this fuel entry.')),
      );
      return;
    }
    final odometerKm = int.parse(_odometerKmController.text.trim());
    final latestKm = _expectedOdometerKm(provider, activeDayTrip);
    if (latestKm != null && odometerKm < latestKm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Odometer KM cannot be less than the latest recorded value ($latestKm).',
          ),
        ),
      );
      return;
    }
    if (latestKm != null &&
        odometerKm > latestKm + _maxOdometerSubmissionDeltaKm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Odometer KM cannot be greater than the latest recorded value '
            'by more than $_maxOdometerSubmissionDeltaKm km ($latestKm).',
          ),
        ),
      );
      return;
    }
    if (latestKm != null) {
      final confirmed = await _confirmFuelOdometerSubmission(
        latestKm: latestKm,
        odometerKm: odometerKm,
      );
      if (!mounted || !confirmed) {
        return;
      }
    }
    final success = await provider.addFuelRecord(
      liters: double.parse(_litersController.text.trim()),
      amount: double.parse(_amountController.text.trim()),
      odometerKm: odometerKm,
      meterImage: _meterImage!,
      billImage: _billImage!,
      vehicleId: activeDayTrip == null ? _selectedVehicleId : null,
      date: DateTime.now(),
    );

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
            success ? 'Vehicle fuel entry saved.' : provider.error ?? 'Failed'),
      ),
    );

    if (success) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicle Fuel Entry')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Consumer<DriverProvider>(
          builder: (context, provider, _) {
            if (_loadingContext) {
              return const Center(child: CircularProgressIndicator());
            }
            final activeDayTrip = _activeDayTrip(provider.trips);
            final activeVehicleName =
                activeDayTrip?.vehicleNumber?.trim() ?? '';
            final showVehicleDropdown = activeDayTrip == null;
            return Form(
              key: _formKey,
              child: ListView(
                children: [
                  if (activeVehicleName.isNotEmpty) ...[
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0A6B6F).withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color:
                              const Color(0xFF0A6B6F).withValues(alpha: 0.24),
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 42,
                            height: 42,
                            decoration: BoxDecoration(
                              color: const Color(0xFF0A6B6F)
                                  .withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.local_shipping_outlined,
                              color: Color(0xFF0A6B6F),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Auto-selected vehicle',
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodySmall
                                      ?.copyWith(
                                        color: Colors.black
                                            .withValues(alpha: 0.64),
                                      ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  activeVehicleName,
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium
                                      ?.copyWith(
                                        fontWeight: FontWeight.w700,
                                      ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                  ] else if (showVehicleDropdown) ...[
                    Text(
                      'No active day trip found. Select the vehicle for this fuel filling.',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.black.withValues(alpha: 0.66),
                          ),
                    ),
                    const SizedBox(height: 10),
                    DropdownButtonFormField<int>(
                      initialValue: _selectedVehicleId,
                      decoration: const InputDecoration(
                        labelText: 'Select Vehicle',
                        prefixIcon: Icon(Icons.local_shipping_outlined),
                      ),
                      items: provider.vehicles
                          .map(
                            (vehicle) => DropdownMenuItem<int>(
                              value: vehicle.id,
                              child: Text(
                                '${vehicle.vehicleNumber} (${vehicle.status})',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: provider.loading
                          ? null
                          : (value) {
                              setState(() {
                                _selectedVehicleId = value;
                              });
                            },
                      validator: (value) {
                        if (!showVehicleDropdown) {
                          return null;
                        }
                        if (provider.vehicles.isEmpty) {
                          return 'No vehicles available for your transporter.';
                        }
                        if (value == null) {
                          return 'Select a vehicle.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextFormField(
                    controller: _litersController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration:
                        const InputDecoration(labelText: 'Quantity (Liters)'),
                    validator: (value) {
                      final parsed = double.tryParse((value ?? '').trim());
                      if (parsed == null || parsed <= 0) {
                        return 'Invalid liters.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _amountController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Rate/Amount'),
                    validator: (value) {
                      final parsed = double.tryParse((value ?? '').trim());
                      if (parsed == null || parsed < 0) {
                        return 'Invalid amount.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _odometerKmController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Odometer KM'),
                    validator: (value) {
                      if (int.tryParse((value ?? '').trim()) == null) {
                        return 'Invalid odometer KM.';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _pickMeterImage,
                    icon: const Icon(Icons.speed),
                    label: Text(_meterImage == null
                        ? 'Capture Meter Image'
                        : 'Retake Meter Image'),
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
                      child: Text(
                        _meterScanMessage!,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: provider.loading ? null : _pickBillImage,
                    icon: const Icon(Icons.receipt_long),
                    label: Text(_billImage == null
                        ? 'Capture Bill Image'
                        : 'Retake Bill Image'),
                  ),
                  if (_billImage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.file(
                          _billImage!,
                          height: 140,
                          width: double.infinity,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: provider.loading ? null : _submit,
                    child: provider.loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save Vehicle Fuel Entry'),
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
