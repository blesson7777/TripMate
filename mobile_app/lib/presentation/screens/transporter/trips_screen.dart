import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/constants/api_constants.dart';
import '../../providers/transporter_provider.dart';
import '../../widgets/staggered_entrance.dart';

class TripsScreen extends StatefulWidget {
  const TripsScreen({super.key});

  @override
  State<TripsScreen> createState() => _TripsScreenState();
}

class _TripsScreenState extends State<TripsScreen> {
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
                message: 'No trips found for the selected scope.',
              );
            }

            return RefreshIndicator(
              onRefresh: provider.loadDashboardData,
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
                itemCount: provider.trips.length,
                itemBuilder: (context, index) {
                  final trip = provider.trips[index];
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
                                    '${trip.startLocation} -> ${trip.destination}',
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium
                                        ?.copyWith(fontWeight: FontWeight.w700),
                                  ),
                                ),
                                if (trip.isLive)
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 8,
                                      vertical: 4,
                                    ),
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
                            const SizedBox(height: 8),
                            if (trip.driverName != null)
                              Text('Driver: ${trip.driverName}'),
                            if (trip.vehicleNumber != null)
                              Text('Vehicle: ${trip.vehicleNumber}'),
                            Text(
                              'Trip KM: ${trip.startKm} -> ${trip.endKm} | Total: ${trip.totalKm}',
                            ),
                            Text(
                              'Attendance KM: ${trip.attendanceStartKm ?? "-"} -> ${trip.attendanceEndKm?.toString() ?? "-"}',
                            ),
                            if (trip.attendanceStatus != null)
                              Text('Status: ${trip.attendanceStatus}'),
                            Text('Created: ${_formatDateTime(trip.createdAt)}'),
                            if (trip.attendanceStartedAt != null)
                              Text('Started: ${_formatDateTime(trip.attendanceStartedAt!)}'),
                            if (trip.attendanceEndedAt != null)
                              Text('Ended: ${_formatDateTime(trip.attendanceEndedAt!)}'),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 10,
                              runSpacing: 8,
                              children: [
                                _InfoChip(
                                    label: 'KM', value: '${trip.totalKm}'),
                                _InfoChip(
                                  label: 'Purpose',
                                  value: trip.purpose ?? 'Not specified',
                                ),
                              ],
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
                    ),
                  );
                },
              ),
            );
          },
        ),
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
                ? const Center(child: Text('No photo'))
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
