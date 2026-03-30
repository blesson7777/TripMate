import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

Future<void> sendTripLocationToApi({
  required String baseUrl,
  required String accessToken,
  required double latitude,
  required double longitude,
  double? accuracyMeters,
  double? speedKph,
  DateTime? recordedAt,
}) async {
  final normalizedBase =
      baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
  final uri = Uri.parse('$normalizedBase/attendance/track-location');

  final response = await http
      .post(
        uri,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode(
          {
            'latitude': latitude.toStringAsFixed(6),
            'longitude': longitude.toStringAsFixed(6),
            if (accuracyMeters != null)
              'accuracy_m': accuracyMeters.toStringAsFixed(2),
            if (speedKph != null) 'speed_kph': speedKph.toStringAsFixed(2),
            if (recordedAt != null)
              'recorded_at': recordedAt.toUtc().toIso8601String(),
          },
        ),
      )
      .timeout(const Duration(seconds: 20));

  if (response.statusCode < 200 || response.statusCode >= 300) {
    final snippet = response.body.trim();
    final message =
        snippet.isEmpty ? 'HTTP ${response.statusCode}' : snippet;
    throw Exception('Failed to send location: $message');
  }
}

