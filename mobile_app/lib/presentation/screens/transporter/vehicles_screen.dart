import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class VehiclesScreen extends StatefulWidget {
  const VehiclesScreen({super.key});

  @override
  State<VehiclesScreen> createState() => _VehiclesScreenState();
}

class _VehiclesScreenState extends State<VehiclesScreen> {
  Future<void> _openAddVehicleSheet() async {
    final formKey = GlobalKey<FormState>();
    final vehicleNoController = TextEditingController();
    final modelController = TextEditingController();
    var status = 'ACTIVE';

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
          ),
          child: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: StatefulBuilder(
              builder: (context, setSheetState) {
                return Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Add Vehicle',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: vehicleNoController,
                          decoration: const InputDecoration(
                            labelText: 'Vehicle Number',
                            prefixIcon: Icon(Icons.pin_outlined),
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return 'Vehicle number is required';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),
                        TextFormField(
                          controller: modelController,
                          decoration: const InputDecoration(
                            labelText: 'Model',
                            prefixIcon: Icon(Icons.local_shipping_outlined),
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return 'Model is required';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),
                        DropdownButtonFormField<String>(
                          initialValue: status,
                          decoration: const InputDecoration(
                            labelText: 'Status',
                            prefixIcon: Icon(Icons.tune_outlined),
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: 'ACTIVE',
                              child: Text('Active'),
                            ),
                            DropdownMenuItem(
                              value: 'MAINTENANCE',
                              child: Text('Maintenance'),
                            ),
                            DropdownMenuItem(
                              value: 'INACTIVE',
                              child: Text('Inactive'),
                            ),
                          ],
                          onChanged: (value) {
                            if (value == null) {
                              return;
                            }
                            setSheetState(() {
                              status = value;
                            });
                          },
                        ),
                        const SizedBox(height: 14),
                        Consumer<TransporterProvider>(
                          builder: (context, provider, _) {
                            return FilledButton.icon(
                              onPressed: provider.loading
                                  ? null
                                  : () async {
                                      if (!formKey.currentState!.validate()) {
                                        return;
                                      }
                                      final success = await context
                                          .read<TransporterProvider>()
                                          .addVehicle(
                                            vehicleNumber:
                                                vehicleNoController.text.trim(),
                                            model: modelController.text.trim(),
                                            status: status,
                                          );
                                      if (!context.mounted) {
                                        return;
                                      }
                                      if (!success) {
                                        ScaffoldMessenger.of(context)
                                            .showSnackBar(
                                          SnackBar(
                                            content: Text(
                                              context
                                                      .read<TransporterProvider>()
                                                      .error ??
                                                  'Unable to add vehicle',
                                            ),
                                          ),
                                        );
                                        return;
                                      }
                                      Navigator.pop(context);
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(
                                        const SnackBar(
                                          content: Text(
                                            'Vehicle added successfully',
                                          ),
                                        ),
                                      );
                                    },
                              icon: provider.loading
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.add_rounded),
                              label: const Text('Add Vehicle'),
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fleet Vehicles')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAddVehicleSheet,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Add Vehicle'),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE8F2F1), Color(0xFFF4EFE6)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            if (provider.loading && provider.vehicles.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null && provider.vehicles.isEmpty) {
              return Center(child: Text(provider.error!));
            }

            if (provider.vehicles.isEmpty) {
              return const _EmptyState(
                icon: Icons.local_shipping_outlined,
                message: 'No vehicles found for this transporter.',
              );
            }

            return RefreshIndicator(
              onRefresh: provider.loadDashboardData,
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.vehicles.length,
                itemBuilder: (context, index) {
                  final vehicle = provider.vehicles[index];
                  return StaggeredEntrance(
                    delay: Duration(milliseconds: 55 * index),
                    child: Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: ListTile(
                        leading: Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF0A6B6F).withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.local_shipping_outlined,
                            color: Color(0xFF0A6B6F),
                          ),
                        ),
                        title: Text(vehicle.vehicleNumber),
                        subtitle: Text(vehicle.model),
                        trailing: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFEAF7F5),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            vehicle.status,
                            style: const TextStyle(
                              color: Color(0xFF0A6B6F),
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 52, color: Colors.black.withValues(alpha: 0.4)),
            const SizedBox(height: 10),
            Text(
              message,
              style: Theme.of(context).textTheme.bodyLarge,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
