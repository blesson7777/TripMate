import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_provider.dart';
import '../../widgets/staggered_entrance.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _otpSent = false;
  bool _obscureNewPassword = true;
  bool _obscureConfirmPassword = true;

  @override
  void dispose() {
    _emailController.dispose();
    _otpController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _sendOtp() async {
    final email = _emailController.text.trim();
    if (!_isValidEmail(email)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid email address')),
      );
      return;
    }

    final auth = context.read<AuthProvider>();
    final sent = await auth.requestPasswordResetOtp(email: email);
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
    final success = await auth.resetPasswordWithOtp(
      email: _emailController.text.trim(),
      otp: _otpController.text.trim(),
      newPassword: _newPasswordController.text.trim(),
      confirmPassword: _confirmPasswordController.text.trim(),
    );

    if (!mounted) {
      return;
    }

    if (!success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(auth.error ?? 'Unable to reset password')),
      );
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Password reset successful. Please login.')),
    );
    Navigator.of(context).pop();
  }

  bool _isValidEmail(String value) {
    return RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(value);
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
        child: SafeArea(
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
                      padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
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
                                      height: 54,
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
                                  'Reset Password',
                                  style: Theme.of(context).textTheme.titleLarge,
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  'Verify OTP from your email and set a new password.',
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyMedium
                                      ?.copyWith(
                                        color: colors.onSurface
                                            .withValues(alpha: 0.72),
                                      ),
                                ),
                                const SizedBox(height: 18),
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
                                          if (!_isValidEmail(text)) {
                                            return 'Enter a valid email address';
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    SizedBox(
                                      height: 52,
                                      width: 132,
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
                                  controller: _newPasswordController,
                                  obscureText: _obscureNewPassword,
                                  decoration: InputDecoration(
                                    labelText: 'New Password',
                                    prefixIcon: const Icon(Icons.lock_outline),
                                    suffixIcon: IconButton(
                                      onPressed: () {
                                        setState(() {
                                          _obscureNewPassword =
                                              !_obscureNewPassword;
                                        });
                                      },
                                      icon: Icon(
                                        _obscureNewPassword
                                            ? Icons.visibility_outlined
                                            : Icons.visibility_off_outlined,
                                      ),
                                    ),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty) {
                                      return 'New password is required';
                                    }
                                    if (text.length < 8) {
                                      return 'Password must be at least 8 characters';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                                TextFormField(
                                  controller: _confirmPasswordController,
                                  obscureText: _obscureConfirmPassword,
                                  decoration: InputDecoration(
                                    labelText: 'Confirm Password',
                                    prefixIcon:
                                        const Icon(Icons.lock_reset_outlined),
                                    suffixIcon: IconButton(
                                      onPressed: () {
                                        setState(() {
                                          _obscureConfirmPassword =
                                              !_obscureConfirmPassword;
                                        });
                                      },
                                      icon: Icon(
                                        _obscureConfirmPassword
                                            ? Icons.visibility_outlined
                                            : Icons.visibility_off_outlined,
                                      ),
                                    ),
                                  ),
                                  validator: (value) {
                                    final text = value?.trim() ?? '';
                                    if (text.isEmpty) {
                                      return 'Please confirm your password';
                                    }
                                    if (text !=
                                        _newPasswordController.text.trim()) {
                                      return 'Passwords do not match';
                                    }
                                    return null;
                                  },
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
                                        : const Icon(Icons.password_rounded),
                                    label: Text(
                                      auth.isLoading
                                          ? 'Processing...'
                                          : 'Verify & Reset Password',
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
