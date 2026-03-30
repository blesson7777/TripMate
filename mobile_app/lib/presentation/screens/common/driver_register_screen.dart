import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/utils/field_validators.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/register_page_shell.dart';
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

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
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
    final emailError = validateEmailAddress(_emailController.text);
    if (emailError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(emailError)),
      );
      return;
    }

    final auth = context.read<AuthProvider>();
    final sent = await auth.requestDriverOtp(
      email: _emailController.text.trim().toLowerCase(),
    );

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
      SnackBar(
        content: Text('OTP sent to ${_emailController.text.trim()}'),
      ),
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
      email: _emailController.text.trim().toLowerCase(),
      otp: _otpController.text.trim(),
      licenseNumber: normalizeIndianLicenseNumber(_licenseController.text),
      transporterId: null,
      phone: _phoneController.text.trim().isEmpty
          ? null
          : _phoneController.text.trim(),
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

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Driver account created successfully.')),
    );
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return RegisterPageShell(
      title: 'Create Driver Account',
      subtitle:
          'Register the driver profile with email OTP verification and an Indian licence number.',
      icon: Icons.local_shipping_outlined,
      stepLabels: const [
        'Enter driver details',
        'Verify email OTP',
        'Create secure password',
      ],
      child: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          return Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 80),
                  child: RegisterSectionCard(
                    title: 'Driver details',
                    icon: Icons.badge_outlined,
                    subtitle:
                        'Use the same phone number and licence number the transporter already knows.',
                    child: Column(
                      children: [
                        TextFormField(
                          controller: _usernameController,
                          textInputAction: TextInputAction.next,
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
                          textCapitalization: TextCapitalization.characters,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'License Number',
                            hintText: 'KL0720110012345',
                            prefixIcon: Icon(Icons.credit_card_outlined),
                          ),
                          validator: validateIndianLicenseNumber,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _phoneController,
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Phone Number',
                            prefixIcon: Icon(Icons.call_outlined),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 140),
                  child: RegisterSectionCard(
                    title: 'Email verification',
                    icon: Icons.mark_email_read_outlined,
                    subtitle:
                        'TripMate sends a 6-digit OTP to this email before the account is created.',
                    child: Column(
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _emailController,
                                keyboardType: TextInputType.emailAddress,
                                textInputAction: TextInputAction.next,
                                onChanged: (_) {
                                  if (_otpSent || _otpController.text.isNotEmpty) {
                                    setState(() {
                                      _otpSent = false;
                                      _otpController.clear();
                                    });
                                  }
                                },
                                decoration: const InputDecoration(
                                  labelText: 'Email',
                                  prefixIcon: Icon(Icons.mail_outline),
                                ),
                                validator: validateEmailAddress,
                              ),
                            ),
                            const SizedBox(width: 12),
                            SizedBox(
                              width: 124,
                              height: 52,
                              child: FilledButton.tonalIcon(
                                onPressed: auth.isLoading ? null : _sendOtp,
                                icon: const Icon(Icons.send_rounded),
                                label: Text(_otpSent ? 'Resend' : 'Send OTP'),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _otpController,
                          keyboardType: TextInputType.number,
                          textInputAction: TextInputAction.next,
                          maxLength: 6,
                          decoration: InputDecoration(
                            labelText: 'Email OTP',
                            counterText: '',
                            prefixIcon: const Icon(Icons.verified_outlined),
                            helperText: _otpSent
                                ? 'Enter the OTP sent to the registered email address.'
                                : 'Send OTP before creating the account.',
                          ),
                          validator: (value) {
                            if ((value ?? '').trim().length != 6) {
                              return 'Enter the 6-digit OTP';
                            }
                            return null;
                          },
                        ),
                        if (kDebugMode && auth.debugOtp != null) ...[
                          const SizedBox(height: 10),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: colors.primary.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Text(
                              'Debug OTP: ${auth.debugOtp}',
                              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                    color: colors.primary,
                                    fontWeight: FontWeight.w700,
                                  ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 200),
                  child: RegisterSectionCard(
                    title: 'Secure password',
                    icon: Icons.lock_outline_rounded,
                    subtitle:
                        'Create a strong password for login, recovery, and driver access.',
                    child: Column(
                      children: [
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.next,
                          decoration: InputDecoration(
                            labelText: 'Password',
                            prefixIcon: const Icon(Icons.lock_outline),
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscurePassword = !_obscurePassword;
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
                            if (value == null || value.trim().isEmpty) {
                              return 'Password is required';
                            }
                            if (value.trim().length < 8) {
                              return 'Password must be at least 8 characters';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _confirmPasswordController,
                          obscureText: _obscureConfirmPassword,
                          textInputAction: TextInputAction.done,
                          decoration: InputDecoration(
                            labelText: 'Confirm Password',
                            prefixIcon: const Icon(Icons.lock_reset_outlined),
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
                            if (value == null || value.trim().isEmpty) {
                              return 'Please confirm your password';
                            }
                            if (value.trim() != _passwordController.text.trim()) {
                              return 'Passwords do not match';
                            }
                            return null;
                          },
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
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
                      minimumSize: const Size.fromHeight(56),
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
                        : const Icon(Icons.verified_user_outlined),
                    label: Text(
                      auth.isLoading
                          ? 'Creating account...'
                          : 'Verify Email & Create Driver Account',
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
