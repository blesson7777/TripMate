import 'package:flutter/material.dart';

import '../../../domain/entities/app_user.dart';
import 'driver_register_screen.dart';
import 'role_login_screen.dart';

class DriverLoginScreen extends StatelessWidget {
  const DriverLoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return RoleLoginScreen(
      allowedRole: UserRole.driver,
      titleText: 'TripMate Driver',
      subtitleText: 'Login with your driver account',
      footer: Builder(
        builder: (innerContext) => OutlinedButton.icon(
          onPressed: () {
            Navigator.of(innerContext).push(
              MaterialPageRoute(
                builder: (_) => const DriverRegisterScreen(),
              ),
            );
          },
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('Create driver account'),
        ),
      ),
    );
  }
}
