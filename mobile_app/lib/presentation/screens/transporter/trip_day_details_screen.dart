import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/constants/api_constants.dart';
import '../../../domain/entities/trip.dart';
import '../../providers/transporter_provider.dart';

class TripDayDetailsScreen extends StatefulWidget {
  const TripDayDetailsScreen({
    required this.selectedDate,
    super.key,
  });

  final DateTime selectedDate;

  @override
  State<TripDayDetailsScreen> createState() => _TripDayDetailsScreenState();
}

class _TripDayDetailsScreenState extends State<TripDayDetailsScreen> {
  bool _sharingInProgress = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Trip Day Details')),
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

            final dayTrips = _dayTrips(provider.trips, widget.selectedDate);
            if (dayTrips.isEmpty) {
              return const Center(child: Text('Selected run day is not available.'));
            }

            final totalKm = dayTrips.fold<int>(0, (sum, trip) => sum + trip.totalKm);
            return RefreshIndicator(
              onRefresh: provider.loadDashboardData,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 20),
                children: [
                  _SectionHeader(
                    'Runs on ${widget.selectedDate.toLocal().toString().split(' ').first}',
                  ),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Run count: ${dayTrips.length}',
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                          ),
                          const SizedBox(height: 4),
                          Text('Total KM: $totalKm'),
                          Text(
                            'Vehicles: ${dayTrips.map((trip) => trip.vehicleNumber ?? '-').toSet().join(', ')}',
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  ...dayTrips.map(
                    (trip) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _buildTripCard(
                        trip: trip,
                        routeLabel: _runLabel(trip),
                        highlight: trip.isLive,
                      ),
                    ),
                  ),
                  if (_sharingInProgress) ...[
                    const SizedBox(height: 8),
                    const LinearProgressIndicator(),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  List<Trip> _dayTrips(List<Trip> allTrips, DateTime selectedDate) {
    final normalizedDate = DateTime(
      selectedDate.year,
      selectedDate.month,
      selectedDate.day,
    );
    final items = allTrips.where((trip) {
      if (!trip.isDayTrip) {
        return false;
      }
      final source = trip.attendanceDate ?? trip.tripStartedAt ?? trip.createdAt;
      final candidate = DateTime(source.year, source.month, source.day);
      return candidate == normalizedDate;
    }).toList();
    items.sort((a, b) {
      final aKey = a.tripStartedAt ?? a.createdAt;
      final bKey = b.tripStartedAt ?? b.createdAt;
      return aKey.compareTo(bKey);
    });
    return items;
  }

  String _runLabel(Trip trip) {
    final service = trip.attendanceServiceName?.trim() ?? '';
    final vehicle = trip.vehicleNumber?.trim() ?? '';
    if (service.isNotEmpty && vehicle.isNotEmpty) {
      return '$service | $vehicle';
    }
    if (service.isNotEmpty) {
      return service;
    }
    if (vehicle.isNotEmpty) {
      return vehicle;
    }
    return 'Run';
  }

  Widget _buildTripCard({
    required Trip trip,
    required String routeLabel,
    bool highlight = false,
  }) {
    final openingImageUrl = _resolveMediaUrl(trip.openingOdoImage);
    final closingImageUrl = _resolveMediaUrl(trip.closingOdoImage);

    return Card(
      color: highlight ? const Color(0xFFF2F9FA) : null,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              routeLabel,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            Text('KM: ${trip.startKm} -> ${trip.endKm} | Total: ${trip.totalKm}'),
            if (trip.driverName != null) Text('Driver: ${trip.driverName}'),
            if (trip.vehicleNumber != null) Text('Vehicle: ${trip.vehicleNumber}'),
            if (trip.attendanceServiceName != null &&
                trip.attendanceServiceName!.trim().isNotEmpty)
              Text('Service: ${trip.attendanceServiceName}'),
            if (trip.tripStartedAt != null)
              Text('Started: ${_formatDateTime(trip.tripStartedAt!)}'),
            if (trip.tripEndedAt != null)
              Text('Ended: ${_formatDateTime(trip.tripEndedAt!)}'),
            if (trip.purpose != null && trip.purpose!.trim().isNotEmpty)
              Text('Purpose: ${trip.purpose}'),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _PhotoPreview(
                    title: 'Opening',
                    imageUrl: openingImageUrl,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _PhotoPreview(
                    title: 'Closing',
                    imageUrl: closingImageUrl,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _ShareTripButton(
                  label: 'WhatsApp Opening',
                  onPressed: _sharingInProgress
                      ? null
                      : () => _shareTripPhotos(
                            trip: trip,
                            routeLabel: routeLabel,
                            openingImageUrl: openingImageUrl,
                            closingImageUrl: closingImageUrl,
                            includeOpening: true,
                            includeClosing: false,
                          ),
                ),
                _ShareTripButton(
                  label: 'WhatsApp Closing',
                  onPressed: _sharingInProgress
                      ? null
                      : () => _shareTripPhotos(
                            trip: trip,
                            routeLabel: routeLabel,
                            openingImageUrl: openingImageUrl,
                            closingImageUrl: closingImageUrl,
                            includeOpening: false,
                            includeClosing: true,
                          ),
                ),
                _ShareTripButton(
                  label: 'WhatsApp Both',
                  onPressed: _sharingInProgress
                      ? null
                      : () => _shareTripPhotos(
                            trip: trip,
                            routeLabel: routeLabel,
                            openingImageUrl: openingImageUrl,
                            closingImageUrl: closingImageUrl,
                            includeOpening: true,
                            includeClosing: true,
                          ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _shareTripPhotos({
    required Trip trip,
    required String routeLabel,
    required String? openingImageUrl,
    required String? closingImageUrl,
    required bool includeOpening,
    required bool includeClosing,
  }) async {
    final selectedUrls = <String>[];
    final hasOpeningPhoto = includeOpening && openingImageUrl != null;
    final hasClosingPhoto = includeClosing && closingImageUrl != null;
    if (hasOpeningPhoto) {
      selectedUrls.add(openingImageUrl);
    }
    if (hasClosingPhoto) {
      selectedUrls.add(closingImageUrl);
    }

    if (selectedUrls.isEmpty) {
      _showMessage('Selected odometer photo is not available.');
      return;
    }
    if (_sharingInProgress) {
      return;
    }

    setState(() {
      _sharingInProgress = true;
    });

    try {
      final files = <XFile>[];
      for (var index = 0; index < selectedUrls.length; index++) {
        final file = await _downloadImageForShare(
          selectedUrls[index],
          routeLabel,
          index,
        );
        files.add(XFile(file.path));
      }

      await Share.shareXFiles(
        files,
        subject: 'Trip Odometer Photos',
        text: _buildShareCaption(
          trip: trip,
          includeOpening: hasOpeningPhoto,
          includeClosing: hasClosingPhoto,
        ),
      );
    } catch (_) {
      _showMessage('Unable to share trip photos right now.');
    } finally {
      if (mounted) {
        setState(() {
          _sharingInProgress = false;
        });
      }
    }
  }

  Future<File> _downloadImageForShare(
    String imageUrl,
    String routeLabel,
    int index,
  ) async {
    final response = await http.get(Uri.parse(imageUrl));
    if (response.statusCode != 200) {
      throw Exception('Image download failed.');
    }

    final safeRoute = routeLabel.replaceAll(RegExp(r'[^a-zA-Z0-9]+'), '_');
    final extension = _guessExtensionFromPath(Uri.parse(imageUrl).path);
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    final path = '${Directory.systemTemp.path}'
        '${Platform.pathSeparator}tripmate_${safeRoute}_${timestamp}_$index.$extension';
    final file = File(path);
    await file.writeAsBytes(response.bodyBytes, flush: true);
    return file;
  }

  String _guessExtensionFromPath(String path) {
    final lower = path.toLowerCase();
    if (lower.endsWith('.png')) {
      return 'png';
    }
    if (lower.endsWith('.webp')) {
      return 'webp';
    }
    if (lower.endsWith('.gif')) {
      return 'gif';
    }
    if (lower.endsWith('.jpeg')) {
      return 'jpeg';
    }
    return 'jpg';
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  String _formatDateTime(DateTime value) {
    return value.toLocal().toString().split('.').first;
  }

  String _buildShareCaption({
    required Trip trip,
    required bool includeOpening,
    required bool includeClosing,
  }) {
    final serviceName = _shareServiceName(trip);
    final tripDate = _shareDateLabel(trip);
    final opening = '$serviceName Opening KM: ${trip.startKm} ($tripDate)';
    final closing = '$serviceName Closing KM: ${trip.endKm} ($tripDate)';

    if (includeOpening && includeClosing) {
      return '$opening\n$closing';
    }
    if (includeOpening) {
      return opening;
    }
    return closing;
  }

  String _shareServiceName(Trip trip) {
    final raw = trip.attendanceServiceName?.trim() ?? '';
    if (raw.isNotEmpty) {
      return raw;
    }
    return 'Trip Service';
  }

  String _shareDateLabel(Trip trip) {
    final sourceDate = trip.tripStartedAt ?? trip.attendanceDate ?? trip.createdAt;
    final local = sourceDate.toLocal();
    final dd = local.day.toString().padLeft(2, '0');
    final mm = local.month.toString().padLeft(2, '0');
    return '$dd-$mm-${local.year}';
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

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
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
            height: 110,
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

class _ShareTripButton extends StatelessWidget {
  const _ShareTripButton({
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: const Icon(Icons.share_outlined, size: 18),
      label: Text(label),
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF1B8C62),
        side: const BorderSide(color: Color(0xFF1B8C62)),
      ),
    );
  }
}
