import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../widgets/staggered_entrance.dart';

class DriverRegisterScreen extends StatefulWidget {
  const DriverRegisterScreen({super.key});

  @override
  State<DriverRegisterScreen> createState() => _DriverRegisterScreenState();
}

class _DriverRegisterScreenState extends State<DriverRegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  final _licenseController = TextEditingController();
  final _phoneController = TextEditingController();

  bool _otpSent = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _emailController.dispose();
    _otpController.dispose();
    _licenseController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _sendOtp() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Email is required to send OTP')),
      );
      return;
    }

    final valid = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email);
    if (!valid) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid email address')),
      );
      return;
    }

    final auth = context.read<AuthProvider>();
    final sent = await auth.requestDriverOtp(email: email);
    if (!mounted) {
      return;
    }

    if (!sent) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(auth.error ?? 'Unable to send OTP')),
      );
      return;
    }

    setState(() {
      _otpSent = true;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('OTP sent to your email')),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final auth = context.read<AuthProvider>();
    final success = await auth.registerDriver(
      username: _usernameController.text.trim(),
      password: _passwordController.text.trim(),
      email: _emailController.text.trim(),
      otp: _otpController.text.trim(),
      licenseNumber: _licenseController.text.trim(),
      transporterId: null,
      phone: _optionalValue(_phoneController.text),
    );

    if (!mounted) {
      return;
    }

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(auth.error ?? 'Registration failed')),
      );
      return;
    }

    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  String? _optionalValue(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    return trimmed;
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFFE7F1F0),
              Color(0xFFF8F1E6),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: StaggeredEntrance(
                delay: const Duration(milliseconds: 120),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.94),
                      borderRadius: BorderRadius.circular(30),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.08),
                          blurRadius: 26,
                          offset: const Offset(0, 16),
                        ),
                      ],
                    ),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
                      child: Consumer<AuthProvider>(
                        builder: (context, auth, _) {
                          return Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    SizedBox(
                                      height: 56,
                                      child: Image.asset(
                                        'assets/branding/tripmate_wordmark.png',
                                        fit: BoxFit.contain,
                                      ),
                                    ),
                                    const Spacer(),
                                    IconButton(
                                      onPressed: () =>
                                          Navigator.of(context).pop(),
                                      icon: const Icon(Icons.close_rounded),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'Create Driver Account',
                                  style: Theme.of(context).textTheme.titleLarge,
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Create your account with OTP. Your transporter can allocate you later using your email.',
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyMedium
                                      ?.copyWith(
                                        color: colors.onSurface
                                            .withValues(alpha: 0.72),
                                      ),
                                ),
                                const SizedBox(height: 18),
                                TextFormField(
                                  controller: _usernameController,
                                  decoration: const InputDecoration(
                                    labelText: 'Username',
                                    prefixIcon: Icon(Icons.person_outline),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().isEmpty) {
                                      return 'Username is required';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _licenseController,
                                  decoration: const InputDecoration(
                                    labelText: 'License Number',
                                    prefixIcon: Icon(Icons.badge_outlined),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().isEmpty) {
                                      return 'License number is required';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  children: [
                                    Expanded(
                                      child: TextFormField(
                                        controller: _emailController,
                                        keyboardType:
                                            TextInputType.emailAddress,
                                        decoration: const InputDecoration(
                                          labelText: 'Email',
                                          prefixIcon: Icon(Icons.mail_outline),
                                        ),
                                        validator: (value) {
                                          final text = value?.trim() ?? '';
                                          if (text.isEmpty) {
                                            return 'Email is required';
                                          }
                                          final valid = RegExp(
                                                  r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                                              .hasMatch(text);
                                          if (!valid) {
                                            return 'Enter a valid email address';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    SizedBox(
                                      width: 138,
                                      height: 52,
                                      child: FilledButton.tonalIcon(
                                        onPressed:
                                            auth.isLoading ? null : _sendOtp,
                                        icon: const Icon(
                                            Icons.mark_email_read_outlined),
                                        label: Text(_otpSent
                                            ? 'Resend OTP'
                                            : 'Send OTP'),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _otpController,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(
                                    labelText: 'OTP',
                                    prefixIcon:
                                        Icon(Icons.verified_user_outlined),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty) {
                                      return 'OTP is required';
                                    }
                                    if (text.length != 6) {
                                      return 'OTP must be 6 digits';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _phoneController,
                                  keyboardType: TextInputType.phone,
                                  decoration: const InputDecoration(
                                    labelText: 'Phone (optional)',
                                    prefixIcon: Icon(Icons.call_outlined),
                                  ),
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  children: [
                                    Expanded(
                                      child: TextFormField(
                                        controller: _passwordController,
                                        obscureText: true,
                                        decoration: const InputDecoration(
                                          labelText: 'Password',
                                          prefixIcon: Icon(Icons.lock_outline),
                                        ),
                                        validator: (value) {
                                          if (value == null ||
                                              value.trim().isEmpty) {
                                            return 'Password is required';
                                          }
                                          if (value.trim().length < 8) {
                                            return 'Password must be at least 8 characters';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: TextFormField(
                                        controller: _confirmPasswordController,
                                        obscureText: true,
                                        decoration: const InputDecoration(
                                          labelText: 'Confirm Password',
                                          prefixIcon:
                                              Icon(Icons.lock_reset_outlined),
                                        ),
                                        validator: (value) {
                                          if (value == null ||
                                              value.trim().isEmpty) {
                                            return 'Please confirm your password';
                                          }
                                          if (value.trim() !=
                                              _passwordController.text.trim()) {
                                            return 'Passwords do not match';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 18),
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
                                  child: FilledButton.icon(
                                    onPressed: auth.isLoading ? null : _submit,
                                    style: FilledButton.styleFrom(
                                      backgroundColor: Colors.transparent,
                                      shadowColor: Colors.transparent,
                                    ),
                                    icon: auth.isLoading
                                        ? const SizedBox(
                                            width: 18,
                                            height: 18,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white,
                                            ),
                                          )
                                        : const Icon(
                                            Icons.rocket_launch_outlined),
                                    label: Text(
                                      auth.isLoading
                                          ? 'Processing...'
                                          : 'Verify & Create Account',
                                    ),
                                  ),
                                ),
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
      ),
    );
  }
}
