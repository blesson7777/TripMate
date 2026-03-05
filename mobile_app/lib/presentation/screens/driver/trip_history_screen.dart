import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/api_constants.dart';
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
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${trip.startLocation} -> ${trip.destination}',
                                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                      fontWeight: FontWeight.w700,
                                    ),
                              ),
                            ),
                            if (trip.isLive)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.orange.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: const Text(
                                  'LIVE',
                                  style: TextStyle(
                                    color: Colors.deepOrange,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Trip KM: ${trip.startKm} -> ${trip.endKm} | Total: ${trip.totalKm}',
                        ),
                        Text(
                          'Attendance KM: ${trip.attendanceStartKm ?? "-"} -> ${trip.attendanceEndKm?.toString() ?? "-"}',
                        ),
                        if (trip.vehicleNumber != null)
                          Text('Vehicle: ${trip.vehicleNumber}'),
                        if (trip.attendanceStatus != null)
                          Text('Status: ${trip.attendanceStatus}'),
                        Text('Created: ${_formatDateTime(trip.createdAt)}'),
                        if (trip.attendanceStartedAt != null)
                          Text('Started: ${_formatDateTime(trip.attendanceStartedAt!)}'),
                        if (trip.attendanceEndedAt != null)
                          Text('Ended: ${_formatDateTime(trip.attendanceEndedAt!)}'),
                        if (trip.purpose != null && trip.purpose!.trim().isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text('Purpose: ${trip.purpose}'),
                          ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: _PhotoPreview(
                                title: 'Opening',
                                imageUrl: _resolveMediaUrl(trip.openingOdoImage),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: _PhotoPreview(
                                title: 'Closing',
                                imageUrl: _resolveMediaUrl(trip.closingOdoImage),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }

  String _formatDateTime(DateTime value) {
    return value.toLocal().toString().split('.').first;
  }

  String? _resolveMediaUrl(String? rawPath) {
    if (rawPath == null || rawPath.trim().isEmpty) {
      return null;
    }

    final path = rawPath.trim();
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return path;
    }

    final apiBaseUri = Uri.parse(ApiConstants.baseUrl);
    final mediaPath = path.startsWith('/') ? path : '/$path';
    return apiBaseUri
        .replace(path: mediaPath, query: null, fragment: null)
        .toString();
  }
}

class _PhotoPreview extends StatelessWidget {
  const _PhotoPreview({
    required this.title,
    required this.imageUrl,
  });

  final String title;
  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$title Odometer',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Container(
            height: 116,
            width: double.infinity,
            color: Colors.black.withValues(alpha: 0.06),
            child: imageUrl == null
                ? const Center(
                    child: Text('No photo'),
                  )
                : InkWell(
                    onTap: () => _openImage(context, imageUrl!),
                    child: Image.network(
                      imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const Center(
                        child: Text('Image error'),
                      ),
                    ),
                  ),
          ),
        ),
      ],
    );
  }

  void _openImage(BuildContext context, String image) {
    showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: InteractiveViewer(
          minScale: 0.7,
          maxScale: 4.0,
          child: Image.network(
            image,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => const SizedBox(
              height: 240,
              child: Center(child: Text('Unable to load image')),
            ),
          ),
        ),
      ),
    );
  }
}
