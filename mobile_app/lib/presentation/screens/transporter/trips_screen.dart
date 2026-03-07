import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../domain/entities/trip.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'trip_day_details_screen.dart';

class TripsScreen extends StatefulWidget {
  const TripsScreen({super.key});

  @override
  State<TripsScreen> createState() => _TripsScreenState();
}

class _TripsScreenState extends State<TripsScreen> {
  bool _newestFirst = true;

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
      appBar: AppBar(title: const Text('Trips')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFE8F2F2), Color(0xFFF7F0E6)],
          ),
        ),
        child: Consumer<TransporterProvider>(
          builder: (context, provider, _) {
            if (provider.loading && provider.trips.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (provider.error != null && provider.trips.isEmpty) {
              return Center(child: Text(provider.error!));
            }

            if (provider.trips.isEmpty) {
              return const _EmptyState(
                icon: Icons.alt_route_outlined,
                message: 'No trip days found for the selected scope.',
              );
            }

            final dayGroups = _groupedTripDays(provider.trips);
            return RefreshIndicator(
              onRefresh: () => provider.loadDashboardData(force: true),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                children: [
                  Card(
                    margin: const EdgeInsets.only(bottom: 10),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 10,
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.sort_rounded),
                          const SizedBox(width: 8),
                          Text(
                            'Sort by day',
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                          const Spacer(),
                          SegmentedButton<bool>(
                            showSelectedIcon: false,
                            segments: const [
                              ButtonSegment<bool>(
                                value: true,
                                label: Text('Newest'),
                              ),
                              ButtonSegment<bool>(
                                value: false,
                                label: Text('Oldest'),
                              ),
                            ],
                            selected: {_newestFirst},
                            onSelectionChanged: (value) {
                              if (value.isEmpty) {
                                return;
                              }
                              setState(() {
                                _newestFirst = value.first;
                              });
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                  ...List.generate(dayGroups.length, (index) {
                    final group = dayGroups[index];
                    final totalKm = group.trips.fold<int>(
                      0,
                      (sum, trip) => sum + trip.totalKm,
                    );
                    final openRuns = group.trips.where((trip) => trip.isLive).length;
                    return StaggeredEntrance(
                      delay: Duration(milliseconds: 50 * index),
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
                                    width: 40,
                                    height: 40,
                                    decoration: BoxDecoration(
                                      color: const Color(0xFFE08D3C)
                                          .withValues(alpha: 0.18),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Icon(
                                      Icons.alt_route_rounded,
                                      color: Color(0xFFCE7424),
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      _dayTitle(group.date),
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleMedium
                                          ?.copyWith(
                                              fontWeight: FontWeight.w700),
                                    ),
                                  ),
                                  if (openRuns > 0)
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: Colors.orange
                                            .withValues(alpha: 0.15),
                                        borderRadius:
                                            BorderRadius.circular(999),
                                      ),
                                      child: const Text(
                                        'RUN OPEN',
                                        style: TextStyle(
                                          color: Colors.deepOrange,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text('Runs: ${group.trips.length}'),
                              Text('Total KM: $totalKm'),
                              Text('Open runs: $openRuns'),
                              if (group.trips.isNotEmpty)
                                Text(
                                  'Vehicles: ${group.trips.map((trip) => trip.vehicleNumber ?? '-').toSet().join(', ')}',
                                ),
                              const SizedBox(height: 8),
                              Wrap(
                                spacing: 10,
                                runSpacing: 8,
                                children: [
                                  _InfoChip(
                                    label: 'Run Count',
                                    value: '${group.trips.length}',
                                  ),
                                  _InfoChip(
                                    label: 'Total KM',
                                    value: '$totalKm',
                                  ),
                                ],
                              ),
                              const SizedBox(height: 10),
                              FilledButton.icon(
                                onPressed: () {
                                  Navigator.of(context).push(
                                    MaterialPageRoute<void>(
                                      builder: (_) => TripDayDetailsScreen(
                                        selectedDate: group.date,
                                      ),
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.open_in_new),
                                label: const Text('Open Day Details'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  List<_TripDayGroup> _groupedTripDays(List<Trip> allTrips) {
    final buckets = <String, List<Trip>>{};
    final dateMap = <String, DateTime>{};

    for (final trip in allTrips.where((trip) => trip.isDayTrip)) {
      final date = trip.attendanceDate ?? trip.tripStartedAt ?? trip.createdAt;
      final local = DateTime(date.year, date.month, date.day);
      final key = local.toIso8601String();
      buckets.putIfAbsent(key, () => <Trip>[]).add(trip);
      dateMap[key] = local;
    }

    final groups = buckets.entries.map((entry) {
      final trips = entry.value
        ..sort((a, b) {
          final aKey = a.tripStartedAt ?? a.createdAt;
          final bKey = b.tripStartedAt ?? b.createdAt;
          return aKey.compareTo(bKey);
        });
      return _TripDayGroup(
        date: dateMap[entry.key]!,
        trips: trips,
      );
    }).toList();

    groups.sort((a, b) {
      final aKey = a.date;
      final bKey = b.date;
      if (_newestFirst) {
        return bKey.compareTo(aKey);
      }
      return aKey.compareTo(bKey);
    });
    return groups;
  }

  String _dayTitle(DateTime value) {
    return 'Run Summary - ${value.toLocal().toString().split(' ').first}';
  }
}

class _TripDayGroup {
  const _TripDayGroup({
    required this.date,
    required this.trips,
  });

  final DateTime date;
  final List<Trip> trips;
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
        color: const Color(0xFFF4F8F9),
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
