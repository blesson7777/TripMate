import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/utils/field_validators.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/register_page_shell.dart';
import '../../widgets/staggered_entrance.dart';

class TransporterRegisterScreen extends StatefulWidget {
  const TransporterRegisterScreen({super.key});

  @override
  State<TransporterRegisterScreen> createState() =>
      _TransporterRegisterScreenState();
}

class _TransporterRegisterScreenState extends State<TransporterRegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _companyNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();
  final _gstinController = TextEditingController();
  final _panController = TextEditingController();
  final _websiteController = TextEditingController();

  final _picker = ImagePicker();
  File? _logoFile;

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _otpSent = false;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _companyNameController.dispose();
    _emailController.dispose();
    _otpController.dispose();
    _phoneController.dispose();
    _addressController.dispose();
    _gstinController.dispose();
    _panController.dispose();
    _websiteController.dispose();
    super.dispose();
  }

  Future<void> _pickLogo() async {
    final image = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 85,
    );
    if (image == null) {
      return;
    }
    setState(() {
      _logoFile = File(image.path);
    });
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
    final sent = await auth.requestTransporterOtp(
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
    String? logoBase64;
    if (_logoFile != null) {
      final bytes = await _logoFile!.readAsBytes();
      if (bytes.isNotEmpty) {
        logoBase64 = base64Encode(bytes);
      }
    }

    if (!mounted) {
      return;
    }

    final success = await auth.registerTransporter(
      username: _usernameController.text.trim(),
      password: _passwordController.text.trim(),
      companyName: _companyNameController.text.trim(),
      email: _emailController.text.trim().toLowerCase(),
      otp: _otpController.text.trim(),
      phone: _optionalValue(_phoneController.text),
      address: _optionalValue(_addressController.text),
      gstin: _optionalValue(_gstinController.text),
      pan: _optionalValue(_panController.text),
      website: _optionalValue(_websiteController.text),
      logoBase64: logoBase64,
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
      const SnackBar(
        content: Text('Transporter account created successfully.'),
      ),
    );
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
    return RegisterPageShell(
      title: 'Create Transporter Account',
      subtitle:
          'Set up the transporter profile with branded company details and email OTP verification.',
      icon: Icons.business_center_outlined,
      stepLabels: const [
        'Enter company details',
        'Verify email OTP',
        'Finish secure signup',
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
                    title: 'Company profile',
                    icon: Icons.apartment_outlined,
                    subtitle:
                        'These details flow into billing, reports, and the transporter profile.',
                    child: Column(
                      children: [
                        TextFormField(
                          controller: _companyNameController,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Company Name',
                            prefixIcon: Icon(Icons.business_outlined),
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return 'Company name is required';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 12),
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
                          controller: _phoneController,
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Phone Number',
                            prefixIcon: Icon(Icons.call_outlined),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _addressController,
                          textInputAction: TextInputAction.next,
                          maxLines: 2,
                          decoration: const InputDecoration(
                            labelText: 'Address (optional)',
                            prefixIcon: Icon(Icons.location_on_outlined),
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
                        'The business email receives the 6-digit OTP required for signup.',
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
                                ? 'Enter the OTP sent to the business email.'
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
                    title: 'Business extras',
                    icon: Icons.dataset_outlined,
                    subtitle:
                        'Optional GST, PAN, website, and logo strengthen the billing header and profile.',
                    child: Column(
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _gstinController,
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: 'GSTIN (optional)',
                                  prefixIcon: Icon(Icons.confirmation_num_outlined),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: TextFormField(
                                controller: _panController,
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: 'PAN (optional)',
                                  prefixIcon: Icon(Icons.badge_outlined),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _websiteController,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Website (optional)',
                            prefixIcon: Icon(Icons.public_outlined),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF4F8FA),
                            borderRadius: BorderRadius.circular(18),
                            border: Border.all(
                              color: colors.outline.withValues(alpha: 0.18),
                            ),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 62,
                                height: 62,
                                decoration: BoxDecoration(
                                  color: colors.primary.withValues(alpha: 0.10),
                                  borderRadius: BorderRadius.circular(18),
                                ),
                                alignment: Alignment.center,
                                child: _logoFile == null
                                    ? Icon(
                                        Icons.image_outlined,
                                        color: colors.primary,
                                      )
                                    : ClipRRect(
                                        borderRadius: BorderRadius.circular(16),
                                        child: Image.file(
                                          _logoFile!,
                                          width: 62,
                                          height: 62,
                                          fit: BoxFit.cover,
                                        ),
                                      ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      _logoFile == null
                                          ? 'Add company logo'
                                          : 'Logo selected successfully',
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleSmall
                                          ?.copyWith(fontWeight: FontWeight.w700),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      'This logo prints on the profile and bill header.',
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: colors.onSurface
                                                .withValues(alpha: 0.68),
                                          ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 8),
                              OutlinedButton.icon(
                                onPressed: auth.isLoading ? null : _pickLogo,
                                icon: const Icon(Icons.upload_outlined),
                                label: Text(_logoFile == null ? 'Upload' : 'Change'),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                StaggeredEntrance(
                  delay: const Duration(milliseconds: 260),
                  child: RegisterSectionCard(
                    title: 'Secure password',
                    icon: Icons.lock_outline_rounded,
                    subtitle:
                        'Create a password for daily login, billing tools, and management access.',
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
                          : 'Verify Email & Create Transporter Account',
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
