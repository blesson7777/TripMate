import 'package:flutter/material.dart';

import '../../widgets/staggered_entrance.dart';
import 'driver_login_screen.dart';
import 'transporter_login_screen.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFFF9F1E2),
              Color(0xFFE6F0EF),
              Color(0xFFD9E7F0),
            ],
          ),
        ),
        child: Stack(
          children: [
            Positioned(
              top: -110,
              right: -40,
              child: _BackdropOrb(
                size: 250,
                color: const Color(0xFF0A6B6F).withValues(alpha: 0.16),
              ),
            ),
            Positioned(
              bottom: -90,
              left: -30,
              child: _BackdropOrb(
                size: 220,
                color: const Color(0xFFE08D3C).withValues(alpha: 0.16),
              ),
            ),
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: StaggeredEntrance(
                    delay: const Duration(milliseconds: 90),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.92),
                          borderRadius: BorderRadius.circular(30),
                          border: Border.all(
                            color: colors.primary.withValues(alpha: 0.1),
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.08),
                              blurRadius: 30,
                              offset: const Offset(0, 18),
                            ),
                          ],
                        ),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(24, 26, 24, 24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SizedBox(
                                height: 56,
                                child: Image.asset(
                                  'assets/branding/tripmate_wordmark.png',
                                  fit: BoxFit.contain,
                                ),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                'Choose app role',
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                              const SizedBox(height: 6),
                              Text(
                                'Open the dedicated login for driver or transporter.',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(
                                      color: colors.onSurface
                                          .withValues(alpha: 0.72),
                                    ),
                              ),
                              const SizedBox(height: 18),
                              _RoleOptionCard(
                                icon: Icons.local_shipping_outlined,
                                title: 'Driver App',
                                subtitle:
                                    'Trips, fuel entries, and day start/end flow.',
                                buttonText: 'Continue as Driver',
                                onTap: () {
                                  Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => const DriverLoginScreen(),
                                    ),
                                  );
                                },
                              ),
                              const SizedBox(height: 12),
                              _RoleOptionCard(
                                icon: Icons.business_outlined,
                                title: 'Transporter App',
                                subtitle:
                                    'Fleet overview, reports, and driver management.',
                                buttonText: 'Continue as Transporter',
                                onTap: () {
                                  Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) =>
                                          const TransporterLoginScreen(),
                                    ),
                                  );
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoleOptionCard extends StatelessWidget {
  const _RoleOptionCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.buttonText,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String buttonText;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: colors.primary.withValues(alpha: 0.12),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  height: 44,
                  width: 44,
                  decoration: BoxDecoration(
                    color: colors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: colors.primary),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: colors.onSurface.withValues(alpha: 0.72),
                  ),
            ),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              onPressed: onTap,
              icon: const Icon(Icons.arrow_forward_rounded),
              label: Text(buttonText),
            ),
          ],
        ),
      ),
    );
  }
}

class _BackdropOrb extends StatelessWidget {
  const _BackdropOrb({
    required this.size,
    required this.color,
  });

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.96, end: 1.04),
      duration: const Duration(milliseconds: 2600),
      curve: Curves.easeInOut,
      builder: (context, value, child) {
        return Transform.scale(
          scale: value,
          child: child,
        );
      },
      onEnd: () {},
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color,
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.6),
              blurRadius: 80,
            ),
          ],
        ),
      ),
    );
  }
}
