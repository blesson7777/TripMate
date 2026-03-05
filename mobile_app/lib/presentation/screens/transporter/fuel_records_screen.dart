import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class FuelRecordsScreen extends StatefulWidget {
  const FuelRecordsScreen({super.key});

  @override
  State<FuelRecordsScreen> createState() => _FuelRecordsScreenState();
}

class _FuelRecordsScreenState extends State<FuelRecordsScreen> {
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
      appBar: AppBar(title: const Text('Fuel Records')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE7F1F0), Color(0xFFF8EFE6)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            if (provider.loading && provider.fuelRecords.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null && provider.fuelRecords.isEmpty) {
              return Center(child: Text(provider.error!));
            }

            if (provider.fuelRecords.isEmpty) {
              return const _EmptyState(
                icon: Icons.local_gas_station_outlined,
                message: 'No fuel records available yet.',
              );
            }

            return RefreshIndicator(
              onRefresh: provider.loadDashboardData,
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.fuelRecords.length,
                itemBuilder: (context, index) {
                  final fuel = provider.fuelRecords[index];
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
                                  width: 42,
                                  height: 42,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFCF6E41)
                                        .withValues(alpha: 0.18),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: const Icon(
                                    Icons.local_gas_station_rounded,
                                    color: Color(0xFFCF6E41),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    '${fuel.vehicleNumber} - ${fuel.driverName}',
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium
                                        ?.copyWith(fontWeight: FontWeight.w700),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 10,
                              runSpacing: 8,
                              children: [
                                _InfoChip(
                                    label: 'Liters', value: '${fuel.liters} L'),
                                _InfoChip(
                                  label: 'Amount',
                                  value: fuel.amount.toStringAsFixed(2),
                                ),
                                if (fuel.odometerKm != null)
                                  _InfoChip(
                                    label: 'Odo',
                                    value: '${fuel.odometerKm} KM',
                                  ),
                                _InfoChip(
                                  label: 'Date',
                                  value: fuel.date
                                      .toLocal()
                                      .toString()
                                      .split(' ')
                                      .first,
                                ),
                              ],
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

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F3EE),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        '$label: $value',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Colors.black.withValues(alpha: 0.72),
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
