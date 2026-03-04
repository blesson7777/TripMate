import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/app_user.dart';
import '../../providers/auth_provider.dart';
import '../driver/driver_dashboard_screen.dart';
import '../transporter/admin_overview_screen.dart';
import '../transporter/transporter_dashboard_screen.dart';

class RoleHomeScreen extends StatelessWidget {
  const RoleHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = context.select((AuthProvider provider) => provider.user);
    if (user == null) {
      return const SizedBox.shrink();
    }

    switch (user.role) {
      case UserRole.driver:
        return const DriverDashboardScreen();
      case UserRole.transporter:
        return const TransporterDashboardScreen();
      case UserRole.admin:
        return const AdminOverviewScreen();
    }
  }
}
