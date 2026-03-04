import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';

class VehiclesScreen extends StatefulWidget {
  const VehiclesScreen({super.key});

  @override
  State<VehiclesScreen> createState() => _VehiclesScreenState();
}

class _VehiclesScreenState extends State<VehiclesScreen> {
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
      appBar: AppBar(title: const Text('Vehicles')),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.vehicles.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.error != null && provider.vehicles.isEmpty) {
            return Center(child: Text(provider.error!));
          }

          return RefreshIndicator(
            onRefresh: provider.loadDashboardData,
            child: ListView.builder(
              itemCount: provider.vehicles.length,
              itemBuilder: (context, index) {
                final vehicle = provider.vehicles[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: ListTile(
                    leading: const Icon(Icons.local_shipping),
                    title: Text(vehicle.vehicleNumber),
                    subtitle: Text('${vehicle.model} | ${vehicle.status}'),
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
