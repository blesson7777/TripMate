import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import 'add_trip_screen.dart';
import 'end_day_screen.dart';
import 'fuel_entry_screen.dart';
import 'start_day_screen.dart';
import 'trip_history_screen.dart';

class DriverDashboardScreen extends StatelessWidget {
  const DriverDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final username = context.select((AuthProvider auth) => auth.user?.username ?? 'Driver');

    return Scaffold(
      appBar: AppBar(
        title: Text('Driver Dashboard - $username'),
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
          _ActionCard(
            title: 'Start Day',
            subtitle: 'Attendance + odometer + location',
            icon: Icons.play_circle_fill,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const StartDayScreen()),
            ),
          ),
          _ActionCard(
            title: 'Add Trip',
            subtitle: 'Create trip records under active attendance',
            icon: Icons.alt_route,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AddTripScreen()),
            ),
          ),
          _ActionCard(
            title: 'Fuel Entry',
            subtitle: 'Upload fuel meter image and bill',
            icon: Icons.local_gas_station,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const FuelEntryScreen()),
            ),
          ),
          _ActionCard(
            title: 'End Day',
            subtitle: 'Closing odometer and attendance end',
            icon: Icons.stop_circle,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const EndDayScreen()),
            ),
          ),
          _ActionCard(
            title: 'Trip History',
            subtitle: 'View past trips',
            icon: Icons.history,
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const TripHistoryScreen()),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
