import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../domain/entities/app_user.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/staggered_entrance.dart';
import 'forgot_password_screen.dart';

class RoleLoginScreen extends StatefulWidget {
  const RoleLoginScreen({
    super.key,
    required this.allowedRole,
    required this.titleText,
    required this.subtitleText,
    this.footer,
  });

  final UserRole allowedRole;
  final String titleText;
  final String subtitleText;
  final Widget? footer;

  @override
  State<RoleLoginScreen> createState() => _RoleLoginScreenState();
}

class _RoleLoginScreenState extends State<RoleLoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _credentialController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;

  @override
  void dispose() {
    _credentialController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final auth = context.read<AuthProvider>();
    final credential = _credentialController.text.trim();
    final password = _passwordController.text.trim();

    if (widget.allowedRole == UserRole.driver ||
        widget.allowedRole == UserRole.transporter) {
      final otpSent = widget.allowedRole == UserRole.driver
          ? await auth.requestDriverLoginOtp(
              credential: credential,
              password: password,
            )
          : await auth.requestTransporterLoginOtp(
              credential: credential,
              password: password,
            );
      if (!mounted) {
        return;
      }
      if (!otpSent) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(auth.error ?? 'Login failed')),
        );
        return;
      }
      await _openOtpDialog(
        credential: credential,
        password: password,
        role: widget.allowedRole,
      );
      return;
    }

    final success = await auth.login(
      credential: credential,
      password: password,
    );

    if (!mounted) {
      return;
    }

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(auth.error ?? 'Login failed')),
      );
      return;
    }

    if (auth.user?.role != widget.allowedRole) {
      auth.logout();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'This app is only for ${_roleLabel(widget.allowedRole)} accounts.',
          ),
        ),
      );
    }
  }

  Future<void> _openOtpDialog({
    required String credential,
    required String password,
    required UserRole role,
  }) async {
    final auth = context.read<AuthProvider>();
    final otpController = TextEditingController();
    var busy = false;

    await showDialog<void>(
      context: context,
      barrierDismissible: !busy,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            Future<void> verifyOtp() async {
              final otp = otpController.text.trim();
              if (otp.isEmpty) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  const SnackBar(content: Text('Enter the OTP sent to email.')),
                );
                return;
              }
              setDialogState(() {
                busy = true;
              });
              final success = role == UserRole.driver
                  ? await auth.verifyDriverLoginOtp(
                      credential: credential,
                      password: password,
                      otp: otp,
                    )
                  : await auth.verifyTransporterLoginOtp(
                      credential: credential,
                      password: password,
                      otp: otp,
                    );
              if (!mounted || !dialogContext.mounted) {
                return;
              }
              setDialogState(() {
                busy = false;
              });
              if (!success) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  SnackBar(
                    content: Text(auth.error ?? 'OTP verification failed.'),
                  ),
                );
                return;
              }
              Navigator.of(dialogContext).pop();
            }

            Future<void> resendOtp() async {
              setDialogState(() {
                busy = true;
              });
              final sent = role == UserRole.driver
                  ? await auth.requestDriverLoginOtp(
                      credential: credential,
                      password: password,
                    )
                  : await auth.requestTransporterLoginOtp(
                      credential: credential,
                      password: password,
                    );
              if (!mounted || !dialogContext.mounted) {
                return;
              }
              setDialogState(() {
                busy = false;
              });
              ScaffoldMessenger.of(dialogContext).showSnackBar(
                SnackBar(
                  content: Text(
                    sent
                        ? 'OTP sent to your email.'
                        : (auth.error ?? 'Unable to send OTP.'),
                  ),
                ),
              );
            }

            return AlertDialog(
              title: const Text('Verify Login'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Enter the OTP sent to your email to continue.'),
                  const SizedBox(height: 14),
                  TextField(
                    controller: otpController,
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                    enabled: !busy,
                    decoration: const InputDecoration(
                      labelText: 'Email OTP',
                      prefixIcon: Icon(Icons.lock_outline),
                      counterText: '',
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: busy
                      ? null
                      : () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                TextButton(
                  onPressed: busy ? null : resendOtp,
                  child: const Text('Resend OTP'),
                ),
                FilledButton(
                  onPressed: busy ? null : verifyOtp,
                  child: busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Verify'),
                ),
              ],
            );
          },
        );
      },
    );

    otpController.dispose();

    if (!mounted) {
      return;
    }
    if (!auth.isLoggedIn) {
      return;
    }
    if (auth.user?.role != widget.allowedRole) {
      auth.logout();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'This app is only for ${_roleLabel(widget.allowedRole)} accounts.',
          ),
        ),
      );
    }
  }

  String _roleLabel(UserRole role) {
    switch (role) {
      case UserRole.driver:
        return 'driver';
      case UserRole.transporter:
        return 'transporter';
      case UserRole.admin:
        return 'admin';
    }
  }

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
              top: -120,
              right: -60,
              child: _GlowBlob(
                size: 280,
                color: const Color(0xFF0A6B6F).withValues(alpha: 0.18),
              ),
            ),
            Positioned(
              bottom: -100,
              left: -40,
              child: _GlowBlob(
                size: 240,
                color: const Color(0xFFE08D3C).withValues(alpha: 0.18),
              ),
            ),
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: StaggeredEntrance(
                    delay: const Duration(milliseconds: 120),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 460),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.9),
                          borderRadius: BorderRadius.circular(30),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.08),
                              blurRadius: 30,
                              offset: const Offset(0, 18),
                            ),
                          ],
                          border: Border.all(
                            color: colors.primary.withValues(alpha: 0.1),
                            width: 1.2,
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(24, 26, 24, 24),
                          child: Consumer<AuthProvider>(
                            builder: (context, auth, _) {
                              return Form(
                                key: _formKey,
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    SizedBox(
                                      height: 56,
                                      child: Image.asset(
                                        'assets/branding/tripmate_wordmark.png',
                                        fit: BoxFit.contain,
                                      ),
                                    ),
                                    const SizedBox(height: 10),
                                    Text(
                                      widget.titleText,
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleLarge,
                                    ),
                                    const SizedBox(height: 6),
                                    Text(
                                      widget.subtitleText,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodyMedium
                                          ?.copyWith(
                                            color: colors.onSurface
                                                .withValues(alpha: 0.72),
                                          ),
                                    ),
                                    const SizedBox(height: 20),
                                    TextFormField(
                                      controller: _credentialController,
                                      decoration: const InputDecoration(
                                        labelText: 'Phone, Email or Username',
                                        prefixIcon: Icon(Icons.person_outline),
                                      ),
                                      validator: (value) {
                                        if (value == null ||
                                            value.trim().isEmpty) {
                                          return 'Phone number, email or username is required';
                                        }
                                        return null;
                                      },
                                    ),
                                    const SizedBox(height: 12),
                                    TextFormField(
                                      controller: _passwordController,
                                      obscureText: _obscurePassword,
                                      decoration: InputDecoration(
                                        labelText: 'Password',
                                        prefixIcon:
                                            const Icon(Icons.lock_outline),
                                        suffixIcon: IconButton(
                                          onPressed: () {
                                            setState(() {
                                              _obscurePassword =
                                                  !_obscurePassword;
                                            });
                                          },
                                          icon: Icon(
                                            _obscurePassword
                                                ? Icons.visibility_outlined
                                                : Icons.visibility_off_outlined,
                                          ),
                                        ),
                                      ),
                                      validator: (value) {
                                        if (value == null ||
                                            value.trim().isEmpty) {
                                          return 'Password is required';
                                        }
                                        return null;
                                      },
                                    ),
                                    Align(
                                      alignment: Alignment.centerRight,
                                      child: TextButton(
                                        onPressed: auth.isLoading
                                            ? null
                                            : () {
                                                Navigator.of(context).push(
                                                  MaterialPageRoute(
                                                    builder: (_) =>
                                                        const ForgotPasswordScreen(),
                                                  ),
                                                );
                                              },
                                        child: const Text('Forgot password?'),
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    Container(
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(16),
                                        gradient: const LinearGradient(
                                          colors: [
                                            Color(0xFF0A6B6F),
                                            Color(0xFF168488),
                                          ],
                                        ),
                                      ),
                                      child: FilledButton(
                                        onPressed:
                                            auth.isLoading ? null : _submit,
                                        style: FilledButton.styleFrom(
                                          backgroundColor: Colors.transparent,
                                          shadowColor: Colors.transparent,
                                        ),
                                        child: auth.isLoading
                                            ? const SizedBox(
                                                height: 18,
                                                width: 18,
                                                child:
                                                    CircularProgressIndicator(
                                                  strokeWidth: 2,
                                                  color: Colors.white,
                                                ),
                                              )
                                            : const Text('Login'),
                                      ),
                                    ),
                                    if (widget.footer != null) ...[
                                      const SizedBox(height: 8),
                                      Align(
                                        alignment: Alignment.centerLeft,
                                        child: widget.footer!,
                                      ),
                                    ],
                                  ],
                                ),
                              );
                            },
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

class _GlowBlob extends StatelessWidget {
  const _GlowBlob({
    required this.size,
    required this.color,
  });

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.96, end: 1.04),
      duration: const Duration(milliseconds: 2800),
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
