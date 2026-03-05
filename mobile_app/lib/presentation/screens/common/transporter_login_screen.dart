import 'package:flutter/material.dart';

import '../../../domain/entities/app_user.dart';
import 'role_login_screen.dart';
import 'transporter_register_screen.dart';

class TransporterLoginScreen extends StatelessWidget {
  const TransporterLoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return RoleLoginScreen(
      allowedRole: UserRole.transporter,
      titleText: 'TripMate Transporter',
      subtitleText: 'Login with your transporter account',
      footer: Builder(
        builder: (innerContext) => OutlinedButton.icon(
          onPressed: () {
            Navigator.of(innerContext).push(
              MaterialPageRoute(
                builder: (_) => const TransporterRegisterScreen(),
              ),
            );
          },
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('Create transporter account'),
        ),
      ),
    );
  }
}
