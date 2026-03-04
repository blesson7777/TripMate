import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';
import 'drivers_screen.dart';
import 'fuel_records_screen.dart';
import 'reports_screen.dart';
import 'trips_screen.dart';
import 'vehicles_screen.dart';

class AdminOverviewScreen extends StatefulWidget {
  const AdminOverviewScreen({super.key});

  @override
  State<AdminOverviewScreen> createState() => _AdminOverviewScreenState();
}

class _AdminOverviewScreenState extends State<AdminOverviewScreen> {
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
      appBar: AppBar(
        title: const Text('Admin Overview'),
        actions: [
          IconButton(
            onPressed: () => context.read<AuthProvider>().logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: Consumer<TransporterProvider>(
        builder: (context, provider, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  _StatCard(title: 'Vehicles', value: provider.vehicles.length.toString()),
                  _StatCard(title: 'Drivers', value: provider.drivers.length.toString()),
                  _StatCard(title: 'Trips', value: provider.trips.length.toString()),
                  _StatCard(
                    title: 'Fuel Records',
                    value: provider.fuelRecords.length.toString(),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              _NavButton(
                title: 'Manage Vehicles',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const VehiclesScreen()),
                ),
              ),
              _NavButton(
                title: 'View Drivers',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const DriversScreen()),
                ),
              ),
              _NavButton(
                title: 'View Trips',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const TripsScreen()),
                ),
              ),
              _NavButton(
                title: 'View Fuel Records',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const FuelRecordsScreen()),
                ),
              ),
              _NavButton(
                title: 'Monthly Reports',
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const ReportsScreen()),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.title, required this.value});

  final String title;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title),
              const SizedBox(height: 8),
              Text(
                value,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({required this.title, required this.onTap});

  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        title: Text(title),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
