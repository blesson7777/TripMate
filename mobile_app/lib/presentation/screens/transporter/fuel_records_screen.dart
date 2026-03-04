import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';

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
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.fuelRecords.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.error != null && provider.fuelRecords.isEmpty) {
            return Center(child: Text(provider.error!));
          }

          return RefreshIndicator(
            onRefresh: provider.loadDashboardData,
            child: ListView.builder(
              itemCount: provider.fuelRecords.length,
              itemBuilder: (context, index) {
                final fuel = provider.fuelRecords[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: ListTile(
                    leading: const Icon(Icons.local_gas_station),
                    title: Text('${fuel.vehicleNumber} - ${fuel.driverName}'),
                    subtitle: Text(
                      '${fuel.liters} L | ${fuel.amount.toStringAsFixed(2)}\n${fuel.date.toLocal().toString().split(' ').first}',
                    ),
                    isThreeLine: true,
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
