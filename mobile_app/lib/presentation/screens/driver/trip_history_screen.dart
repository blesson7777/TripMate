import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/driver_provider.dart';

class TripHistoryScreen extends StatefulWidget {
  const TripHistoryScreen({super.key});

  @override
  State<TripHistoryScreen> createState() => _TripHistoryScreenState();
}

class _TripHistoryScreenState extends State<TripHistoryScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DriverProvider>().loadTrips();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Trip History')),
      body: Consumer<DriverProvider>(
        builder: (context, provider, _) {
          if (provider.loading && provider.trips.isEmpty) {
            return const Center(child: CircularProgressIndicator());
          }

          if (provider.error != null && provider.trips.isEmpty) {
            return Center(child: Text(provider.error!));
          }

          if (provider.trips.isEmpty) {
            return const Center(child: Text('No trips found.'));
          }

          return RefreshIndicator(
            onRefresh: provider.loadTrips,
            child: ListView.builder(
              itemCount: provider.trips.length,
              itemBuilder: (context, index) {
                final trip = provider.trips[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: ListTile(
                    title: Text('${trip.startLocation} -> ${trip.destination}'),
                    subtitle: Text(
                      'KM: ${trip.startKm} to ${trip.endKm} | Total: ${trip.totalKm}',
                    ),
                    trailing: Text(trip.createdAt.toLocal().toString().split('.').first),
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
