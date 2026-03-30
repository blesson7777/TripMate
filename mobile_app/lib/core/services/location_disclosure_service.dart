import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocationDisclosureService {
  LocationDisclosureService._();

  static final LocationDisclosureService instance = LocationDisclosureService._();

  static const String _trackingDisclosureAcceptedKey =
      'tripmate_tracking_disclosure_accepted_v1';

  Future<bool> ensureTripTrackingDisclosureAccepted(BuildContext context) async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(_trackingDisclosureAcceptedKey) == true) {
      return true;
    }

    if (!context.mounted) {
      return false;
    }

    final accepted = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Trip Location Monitoring'),
          content: const Text(
            'TripMate uses location while a trip is open to monitor the active '
            'run, show live trip status to authorized fleet staff, and record '
            'route history. On Android, this may continue when the app is '
            'minimized or closed until the trip is ended.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Not Now'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Continue'),
            ),
          ],
        );
      },
    );

    final allowed = accepted ?? false;
    if (allowed) {
      await prefs.setBool(_trackingDisclosureAcceptedKey, true);
    }
    return allowed;
  }
}
