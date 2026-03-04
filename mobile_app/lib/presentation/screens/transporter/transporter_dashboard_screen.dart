import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import 'drivers_screen.dart';
import 'fuel_records_screen.dart';
import 'reports_screen.dart';
import 'trips_screen.dart';
import 'vehicles_screen.dart';

class TransporterDashboardScreen extends StatefulWidget {
  const TransporterDashboardScreen({super.key});

  @override
  State<TransporterDashboardScreen> createState() => _TransporterDashboardScreenState();
}

class _TransporterDashboardScreenState extends State<TransporterDashboardScreen> {
  @override
  Widget build(BuildContext context) {
    final username = context.select((AuthProvider auth) => auth.user?.username ?? 'Transporter');

    return Scaffold(
      appBar: AppBar(
        title: Text('Transporter Dashboard - $username'),
        actions: [
          IconButton(
            onPressed: () => context.read<AuthProvider>().logout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _MenuCard(
            icon: Icons.local_shipping,
            title: 'Vehicles',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const VehiclesScreen()),
            ),
          ),
          _MenuCard(
            icon: Icons.badge,
            title: 'Drivers',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const DriversScreen()),
            ),
          ),
          _MenuCard(
            icon: Icons.route,
            title: 'Trips',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const TripsScreen()),
            ),
          ),
          _MenuCard(
            icon: Icons.local_gas_station,
            title: 'Fuel Records',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const FuelRecordsScreen()),
            ),
          ),
          _MenuCard(
            icon: Icons.summarize,
            title: 'Reports',
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const ReportsScreen()),
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuCard extends StatelessWidget {
  const _MenuCard({
    required this.icon,
    required this.title,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
