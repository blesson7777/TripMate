import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants/api_constants.dart';
import 'core/network/api_client.dart';
import 'data/datasources/auth_remote_data_source.dart';
import 'data/datasources/fleet_remote_data_source.dart';
import 'data/repositories/auth_repository_impl.dart';
import 'data/repositories/fleet_repository_impl.dart';
import 'presentation/providers/auth_provider.dart';
import 'presentation/providers/driver_provider.dart';
import 'presentation/providers/transporter_provider.dart';
import 'presentation/screens/common/login_screen.dart';
import 'presentation/screens/common/role_home_screen.dart';

void main() {
  final apiClient = ApiClient(baseUrl: ApiConstants.baseUrl);
  final authRepository = AuthRepositoryImpl(
    AuthRemoteDataSource(apiClient),
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

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TripMate Fleet',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF006D77)),
        useMaterial3: true,
      ),
      home: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          if (!auth.isLoggedIn) {
            return const LoginScreen();
          }
          return const RoleHomeScreen();
        },
      ),
    );
  }
}
