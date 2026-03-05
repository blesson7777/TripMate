import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'attendance_screen.dart';
import 'drivers_screen.dart';
import 'fuel_records_screen.dart';
import 'reports_screen.dart';
import 'transporter_profile_screen.dart';
import 'trips_screen.dart';
import 'vehicles_screen.dart';

class TransporterDashboardScreen extends StatefulWidget {
  const TransporterDashboardScreen({super.key});

  @override
  State<TransporterDashboardScreen> createState() =>
      _TransporterDashboardScreenState();
}

class _TransporterDashboardScreenState
    extends State<TransporterDashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<TransporterProvider>().loadDashboardData();
    });
  }

  Future<void> _refresh() {
    return context.read<TransporterProvider>().loadDashboardData();
  }

  @override
  Widget build(BuildContext context) {
    final username = context
        .select((AuthProvider auth) => auth.user?.username ?? 'Transporter');
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
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
                            'TripMate Command',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 20,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () =>
                              _openPage(const TransporterProfileScreen()),
                          icon: const Icon(
                            Icons.account_circle_outlined,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Welcome back, $username',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 22,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Monitor your fleet and reports in one place.',
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
                child: Consumer<TransporterProvider>(
                  builder: (context, provider, _) {
                    final statCards = [
                      _StatItem(
                        title: 'Vehicles',
                        value: provider.vehicles.length.toString(),
                        icon: Icons.local_shipping_outlined,
                        color: const Color(0xFF0A6B6F),
                      ),
                      _StatItem(
                        title: 'Drivers',
                        value: provider.drivers.length.toString(),
                        icon: Icons.badge_outlined,
                        color: const Color(0xFF228B8D),
                      ),
                      _StatItem(
                        title: 'Trips',
                        value: provider.trips.length.toString(),
                        icon: Icons.alt_route_outlined,
                        color: const Color(0xFFE08D3C),
                      ),
                      _StatItem(
                        title: 'Fuel Logs',
                        value: provider.fuelRecords.length.toString(),
                        icon: Icons.local_gas_station_outlined,
                        color: const Color(0xFFCF6E41),
                      ),
                    ];

                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (provider.error != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: Text(
                              provider.error!,
                              style: TextStyle(color: colors.error),
                            ),
                          ),
                        Text(
                          'Fleet Snapshot',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 10),
                        GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          itemCount: statCards.length,
                          gridDelegate:
                              const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 2,
                            childAspectRatio: 1.55,
                            crossAxisSpacing: 10,
                            mainAxisSpacing: 10,
                          ),
                          itemBuilder: (context, index) {
                            final item = statCards[index];
                            return StaggeredEntrance(
                              delay: Duration(milliseconds: 60 * index),
                              child: _FleetStatCard(item: item),
                            );
                          },
                        ),
                        const SizedBox(height: 18),
                        Text(
                          'Operations',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 8),
                        _DashboardActionCard(
                          title: 'Vehicles',
                          subtitle: 'View all assigned fleet vehicles',
                          icon: Icons.local_shipping_rounded,
                          accent: const Color(0xFF0A6B6F),
                          onTap: () => _openPage(const VehiclesScreen()),
                          delay: const Duration(milliseconds: 140),
                        ),
                        _DashboardActionCard(
                          title: 'Drivers',
                          subtitle: 'Track drivers and assignments',
                          icon: Icons.badge_rounded,
                          accent: const Color(0xFF228B8D),
                          onTap: () => _openPage(const DriversScreen()),
                          delay: const Duration(milliseconds: 200),
                        ),
                        _DashboardActionCard(
                          title: 'Trips',
                          subtitle: 'Inspect journey activity and kilometers',
                          icon: Icons.alt_route_rounded,
                          accent: const Color(0xFFE08D3C),
                          onTap: () => _openPage(const TripsScreen()),
                          delay: const Duration(milliseconds: 260),
                        ),
                        _DashboardActionCard(
                          title: 'Fuel Records',
                          subtitle: 'Analyze fueling entries and costs',
                          icon: Icons.local_gas_station_rounded,
                          accent: const Color(0xFFCF6E41),
                          onTap: () => _openPage(const FuelRecordsScreen()),
                          delay: const Duration(milliseconds: 320),
                        ),
                        _DashboardActionCard(
                          title: 'Reports',
                          subtitle: 'Generate monthly trip sheet insights',
                          icon: Icons.summarize_rounded,
                          accent: const Color(0xFF15616D),
                          onTap: () => _openPage(const ReportsScreen()),
                          delay: const Duration(milliseconds: 380),
                        ),
                        _DashboardActionCard(
                          title: 'Attendance',
                          subtitle: 'Track daily driver attendance and leave marks',
                          icon: Icons.fact_check_rounded,
                          accent: const Color(0xFF0F766E),
                          onTap: () => _openPage(const AttendanceScreen()),
                          delay: const Duration(milliseconds: 440),
                        ),
                        const SizedBox(height: 8),
                        if (provider.loading)
                          const Center(
                            child: Padding(
                              padding: EdgeInsets.symmetric(vertical: 10),
                              child: CircularProgressIndicator(),
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _openPage(Widget page) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => page),
    );
  }
}

class _StatItem {
  const _StatItem({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String title;
  final String value;
  final IconData icon;
  final Color color;
}

class _FleetStatCard extends StatelessWidget {
  const _FleetStatCard({required this.item});

  final _StatItem item;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: item.color.withValues(alpha: 0.15),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              height: 42,
              width: 42,
              decoration: BoxDecoration(
                color: item.color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(item.icon, color: item.color),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.value,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  Text(
                    item.title,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.black.withValues(alpha: 0.65),
                        ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DashboardActionCard extends StatelessWidget {
  const _DashboardActionCard({
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
                      colors: [
                        accent,
                        accent.withValues(alpha: 0.78),
                      ],
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
