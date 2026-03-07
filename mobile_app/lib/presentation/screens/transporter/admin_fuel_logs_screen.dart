import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';

class AdminFuelLogsScreen extends StatefulWidget {
  const AdminFuelLogsScreen({super.key});

  @override
  State<AdminFuelLogsScreen> createState() => _AdminFuelLogsScreenState();
}

class _AdminFuelLogsScreenState extends State<AdminFuelLogsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<TransporterProvider>();
      Future.wait([
        provider.loadDashboardData(prefetchHeavyData: false),
        provider.loadFuelRecords(),
      ]);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Admin All Fuel Logs')),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.fuelRecords.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }
          if (provider.error != null && provider.fuelRecords.isEmpty) {
            return Center(child: Text(provider.error!));
          }
          if (provider.fuelRecords.isEmpty) {
            return const Center(child: Text('No fuel logs available.'));
          }
          return RefreshIndicator(
            onRefresh: () => Future.wait([
              provider.loadDashboardData(
                force: true,
                prefetchHeavyData: false,
              ),
              provider.loadFuelRecords(),
            ]),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: provider.fuelRecords.length,
              itemBuilder: (context, index) {
                final item = provider.fuelRecords[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    title: Text('${item.vehicleNumber} - ${item.driverName}'),
                    subtitle: Text(
                      item.isTowerDiesel
                          ? 'Type: Tower Diesel\n'
                              'Date: ${_formatDate(item.effectiveDate)}\n'
                              'Site: ${item.siteName.isEmpty ? '-' : item.siteName}\n'
                              'Fuel: ${item.fuelFilled.toStringAsFixed(2)} | Run: ${item.runKm}'
                          : 'Type: Vehicle Fuel\n'
                              'Date: ${_formatDate(item.effectiveDate)}\n'
                              'Liters: ${item.liters.toStringAsFixed(2)} | Amount: ${item.amount.toStringAsFixed(2)}'
                              '${item.odometerKm != null ? ' | Odo: ${item.odometerKm}' : ''}',
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }

  String _formatDate(DateTime value) {
    final date = value.toLocal();
    final dd = date.day.toString().padLeft(2, '0');
    final mm = date.month.toString().padLeft(2, '0');
    return '$dd-$mm-${date.year}';
  }
}
