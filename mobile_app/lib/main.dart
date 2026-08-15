import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants/api_constants.dart';
import 'core/network/api_client.dart';
import 'data/datasources/auth_local_data_source.dart';
import 'data/datasources/auth_remote_data_source.dart';
import 'data/datasources/fleet_remote_data_source.dart';
import 'data/repositories/auth_repository_impl.dart';
import 'data/repositories/fleet_repository_impl.dart';
import 'domain/entities/app_user.dart';
import 'presentation/providers/auth_provider.dart';
import 'presentation/providers/driver_provider.dart';
import 'presentation/providers/transporter_provider.dart';
import 'presentation/screens/common/driver_login_screen.dart';
import 'presentation/screens/common/transporter_login_screen.dart';
import 'presentation/screens/driver/driver_dashboard_screen.dart';
import 'presentation/screens/transporter/transporter_dashboard_screen.dart';
import 'presentation/theme/tripmate_theme.dart';

void main() {
  final apiClient = ApiClient(baseUrl: ApiConstants.baseUrl);
  final authRepository = AuthRepositoryImpl(
    AuthRemoteDataSource(apiClient),
    AuthLocalDataSource(),
    apiClient,
  );
  final fleetRepository = FleetRepositoryImpl(
    FleetRemoteDataSource(apiClient),
  );

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthProvider(authRepository),
        ),
        ChangeNotifierProvider(
          create: (_) => DriverProvider(fleetRepository),
        ),
        ChangeNotifierProvider(
          create: (_) => TransporterProvider(fleetRepository),
        ),
      ],
      child: const TripMateApp(),
    ),
  );
}

class TripMateApp extends StatelessWidget {
  const TripMateApp({super.key});

  static const _flavor = String.fromEnvironment('FLUTTER_APP_FLAVOR');

  bool get _isTransporterApp => _flavor.toLowerCase().contains('transporter');

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: _isTransporterApp ? 'TripMate Transporter' : 'TripMate Driver',
      debugShowCheckedModeBanner: false,
      theme: TripMateTheme.transporterTheme(),
      home: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          if (!auth.isReady) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          if (!auth.isLoggedIn) {
            return _isTransporterApp
                ? const TransporterLoginScreen()
                : const DriverLoginScreen();
          }
          if (_isTransporterApp && auth.user?.role == UserRole.transporter) {
            return const TransporterDashboardScreen();
          }
          if (!_isTransporterApp && auth.user?.role == UserRole.driver) {
            return const DriverDashboardScreen();
          }
          auth.logout();
          return _isTransporterApp
              ? const TransporterLoginScreen()
              : const DriverLoginScreen();
        },
      ),
    );
  }
}
