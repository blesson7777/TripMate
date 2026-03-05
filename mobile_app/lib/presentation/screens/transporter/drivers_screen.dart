import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'driver_allocation_screen.dart';

class DriversScreen extends StatefulWidget {
  const DriversScreen({super.key});

  @override
  State<DriversScreen> createState() => _DriversScreenState();
}

class _DriversScreenState extends State<DriversScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  void _openAllocationPage() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const DriverAllocationScreen()),
    );
  }

  Future<void> _openVehicleAllocationSheet() async {
    final provider = context.read<TransporterProvider>();
    final drivers = provider.drivers;
    final vehicles = provider.vehicles;

    if (drivers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No drivers available for vehicle allocation')),
      );
      return;
    }

    int selectedDriverId = drivers.first.id;
    int? selectedVehicleId = drivers.first.vehicleId;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Vehicle Allocation',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Select driver and assign or unassign a vehicle.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black.withValues(alpha: 0.68),
                        ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<int>(
                    initialValue: selectedDriverId,
                    decoration: const InputDecoration(
                      labelText: 'Driver',
                      prefixIcon: Icon(Icons.person_outline_rounded),
                    ),
                    items: drivers
                        .map(
                          (driver) => DropdownMenuItem<int>(
                            value: driver.id,
                            child: Text(driver.username),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) {
                        return;
                      }
                      final selectedDriver = drivers.firstWhere(
                        (driver) => driver.id == value,
                      );
                      setSheetState(() {
                        selectedDriverId = value;
                        selectedVehicleId = selectedDriver.vehicleId;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedVehicleId,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle',
                      prefixIcon: Icon(Icons.local_shipping_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Unassign vehicle'),
                      ),
                      ...vehicles.map(
                        (vehicle) => DropdownMenuItem<int?>(
                          value: vehicle.id,
                          child: Text('${vehicle.vehicleNumber} - ${vehicle.model}'),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedVehicleId = value;
                      });
                    },
                  ),
                  const SizedBox(height: 14),
                  Consumer<TransporterProvider>(
                    builder: (context, transporterProvider, _) {
                      return FilledButton.icon(
                        onPressed: transporterProvider.loading
                            ? null
                            : () async {
                                final success = await context
                                    .read<TransporterProvider>()
                                    .assignVehicleToDriver(
                                      driverId: selectedDriverId,
                                      vehicleId: selectedVehicleId,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context.read<TransporterProvider>().error ??
                                            'Unable to update vehicle allocation',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Vehicle allocation updated'),
                                  ),
                                );
                              },
                        icon: transporterProvider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save_outlined),
                        label: const Text('Save'),
                      );
                    },
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  Future<void> _openAssignVehicleSheet({
    required int driverId,
    required int? selectedVehicleId,
  }) async {
    final vehicles = context.read<TransporterProvider>().vehicles;
    int? selectedId = selectedVehicleId;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Allocate Vehicle',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Choose a vehicle for this driver. You can also unassign.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black.withValues(alpha: 0.68),
                        ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<int?>(
                    initialValue: selectedId,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle',
                      prefixIcon: Icon(Icons.local_shipping_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<int?>(
                        value: null,
                        child: Text('Unassign vehicle'),
                      ),
                      ...vehicles.map(
                        (vehicle) => DropdownMenuItem<int?>(
                          value: vehicle.id,
                          child: Text('${vehicle.vehicleNumber} - ${vehicle.model}'),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      setSheetState(() {
                        selectedId = value;
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
                                final success = await context
                                    .read<TransporterProvider>()
                                    .assignVehicleToDriver(
                                      driverId: driverId,
                                      vehicleId: selectedId,
                                    );
                                if (!context.mounted) {
                                  return;
                                }
                                if (!success) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                        context.read<TransporterProvider>().error ??
                                            'Unable to update vehicle allocation',
                                      ),
                                    ),
                                  );
                                  return;
                                }
                                Navigator.pop(context);
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Vehicle allocation updated'),
                                  ),
                                );
                              },
                        icon: provider.loading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.save_outlined),
                        label: const Text('Save'),
                      );
                    },
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Drivers'),
        actions: [
          IconButton(
            onPressed: _openVehicleAllocationSheet,
            icon: const Icon(Icons.directions_car_filled_outlined),
            tooltip: 'Vehicle Allocation',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAllocationPage,
        icon: const Icon(Icons.person_add_alt_1_rounded),
        label: const Text('Allocate Driver'),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE9F2F2), Color(0xFFF5EFE7)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            if (provider.loading && provider.drivers.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null && provider.drivers.isEmpty) {
              return Center(child: Text(provider.error!));
            }

            if (provider.drivers.isEmpty) {
              return const _EmptyState(
                icon: Icons.badge_outlined,
                message: 'No drivers are assigned yet.',
              );
            }

            return RefreshIndicator(
              onRefresh: provider.loadDashboardData,
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.drivers.length,
                itemBuilder: (context, index) {
                  final driver = provider.drivers[index];
                  return StaggeredEntrance(
                    delay: Duration(milliseconds: 55 * index),
                    child: Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 46,
                                  height: 46,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF228B8D)
                                        .withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: const Icon(
                                    Icons.person_outline_rounded,
                                    color: Color(0xFF228B8D),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        driver.username,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                              fontWeight: FontWeight.w700,
                                            ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'License: ${driver.licenseNumber}',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                      Text(
                                        'Vehicle: ${driver.vehicleNumber ?? "Not assigned"}',
                                        style:
                                            Theme.of(context).textTheme.bodySmall,
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Align(
                              alignment: Alignment.centerRight,
                              child: OutlinedButton.icon(
                                onPressed: () => _openAssignVehicleSheet(
                                  driverId: driver.id,
                                  selectedVehicleId: driver.vehicleId,
                                ),
                                icon: const Icon(Icons.directions_car_filled_outlined),
                                label: const Text('Allocate Vehicle'),
                              ),
                            ),
                          ],
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
