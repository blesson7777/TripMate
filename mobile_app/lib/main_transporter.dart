import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants/api_constants.dart';
import 'core/network/api_client.dart';
import 'data/datasources/auth_local_data_source.dart';
import 'data/datasources/auth_remote_data_source.dart';
import 'data/datasources/fleet_remote_data_source.dart';
import 'data/repositories/auth_repository_impl.dart';
import 'data/repositories/fleet_repository_impl.dart';
import 'presentation/providers/auth_provider.dart';
import 'presentation/providers/transporter_provider.dart';
import 'presentation/screens/common/transporter_login_screen.dart';
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
          create: (_) => TransporterProvider(fleetRepository),
        ),
      ],
      child: const TripMateTransporterApp(),
    ),
  );
}

class TripMateTransporterApp extends StatelessWidget {
  const TripMateTransporterApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TripMate Transporter',
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
            return const TransporterLoginScreen();
          }
          return const TransporterDashboardScreen();
        },
      ),
    );
  }
}
