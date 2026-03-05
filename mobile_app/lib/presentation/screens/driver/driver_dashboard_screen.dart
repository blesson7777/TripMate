import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'add_trip_screen.dart';
import 'driver_profile_screen.dart';
import 'end_day_screen.dart';
import 'fuel_entry_screen.dart';
import 'start_day_screen.dart';
import 'trip_history_screen.dart';

class DriverDashboardScreen extends StatelessWidget {
  const DriverDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final username =
        context.select((AuthProvider auth) => auth.user?.username ?? 'Driver');

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Container(
              padding: const EdgeInsets.fromLTRB(18, 56, 18, 28),
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFF0A6B6F),
                    Color(0xFF198288),
                  ],
                ),
                borderRadius: BorderRadius.vertical(
                  bottom: Radius.circular(34),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        padding: const EdgeInsets.all(8),
                        child: Image.asset(
                          'assets/branding/tripmate_icon.png',
                          width: 36,
                          height: 36,
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'TripMate Driver',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                            fontSize: 20,
                          ),
                        ),
                      ),
                      IconButton(
                        onPressed: () => _openPage(context, const DriverProfileScreen()),
                        icon: const Icon(Icons.account_circle_outlined,
                            color: Colors.white),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Welcome, $username',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 22,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Manage attendance, trips, fuel, and history.',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.86),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(14, 16, 14, 20),
            sliver: SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Actions',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 10),
                  _ActionCard(
                    title: 'Start Day',
                    subtitle: 'Attendance + odometer + location',
                    icon: Icons.play_circle_fill_rounded,
                    accent: const Color(0xFF0A6B6F),
                    delay: const Duration(milliseconds: 120),
                    onTap: () => _openPage(context, const StartDayScreen()),
                  ),
                  _ActionCard(
                    title: 'Add Trip',
                    subtitle: 'Create trip records under active attendance',
                    icon: Icons.alt_route_rounded,
                    accent: const Color(0xFFE08D3C),
                    delay: const Duration(milliseconds: 180),
                    onTap: () => _openPage(context, const AddTripScreen()),
                  ),
                  _ActionCard(
                    title: 'Fuel Entry',
                    subtitle: 'Upload meter image and bill',
                    icon: Icons.local_gas_station_rounded,
                    accent: const Color(0xFFCF6E41),
                    delay: const Duration(milliseconds: 240),
                    onTap: () => _openPage(context, const FuelEntryScreen()),
                  ),
                  _ActionCard(
                    title: 'End Day',
                    subtitle: 'Close attendance with end odometer',
                    icon: Icons.stop_circle_rounded,
                    accent: const Color(0xFF228B8D),
                    delay: const Duration(milliseconds: 300),
                    onTap: () => _openPage(context, const EndDayScreen()),
                  ),
                  _ActionCard(
                    title: 'Trip History',
                    subtitle: 'Review your previous trips',
                    icon: Icons.history_rounded,
                    accent: const Color(0xFF15616D),
                    delay: const Duration(milliseconds: 360),
                    onTap: () => _openPage(context, const TripHistoryScreen()),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _openPage(BuildContext context, Widget page) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => page),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.accent,
    required this.onTap,
    required this.delay,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final Color accent;
  final VoidCallback onTap;
  final Duration delay;

  @override
  Widget build(BuildContext context) {
    return StaggeredEntrance(
      delay: delay,
      child: Card(
        margin: const EdgeInsets.only(bottom: 10),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            child: Row(
              children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [accent, accent.withValues(alpha: 0.78)],
                    ),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: Colors.white),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style:
                            Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Colors.black.withValues(alpha: 0.6),
                            ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.arrow_forward_ios_rounded, size: 16),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
