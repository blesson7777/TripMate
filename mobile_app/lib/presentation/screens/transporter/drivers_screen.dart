import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/transporter_provider.dart';

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Drivers')),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.drivers.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.error != null && provider.drivers.isEmpty) {
            return Center(child: Text(provider.error!));
          }

          return RefreshIndicator(
            onRefresh: provider.loadDashboardData,
            child: ListView.builder(
              itemCount: provider.drivers.length,
              itemBuilder: (context, index) {
                final driver = provider.drivers[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: ListTile(
                    leading: const Icon(Icons.badge),
                    title: Text(driver.username),
                    subtitle: Text(
                      'License: ${driver.licenseNumber}\nVehicle: ${driver.vehicleNumber ?? "Not assigned"}',
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
